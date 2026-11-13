#!/usr/bin/env node
/**
 * Ultra-fast YouTube Studio Uploader via Chrome DevTools Protocol (CDP Code Mode).
 * Uses Node 24 native fetch + WebSocket (zero external dependencies) to upload queued
 * Shorts directly through the user's already-authenticated Chrome session in ~15-30s/video.
 */

import fs from "node:fs";
import path from "node:path";

const DEFAULT_QUEUE = path.resolve(process.cwd(), "output", "ready", "upload_queue.json");
const STUDIO_URL = "https://studio.youtube.com";

function parseArgs(argv) {
  const opts = {
    queue: DEFAULT_QUEUE,
    cdpUrl: process.env.CHROME_CDP_URL || "http://127.0.0.1:9222",
    stem: null,
    limit: 0,
    dryRun: false,
    checkOnly: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === "--queue" && argv[i + 1]) opts.queue = path.resolve(argv[++i]);
    else if (a === "--cdp-url" && argv[i + 1]) opts.cdpUrl = argv[++i];
    else if (a === "--stem" && argv[i + 1]) opts.stem = argv[++i];
    else if (a === "--limit" && argv[i + 1]) opts.limit = Number(argv[++i]) || 0;
    else if (a === "--dry-run") opts.dryRun = true;
    else if (a === "--check") opts.checkOnly = true;
  }
  return opts;
}

class CDPClient {
  constructor(wsUrl) {
    this.wsUrl = wsUrl;
    this.ws = null;
    this.nextId = 1;
    this.pending = new Map();
    this.events = [];
  }

  async connect(timeoutMs = 35000) {
    this.ws = new WebSocket(this.wsUrl);
    await new Promise((resolve, reject) => {
      const hintTimer = setTimeout(() => {
        console.error('[CDP] Chrome "Uzaktan hata ayiklamaya izin verilsin mi?" (Allow remote debugging) onay penceresi acildiysa lutfen Chrome\'da Izin ver\'e tiklayin...');
      }, 1500);
      const t = setTimeout(() => {
        clearTimeout(hintTimer);
        reject(new Error(`CDP_APPROVAL_TIMEOUT: Timed out after ${timeoutMs}ms connecting to ${this.wsUrl}. Confirm Chrome's "Allow remote debugging?" dialog if shown.`));
      }, timeoutMs);
      this.ws.addEventListener("open", () => {
        clearTimeout(hintTimer);
        clearTimeout(t);
        resolve();
      });
      this.ws.addEventListener("error", (err) => {
        clearTimeout(hintTimer);
        clearTimeout(t);
        reject(new Error(err?.message || "WebSocket error"));
      });
    });
    this.ws.addEventListener("message", (ev) => {
      const msg = JSON.parse(typeof ev.data === "string" ? ev.data : ev.data.toString());
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        if (msg.error) reject(new Error(`${msg.error.message} (${msg.error.code})`));
        else resolve(msg.result);
      } else if (msg.method) {
        this.events.push(msg);
      }
    });
  }

  send(method, params = {}, sessionId = undefined) {
    const id = this.nextId++;
    const payload = sessionId ? { id, method, params, sessionId } : { id, method, params };
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id);
          reject(new Error(`CDP timeout calling ${method}`));
        }
      }, 25000);
      this.pending.set(id, {
        resolve: (res) => {
          clearTimeout(timer);
          resolve(res);
        },
        reject: (err) => {
          clearTimeout(timer);
          reject(err);
        },
      });
      this.ws.send(JSON.stringify(payload));
    });
  }

  close() {
    try {
      this.ws?.close();
    } catch {
      // ignore
    }
  }
}

export async function discoverCdpBrowserWs(cdpUrl = "http://127.0.0.1:9222") {
  // 1. Check explicit /json/version HTTP endpoint (--remote-debugging-port)
  try {
    const res = await fetch(`${cdpUrl.replace(/\/$/, "")}/json/version`, {
      signal: AbortSignal.timeout(1200),
    });
    if (res.ok) {
      const data = await res.json();
      if (data?.webSocketDebuggerUrl) {
        return { wsUrl: data.webSocketDebuggerUrl, source: "http_json_version" };
      }
    }
  } catch {
    // try DevToolsActivePort fallback
  }

  // 2. Check Chrome M136+ chrome://inspect/#remote-debugging DevToolsActivePort file
  const localAppData = process.env.LOCALAPPDATA || "";
  const activePortFile = path.join(localAppData, "Google", "Chrome", "User Data", "DevToolsActivePort");
  if (localAppData && fs.existsSync(activePortFile)) {
    const lines = fs.readFileSync(activePortFile, "utf8").trim().split(/\r?\n/);
    const port = Number(lines[0]?.trim());
    const wsPath = (lines[1] || "").trim();
    if (port > 0 && wsPath.startsWith("/")) {
      return { wsUrl: `ws://127.0.0.1:${port}${wsPath}`, source: "DevToolsActivePort" };
    }
  }
  return null;
}

const SLEEP = (ms) => new Promise((r) => setTimeout(r, ms));

async function evalInPage(cdp, sessionId, fnSource, arg = undefined) {
  const expr = arg === undefined ? `(${fnSource})()` : `(${fnSource})(${JSON.stringify(arg)})`;
  const res = await cdp.send(
    "Runtime.evaluate",
    { expression: expr, awaitPromise: true, returnByValue: true },
    sessionId
  );
  if (res?.exceptionDetails) {
    const desc = res.exceptionDetails.exception?.description || res.exceptionDetails.text || "JS exception";
    throw new Error(desc);
  }
  return res?.result?.value;
}

async function waitForCondition(cdp, sessionId, predicateSource, arg = undefined, timeoutMs = 15000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const val = await evalInPage(cdp, sessionId, predicateSource, arg);
    if (val) return val;
    await SLEEP(150);
  }
  throw new Error(`Timed out after ${timeoutMs}ms waiting for Studio condition`);
}

// In-page helper injected once per page session: supports Shadow DOM traversal + Polymer typing.
const INSTALL_HELPERS_FN = () => {
  if (window.__antigravityStudioHelpers) return true;
  const qAllDeep = (selector, root = document) => {
    const out = [];
    const seen = new Set();
    const visit = (node) => {
      if (!node || !node.querySelectorAll) return;
      for (const el of node.querySelectorAll(selector)) {
        if (!seen.has(el)) {
          seen.add(el);
          out.push(el);
        }
      }
      for (const el of node.querySelectorAll("*")) {
        if (el.shadowRoot) visit(el.shadowRoot);
      }
    };
    visit(root);
    return out;
  };
  const visible = (el) => {
    if (!el) return false;
    const style = getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") return false;
    const r = el.getBoundingClientRect();
    return r.width > 1 && r.height > 1;
  };
  const clickEl = (el) => {
    if (!el) return false;
    el.scrollIntoView({ block: "center", inline: "center" });
    el.click();
    return true;
  };
  const clickByText = (patterns, selectors = 'button, ytcp-button, tp-yt-paper-item, tp-yt-paper-radio-button, [role="button"], [role="radio"], [role="option"]') => {
    const pats = Array.isArray(patterns) ? patterns : [patterns];
    const els = qAllDeep(selectors).filter(visible);
    for (const pat of pats) {
      const re = new RegExp(pat, "i");
      const hit = els.find((el) => re.test((el.innerText || el.textContent || el.getAttribute("aria-label") || "").trim()));
      if (hit) return clickEl(hit);
    }
    return false;
  };
  const setEditableText = (el, text) => {
    if (!el) return false;
    el.scrollIntoView({ block: "center" });
    el.focus();
    if ("value" in el && el.tagName !== "DIV") {
      el.value = "";
      el.value = text;
      el.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
      el.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
      return true;
    }
    const sel = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(el);
    sel.removeAllRanges();
    sel.addRange(range);
    document.execCommand("delete", false);
    document.execCommand("insertText", false, text);
    el.dispatchEvent(new InputEvent("input", { bubbles: true, composed: true, data: text, inputType: "insertText" }));
    el.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    return true;
  };
  window.__antigravityStudioHelpers = { qAllDeep, visible, clickEl, clickByText, setEditableText };
  return true;
};

async function attachStudioSession(cdp) {
  const { targetInfos } = await cdp.send("Target.getTargets");
  let page = targetInfos.find((t) => t.type === "page" && t.url.includes("studio.youtube.com"));
  if (!page) {
    const { targetId } = await cdp.send("Target.createTarget", { url: STUDIO_URL });
    page = { targetId, url: STUDIO_URL };
    await SLEEP(1500);
  } else {
    await cdp.send("Target.activateTarget", { targetId: page.targetId });
  }
  const { sessionId } = await cdp.send("Target.attachToTarget", { targetId: page.targetId, flatten: true });
  await Promise.all([
    cdp.send("Page.enable", {}, sessionId),
    cdp.send("Runtime.enable", {}, sessionId),
    cdp.send("DOM.enable", {}, sessionId),
  ]);
  return { sessionId, targetId: page.targetId };
}

async function uploadSingleItem(cdp, sessionId, item) {
  const t0 = Date.now();
  const absVideo = path.resolve(item.video_path);
  if (!fs.existsSync(absVideo)) {
    throw new Error(`Missing video file: ${absVideo}`);
  }

  // Ensure Studio dashboard is loaded and signed in
  const curUrl = await evalInPage(cdp, sessionId, () => location.href);
  if (!curUrl.includes("studio.youtube.com")) {
    await cdp.send("Page.navigate", { url: STUDIO_URL }, sessionId);
  }
  await waitForCondition(cdp, sessionId, () => {
    if (location.hostname.includes("accounts.google.com")) return "LOGIN_REQUIRED";
    return Boolean(document.querySelector("ytcp-button#create-icon, #upload-icon, input[type='file']"));
  }, undefined, 20000);

  const authCheck = await evalInPage(cdp, sessionId, () => location.hostname);
  if (authCheck.includes("accounts.google.com")) {
    throw new Error("LOGIN_REQUIRED: Please sign in to YouTube Studio in Chrome first.");
  }

  await evalInPage(cdp, sessionId, INSTALL_HELPERS_FN);

  // Open Upload Dialog if file input is not already mounted
  const hasInput = await evalInPage(cdp, sessionId, () => {
    const h = window.__antigravityStudioHelpers;
    return h.qAllDeep('input[type="file"]').length > 0;
  });
  if (!hasInput) {
    await evalInPage(cdp, sessionId, () => {
      const h = window.__antigravityStudioHelpers;
      const createBtn = h.qAllDeep("ytcp-button#create-icon, #upload-icon")[0];
      if (createBtn) h.clickEl(createBtn);
    });
    await SLEEP(250);
    await evalInPage(cdp, sessionId, () => {
      const h = window.__antigravityStudioHelpers;
      if (h.qAllDeep('input[type="file"]').length === 0) {
        h.clickByText(["video yükle", "upload video", "yükle", "upload"]);
      }
    });
  }

  // Attach video file directly via CDP DOM.setFileInputFiles (no OS #32770 file picker!)
  await waitForCondition(cdp, sessionId, () => {
    const h = window.__antigravityStudioHelpers;
    return h.qAllDeep('input[type="file"]').length > 0;
  }, undefined, 10000);

  const fileInputObj = await cdp.send(
    "Runtime.evaluate",
    {
      expression: "window.__antigravityStudioHelpers.qAllDeep('input[type=\"file\"]')[0]",
      returnByValue: false,
    },
    sessionId
  );
  const objectId = fileInputObj?.result?.objectId;
  if (!objectId) throw new Error("Failed to acquire input[type=file] remote objectId");
  await cdp.send("DOM.setFileInputFiles", { files: [absVideo], objectId }, sessionId);

  // Wait for Title & Description editors in Details dialog
  await waitForCondition(cdp, sessionId, () => {
    const h = window.__antigravityStudioHelpers;
    const boxes = h.qAllDeep('ytcp-video-title #textbox[contenteditable="true"], #title-textarea #textbox, #textbox[contenteditable="true"]').filter(h.visible);
    return boxes.length >= 2;
  }, undefined, 25000);

  // Populate Title, Description, Made-for-Kids, Show More, Altered Content, Tags cleanly in 1 eval
  const prepMeta = {
    title: String(item.title || "").slice(0, 100),
    description: String(item.description || "").slice(0, 5000),
    tags: Array.isArray(item.tags) ? item.tags.join(", ") : String(item.tags_csv || ""),
    madeForKids: Boolean(item.studio_settings?.made_for_kids),
    alteredContent: Boolean(item.studio_settings?.altered_content),
  };

  await evalInPage(cdp, sessionId, (meta) => {
    const h = window.__antigravityStudioHelpers;
    const titleBox = h.qAllDeep('ytcp-video-title #textbox[contenteditable="true"], #title-textarea #textbox')[0];
    const descBox = h.qAllDeep('ytcp-video-description #textbox[contenteditable="true"], #description-textarea #textbox')[0];
    if (titleBox) h.setEditableText(titleBox, meta.title);
    if (descBox) h.setEditableText(descBox, meta.description);

    const kidsName = meta.madeForKids ? "VIDEO_MADE_FOR_KIDS_MFK" : "VIDEO_MADE_FOR_KIDS_NOT_MFK";
    const kidsBtn = h.qAllDeep(`tp-yt-paper-radio-button[name="${kidsName}"], [name="${kidsName}"]`)[0];
    if (kidsBtn) h.clickEl(kidsBtn);

    const toggleMore = h.qAllDeep("#toggle-button")[0];
    if (toggleMore && h.visible(toggleMore)) {
      const lbl = (toggleMore.innerText || "").toLowerCase();
      if (lbl.includes("more") || lbl.includes("fazla")) h.clickEl(toggleMore);
    }
  }, prepMeta);

  await SLEEP(300);

  // Fill Altered Content + Tags after Show More expansion
  await evalInPage(cdp, sessionId, (meta) => {
    const h = window.__antigravityStudioHelpers;
    const altChoice = meta.alteredContent ? "YES" : "NO";
    const altRadio = h.qAllDeep(
      `ytcp-altered-content-select tp-yt-paper-radio-button[name="${altChoice}"], tp-yt-paper-radio-button[name="VIDEO_HAS_ALTERED_CONTENT_${altChoice}"]`
    )[0];
    if (altRadio) h.clickEl(altRadio);

    const tagInput = h.qAllDeep('#tags-container input#text-input, ytcp-form-input-container#tags-container input')[0];
    if (tagInput && meta.tags) {
      tagInput.scrollIntoView({ block: "center" });
      tagInput.focus();
      h.setEditableText(tagInput, meta.tags);
      tagInput.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, bubbles: true }));
    }
  }, prepMeta);

  await SLEEP(250);

  // Advance Details -> Video elements -> Checks -> Visibility
  for (let step = 0; step < 3; step += 1) {
    await evalInPage(cdp, sessionId, () => {
      const h = window.__antigravityStudioHelpers;
      const nextBtn = h.qAllDeep("#next-button")[0];
      if (nextBtn) h.clickEl(nextBtn);
    });
    await SLEEP(350);
  }

  // Select Visibility radio (fail-safe to PRIVATE instead of prematurely publishing SCHEDULED items publicly)
  const visName = (item.recommended_visibility || "public").toUpperCase();
  const mappedVis =
    visName === "UNLISTED"
      ? "UNLISTED"
      : (visName === "PRIVATE" || visName === "SCHEDULED" ? "PRIVATE" : "PUBLIC");
  await waitForCondition(cdp, sessionId, (vName) => {
    const h = window.__antigravityStudioHelpers;
    const rad = h.qAllDeep(`tp-yt-paper-radio-button[name="${vName}"]`)[0];
    if (rad) {
      h.clickEl(rad);
      return true;
    }
    return false;
  }, mappedVis, 10000);

  // Wait up to 90s for upload % + HD/SD check readiness if #done-button is disabled
  await waitForCondition(cdp, sessionId, () => {
    const h = window.__antigravityStudioHelpers;
    const done = h.qAllDeep("#done-button")[0];
    return Boolean(done && !done.disabled && done.getAttribute("aria-disabled") !== "true");
  }, undefined, 90000);

  await evalInPage(cdp, sessionId, () => {
    const h = window.__antigravityStudioHelpers;
    const done = h.qAllDeep("#done-button")[0];
    if (done) h.clickEl(done);
  });

  // Extract published video URL from confirmation dialog
  const videoUrl = await waitForCondition(cdp, sessionId, () => {
    const h = window.__antigravityStudioHelpers;
    const links = h.qAllDeep('a[href*="youtu.be/"], a[href*="youtube.com/shorts/"], a[href*="youtube.com/watch"]');
    const valid = links.map((a) => a.href).find((u) => /^https:\/\/(youtu\.be|www\.youtube\.com|youtube\.com)\//.test(u));
    return valid || null;
  }, undefined, 25000);

  // Close publish confirmation dialog cleanly
  await evalInPage(cdp, sessionId, () => {
    const h = window.__antigravityStudioHelpers;
    const closeBtn = h.qAllDeep("#close-button, ytcp-uploads-still-processing-dialog #close-button")[0];
    if (closeBtn && h.visible(closeBtn)) h.clickEl(closeBtn);
  });

  return {
    stem: item.stem,
    video_url: videoUrl,
    elapsed_sec: Number(((Date.now() - t0) / 1000).toFixed(2)),
  };
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  const cdpInfo = await discoverCdpBrowserWs(opts.cdpUrl);

  if (opts.checkOnly) {
    console.log(JSON.stringify({ ok: Boolean(cdpInfo), cdp: cdpInfo }, null, 2));
    process.exit(cdpInfo ? 0 : 2);
  }

  if (!fs.existsSync(opts.queue)) {
    console.error(JSON.stringify({ ok: false, error: "QUEUE_NOT_FOUND", queue: opts.queue }));
    process.exit(1);
  }

  const queue = JSON.parse(fs.readFileSync(opts.queue, "utf8"));
  const TERMINAL_STATUSES = new Set(["published", "scheduled", "uploaded"]);
  let pending = (queue.items || []).filter((it) => !TERMINAL_STATUSES.has(String(it.status || "").toLowerCase()));
  if (opts.stem) pending = (queue.items || []).filter((it) => it.stem === opts.stem);
  if (opts.limit > 0) pending = pending.slice(0, opts.limit);

  if (opts.dryRun) {
    console.log(JSON.stringify({
      ok: true,
      dry_run: true,
      cdp_available: Boolean(cdpInfo),
      cdp: cdpInfo,
      pending_stems: pending.map((p) => p.stem),
    }, null, 2));
    process.exit(0);
  }

  if (pending.length === 0) {
    console.log(JSON.stringify({ ok: true, skipped_all: true, pending_stems: [], uploaded: [] }, null, 2));
    process.exit(0);
  }

  if (!cdpInfo) {
    console.error(JSON.stringify({
      ok: false,
      error: "CDP_UNAVAILABLE",
      hint: "Enable chrome://inspect/#remote-debugging in Chrome OR launch Chrome with --remote-debugging-port=9222; otherwise fall back to Tier 2 computer-use batch.",
    }));
    process.exit(2);
  }

  const cdp = new CDPClient(cdpInfo.wsUrl);
  const results = [];
  try {
    await cdp.connect();
    const { sessionId } = await attachStudioSession(cdp);
    for (const item of pending) {
      const r = await uploadSingleItem(cdp, sessionId, item);
      results.push(r);
    }
    console.log(JSON.stringify({ ok: true, cdp_source: cdpInfo.source, uploaded: results }, null, 2));
  } finally {
    cdp.close();
  }
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"));
if (isMain) {
  main().catch((err) => {
    console.error(JSON.stringify({ ok: false, error: err?.message || String(err) }));
    process.exit(1);
  });
}
