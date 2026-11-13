"""Safety, permission tracking, blocklist, and audit logging for Computer Use."""

from __future__ import annotations

import ctypes
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_BLOCKED_PROCESSES = frozenset({
    "consent.exe",          # Windows UAC elevation prompt
    "logonui.exe",          # Windows Lock / Sign-in screen
    "credentialuibroker.exe",
    "lockapp.exe",
    "1password.exe",
    "bitwarden.exe",
    "keepass.exe",
    "keepassxc.exe",
    "dashlane.exe",
    "lastpass.exe",
    "enpass.exe",
})

DEFAULT_BLOCKED_TITLE_SUBSTRINGS = (
    "user account control",
    "kullanıcı hesabı denetimi",
    "windows security",
    "windows güvenliği",
)

DEFAULT_DANGEROUS_KEY_COMBOS = frozenset({
    "alt+f4",
    "ctrl+alt+delete",
    "ctrl+alt+del",
    "win+l",
})

VK_PAUSE = 0x13
VK_ESCAPE = 0x1B
MAX_AUDIT_BYTES = 5 * 1024 * 1024


def resolve_data_dir() -> Path:
    """Resolve persistent data directory for Computer Use state and logs."""
    raw = (
        os.environ.get("COMPUTER_USE_DATA_DIR")
        or os.environ.get("PLUGIN_DATA")
        or str(Path.home() / ".gemini" / "config" / "plugins" / "computer-use" / "data")
    )
    path = Path(raw)
    path.mkdir(parents=True, exist_ok=True)
    (path / "screenshots").mkdir(parents=True, exist_ok=True)
    return path


def _normalize_app_name(name: str) -> str:
    cleaned = name.strip().lower()
    if cleaned.endswith(".exe"):
        cleaned = cleaned[:-4]
    return cleaned


def _normalize_key_combo(combo: str) -> str:
    parts = [p.strip().lower() for p in combo.replace("-", "+").split("+") if p.strip()]
    aliases = {
        "control": "ctrl",
        "control_l": "ctrl",
        "control_r": "ctrl",
        "alt_l": "alt",
        "alt_r": "alt",
        "menu": "alt",
        "shift_l": "shift",
        "shift_r": "shift",
        "super": "win",
        "super_l": "win",
        "super_r": "win",
        "cmd": "win",
        "meta": "win",
        "del": "delete",
    }
    normalized = [aliases.get(p, p) for p in parts]
    modifiers = sorted(p for p in normalized if p in {"ctrl", "alt", "shift", "win"})
    keys = [p for p in normalized if p not in {"ctrl", "alt", "shift", "win"}]
    return "+".join([*modifiers, *keys])


@dataclass
class SafetyPolicy:
    """Configurable runtime safety policy for desktop automation."""

    require_app_grant: bool = False
    allow_system_shortcuts: bool = False
    show_overlay: bool = True
    smooth_cursor_ms: int = 220
    annotate_mode: str = "grid"
    blocked_processes: set[str] = field(default_factory=lambda: set(DEFAULT_BLOCKED_PROCESSES))
    blocked_title_substrings: tuple[str, ...] = DEFAULT_BLOCKED_TITLE_SUBSTRINGS
    dangerous_key_combos: set[str] = field(default_factory=lambda: set(DEFAULT_DANGEROUS_KEY_COMBOS))


class SafetyManager:
    """Manages per-app grants, sensitive target blocks, emergency stop, and audit logs."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or resolve_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.policy_path = self.data_dir / "policy.json"
        self.grants_path = self.data_dir / "session_grants.json"
        self.audit_path = self.data_dir / "audit.jsonl"
        self.emergency_flag_path = self.data_dir / "emergency_stop.flag"
        self.policy = self._load_policy()
        self.granted_apps: dict[str, dict[str, Any]] = self._load_grants()
        self._ai_active_until: float = 0.0
        self._synthetic_esc_until: float = 0.0
        self._last_esc_tap_ts: float = 0.0
        self._esc_was_down: bool = False

    def _load_policy(self) -> SafetyPolicy:
        policy = SafetyPolicy()
        if not self.policy_path.exists():
            return policy
        try:
            raw = json.loads(self.policy_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return policy

        if isinstance(raw.get("require_app_grant"), bool):
            policy.require_app_grant = raw["require_app_grant"]
        if isinstance(raw.get("allow_system_shortcuts"), bool):
            policy.allow_system_shortcuts = raw["allow_system_shortcuts"]
        if isinstance(raw.get("show_overlay"), bool):
            policy.show_overlay = raw["show_overlay"]
        if isinstance(raw.get("smooth_cursor_ms"), int):
            policy.smooth_cursor_ms = max(0, min(500, raw["smooth_cursor_ms"]))
        if raw.get("annotate_mode") in {"none", "grid", "som"}:
            policy.annotate_mode = str(raw["annotate_mode"])
        if isinstance(raw.get("extra_blocked_processes"), list):
            for proc in raw["extra_blocked_processes"]:
                if isinstance(proc, str) and proc.strip():
                    policy.blocked_processes.add(proc.strip().lower())
        if isinstance(raw.get("unblocked_processes"), list):
            for proc in raw["unblocked_processes"]:
                if isinstance(proc, str):
                    policy.blocked_processes.discard(proc.strip().lower())
        return policy

    def save_policy(self) -> None:
        """Persist non-default policy overrides cleanly."""
        payload = {
            "require_app_grant": self.policy.require_app_grant,
            "allow_system_shortcuts": self.policy.allow_system_shortcuts,
            "show_overlay": self.policy.show_overlay,
            "smooth_cursor_ms": self.policy.smooth_cursor_ms,
            "annotate_mode": self.policy.annotate_mode,
            "extra_blocked_processes": sorted(self.policy.blocked_processes - DEFAULT_BLOCKED_PROCESSES),
            "unblocked_processes": sorted(DEFAULT_BLOCKED_PROCESSES - self.policy.blocked_processes),
        }
        self.policy_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _load_grants(self) -> dict[str, dict[str, Any]]:
        if not self.grants_path.exists():
            return {}
        try:
            data = json.loads(self.grants_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_grants(self) -> None:
        self.grants_path.write_text(json.dumps(self.granted_apps, indent=2), encoding="utf-8")

    def mark_ai_activity(self, window_sec: float = 20.0) -> None:
        """Record recent AI desktop control so double-Esc physical takeover is armed."""
        self._ai_active_until = max(self._ai_active_until, time.monotonic() + max(0.0, window_sec))

    def mark_synthetic_escape(self, ignore_sec: float = 0.6) -> None:
        """Suppress physical double-Esc detection right after AI sends synthetic Escape."""
        self._synthetic_esc_until = max(self._synthetic_esc_until, time.monotonic() + max(0.0, ignore_sec))
        self._last_esc_tap_ts = 0.0
        self._esc_was_down = False

    def is_emergency_stopped(self) -> tuple[bool, str]:
        """Check whether emergency stop flag file, Pause key, or double-Esc handover is active."""
        if self.emergency_flag_path.exists():
            return True, "Emergency stop is active. Call emergency_stop(reset=true) or click Devam Et to resume."
        try:
            # High-order bit indicates key is currently held.
            if ctypes.windll.user32.GetAsyncKeyState(VK_PAUSE) & 0x8000:
                self.set_emergency_stop(True, "Pause/Break tuşu ile kontrol devralındı.")
                return True, "Emergency stop triggered via Pause/Break key."

            now = time.monotonic()
            if now <= self._ai_active_until and now > self._synthetic_esc_until:
                esc_down = bool(ctypes.windll.user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000)
                if esc_down and not self._esc_was_down:
                    if 0.0 < (now - self._last_esc_tap_ts) <= 0.45:
                        self._last_esc_tap_ts = 0.0
                        self._esc_was_down = True
                        self.set_emergency_stop(True, "Çift Esc ile kontrol devralındı.")
                        return True, "Emergency stop triggered via double-Esc handover."
                    self._last_esc_tap_ts = now
                self._esc_was_down = esc_down
        except Exception:
            pass
        return False, ""

    def set_emergency_stop(self, active: bool, reason: str = "User or agent requested stop") -> dict[str, Any]:
        """Activate or clear emergency stop state."""
        if active:
            self.emergency_flag_path.write_text(
                json.dumps({"stopped_at": time.time(), "reason": reason}),
                encoding="utf-8",
            )
        elif self.emergency_flag_path.exists():
            self.emergency_flag_path.unlink()
        return {"emergency_stop": active, "reason": reason}

    def is_blocked_target(self, process_name: str, title: str) -> tuple[bool, str]:
        """Determine whether a target window/process is protected by security guardrails."""
        proc_lower = (process_name or "").strip().lower()
        title_lower = (title or "").strip().lower()
        if proc_lower in self.policy.blocked_processes:
            return True, f"Target process '{process_name}' is protected by Computer Use security policy."
        for needle in self.policy.blocked_title_substrings:
            if needle in title_lower:
                return True, f"Target window '{title}' matches protected security UI ('{needle}')."
        return False, ""

    def request_access(
        self,
        app_names: list[str],
        reason: str,
        allow_clipboard: bool = False,
    ) -> dict[str, Any]:
        """Grant session-scoped access to specified non-blocked applications."""
        granted: list[str] = []
        denied: list[dict[str, str]] = []
        now = time.time()

        for app in app_names:
            norm = _normalize_app_name(app)
            if not norm:
                continue
            blocked, block_reason = self.is_blocked_target(f"{norm}.exe", app)
            if blocked:
                denied.append({"app": app, "reason": block_reason})
                continue
            self.granted_apps[norm] = {
                "display_name": app,
                "reason": reason,
                "allow_clipboard": allow_clipboard,
                "granted_at": now,
            }
            granted.append(app)

        self._save_grants()
        return {
            "granted": granted,
            "denied": denied,
            "granted_apps": self.list_granted_applications(),
        }

    def revoke_access(self, app_names: list[str] | None = None) -> dict[str, Any]:
        """Revoke access for specific applications or all granted applications."""
        if not app_names:
            self.granted_apps.clear()
        else:
            for app in app_names:
                self.granted_apps.pop(_normalize_app_name(app), None)
        self._save_grants()
        return {"granted_apps": self.list_granted_applications()}

    def list_granted_applications(self) -> list[dict[str, Any]]:
        """Return currently granted application records."""
        return [
            {"key": key, **meta}
            for key, meta in sorted(self.granted_apps.items())
        ]

    def check_input_allowed(
        self,
        action_name: str,
        frontmost: dict[str, Any] | None,
        current_elevated: bool,
        key_combo: str | None = None,
    ) -> tuple[bool, str]:
        """Validate whether an input action is safe and permitted to execute."""
        stopped, stop_msg = self.is_emergency_stopped()
        if stopped:
            return False, stop_msg

        if key_combo:
            norm_combo = _normalize_key_combo(key_combo)
            if not self.policy.allow_system_shortcuts and norm_combo in self.policy.dangerous_key_combos:
                return (
                    False,
                    f"Shortcut '{key_combo}' is blocked by default safety policy. "
                    "Enable allow_system_shortcuts via configure_safety if the user explicitly requested it.",
                )

        if frontmost:
            proc = str(frontmost.get("process_name") or "")
            title = str(frontmost.get("title") or "")
            blocked, reason = self.is_blocked_target(proc, title)
            if blocked:
                return False, reason

            if frontmost.get("is_elevated") and not current_elevated:
                return (
                    False,
                    f"Foreground window '{title}' ({proc}) is running elevated as Administrator, "
                    "while the MCP server is non-elevated. Windows UIPI blocks synthetic input to elevated windows.",
                )

            if self.policy.require_app_grant and proc:
                norm = _normalize_app_name(proc)
                if norm not in self.granted_apps:
                    return (
                        False,
                        f"Strict app grant mode is enabled and '{proc}' has not been granted access yet. "
                        "Call request_access first.",
                    )

        return True, ""

    def audit(
        self,
        tool_name: str,
        args: dict[str, Any],
        ok: bool,
        frontmost: dict[str, Any] | None = None,
        error: str | None = None,
        redact_text: bool = False,
    ) -> None:
        """Append a sanitized JSONL audit entry with size rotation."""
        try:
            if self.audit_path.exists() and self.audit_path.stat().st_size > MAX_AUDIT_BYTES:
                rotated = self.data_dir / "audit.prev.jsonl"
                if rotated.exists():
                    rotated.unlink()
                self.audit_path.rename(rotated)

            sanitized = dict(args)
            if "text" in sanitized and isinstance(sanitized["text"], str):
                if redact_text:
                    sanitized["text"] = f"<REDACTED len={len(sanitized['text'])}>"
                elif len(sanitized["text"]) > 120:
                    sanitized["text"] = sanitized["text"][:117] + "..."

            entry = {
                "ts": round(time.time(), 3),
                "tool": tool_name,
                "ok": ok,
                "args": sanitized,
                "frontmost": {
                    "process": frontmost.get("process_name"),
                    "title": frontmost.get("title"),
                }
                if frontmost
                else None,
                "error": error,
            }
            with self.audit_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass
