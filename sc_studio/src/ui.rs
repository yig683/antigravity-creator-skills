//! Masaüstü penceresi (tao + wry → WebView2) ve uygulama içi tarayıcı.

use crate::accounts::Identity;
use crate::session::{restore_cookies, set_soundcloud_oauth_cookie, snapshot_cookies, wipe_session_blocking};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tao::dpi::{PhysicalPosition, PhysicalSize, Size};
use tao::event::{Event, WindowEvent};
use tao::event_loop::{ControlFlow, EventLoopBuilder, EventLoopWindowTarget};
use tao::window::{Window, WindowBuilder};
use wry::{WebView, WebViewBuilder};

#[cfg(windows)]
fn hwnd_of(w: &Window) -> isize {
    use tao::platform::windows::WindowExtWindows;
    w.hwnd() as isize
}

#[cfg(not(windows))]
fn hwnd_of(_w: &Window) -> isize {
    0
}

/// Dahili SoundCloud yükleme penceresine aktarılacak parça verisi.
#[derive(Debug, Clone)]
pub struct UploadJob {
    pub filename: String,
    pub title: String,
    pub audio_b64: String,
    pub cover_b64: Option<String>,
    pub auto_submit: bool,
    pub sharing: String,
    pub skip_monetize: bool,
}

/// SoundCloud for Artists Monetization otomasyonu için iş tanımı.
#[derive(Debug, Clone)]
pub struct MonetizeJob {
    pub target_title: Option<String>,
    pub resubmit_rejected: bool,
    pub submit_unsubmitted: bool,
    pub artist_hint: String,
    pub intro_note: String,
}

/// Arayüz thread'ine gönderilen olaylar (HTTP / IPC katmanından tetiklenir).
#[derive(Debug, Clone)]
pub enum UiEvent {
    /// Tarayıcı penceresini aç / öne getir. Adres verilirse oraya git
    /// ("SoundCloud ile giriş yap" giriş sayfasıyla).
    OpenBrowser(Option<String>),
    /// Dahili SoundCloud child WebView konum/görünürlük güncellemesi.
    ScBounds {
        visible: bool,
        x: f64,
        y: f64,
        w: f64,
        h: f64,
    },
    /// Dahili SoundCloud WebView içinde gezin ("back", "forward", "reload" veya URL).
    ScNavigate(String),
    /// WebView2 SoundCloud çerezlerini ve tarama verisini temizler (temiz çıkış).
    ScClearSession,
    /// Hesap ekle: mevcut oturumu kaydet, temiz bir oturumla giriş penceresini aç.
    AddAccount,
    /// Hesap değiştir: önceki hesabın oturumunu kaydet, hedef hesabın oturumunu yükle.
    SwitchAccount { from: Identity, to: String },
    /// Hesabın oturum çerezlerini kaydet (çıkıştan / token değişiminden önce).
    SnapshotAccount(Identity),
    /// Kullanıcı tarafından verilen SoundCloud oauth_token çerezini WebView2'ye yükler.
    ScSetOauthCookie(String),
    /// Arşivdeki bir MP3 + kapağı doğrudan SoundCloud /upload formuna aktar.
    ScInjectUpload(UploadJob),
    /// Aktif yükleme/monetize otomasyonunu iptal eder.
    ScCancelUpload,
    /// Yüklenen veya reddedilen parçalar için artists.soundcloud.com monetize başvurusu başlat.
    ScStartMonetize(MonetizeJob),
    /// Tarayıcıda giriş yapılan hesap alındı; pencere giriş için açıldıysa kapat.
    LoginDetected,
    /// Ana pencereyi öne getir (ör. varsayılan tarayıcıda giriş bitince).
    FocusMain,
    /// İlk boyama tamamlandı — ana pencereyi beyaz parlama olmadan göster.
    UiReady,
    /// Kullanıcı aktif indirmeye rağmen çıkmayı onayladı.
    ForceExit,
}

/// SoundCloud giriş, yükleme ve monetization sayfaları.
pub const SIGNIN_URL: &str = "https://soundcloud.com/signin";
pub const UPLOAD_URL: &str = "https://soundcloud.com/upload";
pub const MONETIZE_URL: &str = "https://artists.soundcloud.com/monetization/soundcloud";

/// soundcloud.com ve artists.soundcloud.com sayfalarına enjekte edilen köprü betiği:
/// 1) Giriş yapılmış hesabı algılar (`sc_user`).
/// 2) `/upload` akışında MP3 + başlık + kapak + Upload + Amplify otomasyonunu çalıştırır.
/// 3) `artists.soundcloud.com/monetization/soundcloud` üzerinde yeni & reddedilenleri gönderir.
const SC_BRIDGE_JS: &str = r##"
(function () {
  var scHost = location.hostname === "soundcloud.com" || location.hostname === "artists.soundcloud.com";
  if (!scHost || window !== window.top || !window.ipc) return;
  var lastSentKey = "";
  window.__scsLiveArtist = window.__scsLiveArtist || "";
  function report(me) {
    if (!me || !me.id) return;
    var uname = (me.username || me.full_name || "").trim();
    if (!uname) return;
    window.__scsLiveArtist = uname;
    var key = String(me.id) + ":" + uname;
    if (key === lastSentKey) return;
    lastSentKey = key;
    window.ipc.postMessage(JSON.stringify({
      type: "sc_user",
      id: String(me.id),
      username: uname,
      avatar_url: me.avatar_url || "",
      permalink_url: me.permalink_url || ""
    }));
  }
  function check() {
    try {
      var h = window.__sc_hydration;
      if (Array.isArray(h)) {
        for (var i = 0; i < h.length; i++) {
          if (h[i] && h[i].hydratable === "meUser" && h[i].data) { report(h[i].data); return; }
        }
      }
      var m = document.cookie.match(/(?:^|;\s*)oauth_token=([^;]+)/);
      if (!m) { lastSentKey = ""; window.__scsLiveArtist = ""; return; }
      fetch("https://api-v2.soundcloud.com/me", {
        headers: { Authorization: "OAuth " + decodeURIComponent(m[1]) }
      }).then(function (r) { return r.ok ? r.json() : null; })
        .then(report).catch(function () {});
    } catch (e) {}
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", check);
  else check();
  setInterval(check, 2500);

  function ensureArtistsTheme() {
    if (location.hostname !== "artists.soundcloud.com") return;
    try {
      if (window.__getDarkMode && !window.__getDarkMode() && window.__setDarkMode) {
        window.__setDarkMode(true);
      }
      var docEl = document.head || document.documentElement;
      if (docEl && !document.getElementById("scs-artists-style")) {
        var st = document.createElement("style");
        st.id = "scs-artists-style";
        st.textContent = [
          "html, body { color-scheme: dark !important; background-color: #101013 !important; }",
          "#onetrust-banner-sdk, #onetrust-consent-sdk { display: none !important; }",
          "[role=\"dialog\"] { overflow-y: auto !important; max-height: 100vh !important; }",
          "html.dark [type=\"sync\"], html.dark div[class*=\"bg-teal\"] { background-color: rgba(20, 48, 42, .45) !important; color: #d8f3ec !important; border-color: rgba(45, 180, 140, .28) !important; }"
        ].join("\n");
        docEl.appendChild(st);
      }
    } catch (e) {}
  }
  if (location.hostname === "artists.soundcloud.com") {
    ensureArtistsTheme();
    document.addEventListener("DOMContentLoaded", ensureArtistsTheme);
    var themeTries = 0;
    var themeIv = setInterval(function () {
      ensureArtistsTheme();
      themeTries++;
      if ((window.__getDarkMode && window.__getDarkMode()) || themeTries > 20) clearInterval(themeIv);
    }, 300);
  }

  function postUp(stage, active, ok, err) {
    try {
      window.ipc.postMessage(JSON.stringify({
        type: "upload_status",
        stage: stage || "",
        active: !!active,
        ok: !!ok,
        error: err || null
      }));
    } catch (e) {}
  }
  function b64ToBytes(b64) {
    var bin = atob(b64);
    var arr = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
    return arr;
  }
  function allDocs() {
    var docs = [document];
    function scan(d) {
      try {
        var frames = d.querySelectorAll("iframe");
        for (var i = 0; i < frames.length; i++) {
          try {
            var cd = frames[i].contentDocument;
            if (cd && docs.indexOf(cd) === -1) {
              docs.push(cd);
              scan(cd);
            }
          } catch (e) {}
        }
      } catch (e) {}
    }
    scan(document);
    return docs;
  }
  function findInDocs(docs, sel) {
    var out = [];
    for (var i = 0; i < docs.length; i++) {
      try {
        var nodes = docs[i].querySelectorAll(sel);
        for (var j = 0; j < nodes.length; j++) out.push(nodes[j]);
      } catch (e) {}
    }
    return out;
  }
  function setReactValue(el, val) {
    if (!el) return;
    try {
      var win = (el.ownerDocument && el.ownerDocument.defaultView) || window;
      var proto = el.tagName === "TEXTAREA" ? win.HTMLTextAreaElement.prototype : win.HTMLInputElement.prototype;
      var desc = Object.getOwnPropertyDescriptor(proto, "value");
      var tracker = el._valueTracker;
      if (tracker) tracker.setValue(val === "__scs__" ? "" : "__scs__");
      if (desc && desc.set) desc.set.call(el, val);
      else el.value = val;
      el.dispatchEvent(new win.Event("input", { bubbles: true }));
      el.dispatchEvent(new win.Event("change", { bubbles: true }));
      el.dispatchEvent(new win.FocusEvent("blur", { bubbles: true }));
    } catch (e) {}
  }
  function assignFile(input, file) {
    var win = (input.ownerDocument && input.ownerDocument.defaultView) || window;
    var dt = new win.DataTransfer();
    dt.items.add(file);
    var desc = Object.getOwnPropertyDescriptor(win.HTMLInputElement.prototype, "files");
    if (desc && desc.set) desc.set.call(input, dt.files);
    else input.files = dt.files;
    input.dispatchEvent(new win.Event("change", { bubbles: true }));
    return dt;
  }
  function findTitleInput(docs, stem) {
    var list = findInDocs(docs, "input, textarea");
    var candidates = [];
    for (var i = 0; i < list.length; i++) {
      var el = list[i];
      var ty = (el.getAttribute("type") || "text").toLowerCase();
      if (ty === "search" || ty === "file" || ty === "checkbox" || ty === "radio" || ty === "hidden") continue;
      if (el.closest('header, nav, [role="banner"], #onetrust-consent-sdk, [class*="headerSearch" i]')) continue;
      var r = el.getBoundingClientRect();
      if (r.width < 80 || r.height < 14) continue;
      candidates.push(el);
    }
    var byAttr = candidates.find(function (el) {
      var meta = [el.name, el.id, el.placeholder, el.getAttribute("aria-label"), el.getAttribute("data-testid")].join(" ").toLowerCase();
      return meta.includes("title") && !meta.includes("album");
    });
    if (byAttr) return byAttr;
    var stemLow = (stem || "").trim().toLowerCase();
    var byStem = stemLow ? candidates.find(function (el) {
      var v = (el.value || "").trim().toLowerCase();
      return v === stemLow || v.indexOf(stemLow.slice(0, Math.min(18, stemLow.length))) !== -1;
    }) : null;
    if (byStem) return byStem;
    return candidates.find(function (el) {
      var doc = el.ownerDocument || document;
      var lbl = el.id ? doc.querySelector('label[for="' + el.id + '"]') : el.closest("label");
      return lbl && /title|başlık/i.test(lbl.textContent || "");
    }) || null;
  }
  function findSubmitButton(docs) {
    var btns = findInDocs(docs, 'button, [role="button"]');
    var exact = null;
    for (var i = 0; i < btns.length; i++) {
      var b = btns[i];
      if (b.closest('header, nav, [role="banner"], #onetrust-consent-sdk')) continue;
      var r = b.getBoundingClientRect();
      if (r.width < 50 || r.height < 24) continue;
      var aria = (b.getAttribute("aria-label") || "").trim().toLowerCase();
      var txt = (b.innerText || b.textContent || "").trim().toLowerCase();
      var cls = (b.className || "").toString();
      if (/^(upload|save|publish|yükle|kaydet)$/.test(aria) || /^(upload|save|publish|yükle|kaydet)$/.test(txt)) {
        exact = b;
        if (cls.indexOf("MuiButton-contained") !== -1) return b;
      } else if (!exact && cls.indexOf("MuiButton-containedSuccess") !== -1) {
        exact = b;
      }
    }
    return exact;
  }
  function isStep1AmplifyOptedIn(docs) {
    var els = findInDocs(docs, '[name="firstFansPreEnrollments"]');
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      var aria = (el.getAttribute("aria-label") || "").toLowerCase();
      if (el.checked || aria.indexOf("remove") !== -1) return true;
    }
    return false;
  }
  function findStep1AmplifyToggle(docs) {
    var els = findInDocs(docs, '[name="firstFansPreEnrollments"]');
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      if (el.disabled || el.getAttribute("aria-disabled") === "true") continue;
      var aria = (el.getAttribute("aria-label") || "").trim().toLowerCase();
      var txt = (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim().toLowerCase();
      if (aria.indexOf("remove") !== -1 || el.checked) continue;
      if (/unlock/i.test(txt || aria)) continue;
      if (el.tagName === "INPUT" || /^amplify(\s+tracks?)?$/i.test(txt)) return el;
    }
    return null;
  }
  function isStep2AmplifyScreen(pageTxt) {
    return /next,\s*amplify|track uploaded|tracks uploaded|potential plays for your track/i.test(pageTxt || "");
  }
  function findAmplifyButton(docs, pageTxt) {
    var onStep2 = isStep2AmplifyScreen(pageTxt || bodyText(docs));
    var btns = findInDocs(docs, 'button, a, [role="button"]');
    for (var i = 0; i < btns.length; i++) {
      var b = btns[i];
      if (b.closest('header, nav, ol, [role="banner"], #onetrust-consent-sdk')) continue;
      if ((b.getAttribute("name") || "") === "firstFansPreEnrollments") continue;
      var r = b.getBoundingClientRect();
      if (r.width < 60 || r.height < 24) continue;
      var aria = (b.getAttribute("aria-label") || "").trim().toLowerCase();
      var txt = (b.innerText || b.textContent || "").replace(/\s+/g, " ").trim().toLowerCase();
      var label = txt || aria;
      if (/remove|unlock|maybe|later|learn|what is|included|not all/i.test(label)) continue;
      if (/^amplify\s+(this|these)\s+tracks?$/i.test(txt) || /^amplify\s+(this|these)\s+tracks?$/i.test(aria)) {
        return b;
      }
      if (onStep2 && (/\bamplify(\s+this\s+track|\s+these\s+tracks)?\b/i.test(txt) || /\bamplify(\s+this\s+track|\s+these\s+tracks)?\b/i.test(aria))) {
        return b;
      }
    }
    return null;
  }
  function hasSpinner(docs) {
    return findInDocs(docs, '[role="progressbar"], .MuiCircularProgress-root').length > 0;
  }
  function isAmplifyUpsell(docs, pageTxt) {
    if (pageTxt && /out\s+of\s+amplify\s+credits/i.test(pageTxt)) return true;
    var btns = findInDocs(docs, 'button, [role="button"]');
    for (var i = 0; i < btns.length; i++) {
      var t = (btns[i].innerText || btns[i].getAttribute("aria-label") || "").toLowerCase();
      if (/unlock\s+amplify|get\s+unlimited\s+credits/i.test(t)) return true;
    }
    return false;
  }
  function bodyText(docs) {
    var s = "";
    for (var i = 0; i < docs.length; i++) {
      try { if (docs[i].body) s += "\n" + (docs[i].body.innerText || ""); } catch (e) {}
    }
    return s;
  }
  function findUploadError(docs) {
    var alerts = findInDocs(docs, '[role="alert"], .MuiAlert-standardError, .MuiAlert-filledError');
    for (var i = 0; i < alerts.length; i++) {
      var t = (alerts[i].innerText || "").trim();
      if (/limit|failed|error|cannot|exceeded|already|problem amplifying/i.test(t)) return t.slice(0, 140);
    }
    return null;
  }

  window.__scsChunks = [];
  if (window.__scsUploadTimer) { clearInterval(window.__scsUploadTimer); window.__scsUploadTimer = null; }
  window.__scsResetUpload = function () {
    if (window.__scsUploadTimer) { clearInterval(window.__scsUploadTimer); window.__scsUploadTimer = null; }
    window.__scsChunks = [];
  };
  window.__scsAppendAudio = function (c) { window.__scsChunks.push(c); };
  window.__scsCommitUpload = function (filename, title, coverB64, autoSubmit, sharing, skipMonetize) {
    if (window.__scsUploadTimer) { clearInterval(window.__scsUploadTimer); window.__scsUploadTimer = null; }
    var audioB64 = window.__scsChunks.join("");
    window.__scsChunks = [];
    var audioFile = new File([b64ToBytes(audioB64)], filename, { type: "audio/mpeg" });
    var stem = (filename || "").replace(/\.[^.]+$/, "");
    var audioDone = false;
    var titleDone = !title;
    var coverDone = !coverB64;
    var privacyDone = sharing !== "private";
    var readyTicks = 0;
    var step1AmpAttempted = false;
    var step1AmpClickAt = 0;
    var step1Amplified = false;
    var submitClicked = false;
    var submitAt = 0;
    var trackUploadedAt = 0;
    var amplifyClicked = false;
    var amplifyAt = 0;
    var ampRetryClicked = false;
    var step2GoneAt = 0;
    var tries = 0;
    var lastStage = "";
    function setStage(msg, active, ok, err) {
      if (msg === lastStage && active) return;
      lastStage = msg;
      postUp(msg, active, ok, err);
    }
    function finishToMonetize(note) {
      if (window.__scsUploadTimer) {
        clearInterval(window.__scsUploadTimer);
        window.__scsUploadTimer = null;
      }
      if (skipMonetize) {
        postUp(note ? ("✓ " + note) : "✓ Yüklendi & Amplify yapıldı", false, true, null);
        return;
      }
      try {
        window.ipc.postMessage(JSON.stringify({
          type: "upload_phase_done",
          title: title || stem || "",
          note: note || ""
        }));
      } catch (e) {
        postUp(note || "✓ SoundCloud'a yüklendi!", false, true, null);
      }
    }

    setStage("Yükleme alanı hazırlanıyor...", true, false, null);

    window.__scsUploadTimer = setInterval(function () {
      tries++;
      var docs = allDocs();

      if (!audioDone) {
        if (tries > 60) {
          clearInterval(window.__scsUploadTimer);
          window.__scsUploadTimer = null;
          postUp("Yükleme alanı bulunamadı.", false, false, "SoundCloud /upload formu algılanamadı.");
          return;
        }
        var fileInputs = findInDocs(docs, 'input[type="file"]');
        var audioInput = fileInputs.find(function (el) {
          var acc = (el.getAttribute("accept") || "").toLowerCase();
          return !acc.includes("image") && el.id !== "fileInput";
        });
        if (audioInput) {
          var win = (audioInput.ownerDocument && audioInput.ownerDocument.defaultView) || window;
          var scopedAudio = new win.File([audioFile], filename, { type: "audio/mpeg" });
          assignFile(audioInput, scopedAudio);
          audioDone = true;
          setStage("MP3 aktarılıyor, başlık & kapak ekleniyor...", true, false, null);
        } else if (tries > 20) {
          var txt = bodyText(docs);
          if (location.pathname.indexOf("signin") !== -1 || /sign in to|create a soundcloud account/i.test(txt)) {
            clearInterval(window.__scsUploadTimer);
            window.__scsUploadTimer = null;
            postUp("", false, false, "SoundCloud hesabına giriş yapılmamış — giriş yapıp tekrar dene.");
          }
        }
        return;
      }

      if (!submitClicked) {
        if (!titleDone && title) {
          var titleEl = findTitleInput(docs, stem);
          if (titleEl) {
            if ((titleEl.value || "").trim() !== title.trim()) {
              setReactValue(titleEl, title);
            }
            if ((titleEl.value || "").trim() === title.trim()) titleDone = true;
          }
        }

        if (!coverDone && coverB64) {
          var imgInput = findInDocs(docs, 'input[data-testid="file-input"], input#fileInput[type="file"], input[type="file"][accept*="image"]')[0];
          if (imgInput) {
            var iwin = (imgInput.ownerDocument && imgInput.ownerDocument.defaultView) || window;
            var coverFile = new iwin.File([b64ToBytes(coverB64)], "cover.jpg", { type: "image/jpeg" });
            assignFile(imgInput, coverFile);
            coverDone = true;
          }
        }

        if (!privacyDone) {
          var radios = findInDocs(docs, 'input[type="radio"]');
          var priv = radios.find(function (r) {
            var lbl = (r.value || "") + " " + ((r.closest("label") && r.closest("label").textContent) || "");
            return /private/i.test(lbl);
          });
          if (priv) {
            if (!priv.checked) priv.click();
            privacyDone = true;
          }
        }

        var upErr = findUploadError(docs);
        if (upErr) {
          clearInterval(window.__scsUploadTimer);
          window.__scsUploadTimer = null;
          postUp("", false, false, upErr);
          return;
        }

        if (titleDone && coverDone) {
          if (sharing !== "private" && !isAmplifyUpsell(docs, "")) {
            if (isStep1AmplifyOptedIn(docs)) {
              step1Amplified = true;
            } else if (!step1AmpAttempted && readyTicks >= 1) {
              var preEl = findStep1AmplifyToggle(docs);
              if (preEl) {
                try { preEl.click(); } catch (e) {}
                step1AmpAttempted = true;
                step1AmpClickAt = tries;
              }
            }
          }
          readyTicks++;
          if (!autoSubmit && readyTicks >= 2) {
            clearInterval(window.__scsUploadTimer);
            window.__scsUploadTimer = null;
            setStage("✓ MP3, başlık ve kapak eklendi — Upload'a basarak yayınlayın.", false, true, null);
            return;
          }
          var step1AmpSettled = !step1AmpAttempted || step1Amplified || (tries - step1AmpClickAt >= 2);
          var submitBtn = findSubmitButton(docs);
          if (autoSubmit && readyTicks >= 3 && step1AmpSettled && submitBtn) {
            var isDisabled = !!submitBtn.disabled || submitBtn.getAttribute("aria-disabled") === "true";
            if (!isDisabled) {
              submitBtn.click();
              submitClicked = true;
              submitAt = tries;
              setStage("SoundCloud'a kaydediliyor ve yayınlanıyor...", true, false, null);
              return;
            }
            setStage("Ses işleniyor, hazır olunca otomatik yayınlanacak...", true, false, null);
          } else {
            setStage("Form hazırlanıyor...", true, false, null);
          }
        }

        if (tries > 240) {
          clearInterval(window.__scsUploadTimer);
          window.__scsUploadTimer = null;
          postUp("", false, false, "Yükleme formu zaman aşımına uğradı — Upload butonunu kontrol et.");
        }
        return;
      }

      var errAfter = findUploadError(docs);
      if (errAfter) {
        if (amplifyClicked || trackUploadedAt) {
          finishToMonetize("Yüklendi (Amplify: " + errAfter + ")");
        } else {
          clearInterval(window.__scsUploadTimer);
          window.__scsUploadTimer = null;
          postUp("", false, false, errAfter);
        }
        return;
      }
      var pageTxt = bodyText(docs);
      var leftUpload = location.pathname.indexOf("/upload") === -1;
      if (leftUpload) {
        finishToMonetize((amplifyClicked || step1Amplified) ? "Yüklendi & Amplify yapıldı" : "Yüklendi");
        return;
      }

      if (!amplifyClicked) {
        var ampBtn = findAmplifyButton(docs, pageTxt);
        if (ampBtn) {
          var ampDisabled = !!ampBtn.disabled || ampBtn.getAttribute("aria-disabled") === "true";
          if (!ampDisabled) {
            try { ampBtn.scrollIntoView && ampBtn.scrollIntoView({ block: "center" }); } catch (e) {}
            ampBtn.click();
            amplifyClicked = true;
            amplifyAt = tries;
            setStage("Parça yüklendi — Amplify uygulanıyor...", true, false, null);
          } else {
            setStage("Parça yüklendi — Amplify hazırlanıyor...", true, false, null);
          }
          return;
        }
        if (isStep2AmplifyScreen(pageTxt) && isAmplifyUpsell(docs, pageTxt)) {
          finishToMonetize("Yüklendi (Amplify kredisi / planı yok)");
          return;
        }
        if (/track uploaded|tracks uploaded|saved to soundcloud/i.test(pageTxt)) {
          if (!trackUploadedAt) trackUploadedAt = tries;
          if (/we['’]ll analyze|analyzing your track/i.test(pageTxt)) {
            finishToMonetize("Yüklendi & Amplify ön başvurusu yapıldı");
            return;
          }
          var settleTicks = step1Amplified ? 6 : 12;
          if (tries - trackUploadedAt >= settleTicks && !isStep2AmplifyScreen(pageTxt)) {
            finishToMonetize(step1Amplified ? "Yüklendi & Amplify ön başvurusu yapıldı" : "Yüklendi");
            return;
          }
          setStage(step1Amplified ? "Parça yüklendi — Amplify doğrulanıyor..." : "Parça yüklendi — Amplify bekleniyor...", true, false, null);
          return;
        }
        var stillUploading = /uploading your files|saving\.\.\.|transcod/i.test(pageTxt) || hasSpinner(docs);
        if (tries - submitAt > (stillUploading ? 240 : 120)) {
          finishToMonetize("Yükleme gönderildi");
        }
        return;
      }

      var spinning = hasSpinner(docs);
      var ampStillBtn = findAmplifyButton(docs, pageTxt);
      var ampStillDisabled = !!ampStillBtn && (!!ampStillBtn.disabled || ampStillBtn.getAttribute("aria-disabled") === "true");
      if (ampStillBtn && !ampStillDisabled && !spinning && !ampRetryClicked && tries - amplifyAt >= 3 && tries - amplifyAt <= 10) {
        try { ampStillBtn.scrollIntoView && ampStillBtn.scrollIntoView({ block: "center" }); } catch (e) {}
        ampStillBtn.click();
        ampRetryClicked = true;
        return;
      }
      var ampDoneTxt = /we['’]ll analyze|amplified|already amplified|analyzing your track/i.test(pageTxt);
      var step2Gone = !ampStillBtn && !/next,\s*amplify/i.test(pageTxt) && !/maybe later/i.test(pageTxt);
      var savedVisible = /saved to soundcloud|view track|view album/i.test(pageTxt);
      if (step2Gone || ampDoneTxt) {
        if (!step2GoneAt) step2GoneAt = tries;
      } else {
        step2GoneAt = 0;
      }
      if (!spinning && (ampDoneTxt || (step2Gone && savedVisible && tries - step2GoneAt >= 3) || (step2Gone && tries - amplifyAt >= 6))) {
        finishToMonetize("Yüklendi & Amplify yapıldı");
        return;
      }
      if (tries - amplifyAt > 36) {
        finishToMonetize(step2Gone ? "Yüklendi & Amplify yapıldı" : "Yüklendi (Amplify zaman aşımı)");
      }
    }, 450);
  };

  if (window.__scsMonetizeTimer) { clearInterval(window.__scsMonetizeTimer); window.__scsMonetizeTimer = null; }
  window.__scsStartMonetize = function (targetTitle, resubmitRejected, submitUnsubmitted, artistHint, introNote) {
    if (window.__scsMonetizeTimer) { clearInterval(window.__scsMonetizeTimer); window.__scsMonetizeTimer = null; }
    var norm = function (s) {
      return (s || "").toLowerCase().replace(/\s+/g, " ").trim();
    };
    var targetNorm = norm(targetTitle);
    var targetHandled = !targetNorm;
    var attempted = {};
    var resubmitted = 0;
    var submitted = 0;
    var failed = 0;
    var scrollRounds = 0;
    var waitLoadTicks = 0;
    var syncWaitTicks = 0;
    var searchNudged = false;
    var activeModal = null;
    var liveArtist = window.__scsLiveArtist || "";
    var lastHeight = 0;
    var waitMoreTicks = 0;
    var tries = 0;
    var lastStage = "";
    try {
      var mTok = document.cookie.match(/(?:^|;\s*)oauth_token=([^;]+)/);
      if (mTok) {
        fetch("https://api-v2.soundcloud.com/me", {
          headers: { Authorization: "OAuth " + decodeURIComponent(mTok[1]) }
        }).then(function (r) { return r.ok ? r.json() : null; }).then(function (me) {
          var u = me && (me.username || me.full_name || "").trim();
          if (u) {
            liveArtist = u;
            window.__scsLiveArtist = u;
            report(me);
          }
        }).catch(function () {});
      }
    } catch (e) {}
    function setStage(msg) {
      if (msg === lastStage) return;
      lastStage = msg;
      postUp(msg, true, false, null);
    }
    function finishMon(msg, ok, err) {
      if (window.__scsMonetizeTimer) {
        clearInterval(window.__scsMonetizeTimer);
        window.__scsMonetizeTimer = null;
      }
      window.scrollTo(0, 0);
      postUp(msg, false, ok, err || null);
    }
    function findModal() {
      var dialogs = document.querySelectorAll('[role="dialog"], form');
      for (var i = 0; i < dialogs.length; i++) {
        var d = dialogs[i];
        var txt = d.innerText || "";
        if (d.querySelector('input[name="monetizeRightsConfirmed"]') ||
            (/have the rights to monetize this track/i.test(txt) && d.querySelector('button[type="submit"]')) ||
            /submit your request now|complete these one-time steps/i.test(txt)) {
          return d;
        }
      }
      return null;
    }
    function collectRows() {
      var out = [];
      var btns = document.querySelectorAll("button");
      for (var i = 0; i < btns.length; i++) {
        var b = btns[i];
        if (b.getAttribute("data-scs-done") === "1") continue;
        var bt = (b.innerText || b.textContent || "").replace(/\s+/g, " ").trim();
        var isRej = /^resubmit this track$/i.test(bt);
        var isNew = /^monetize this track$/i.test(bt);
        if (!isRej && !isNew) continue;
        var row = b.closest('div[class*="odd:bg-highlight"]') || b.closest("div.w-full") || b.parentElement;
        var titleEl = row ? (row.querySelector("span[title]") || row.querySelector('a[href*="/tracks/soundcloud/"]')) : null;
        var titleTxt = titleEl ? (titleEl.getAttribute("title") || titleEl.innerText || "") : "";
        if (!titleTxt && row) {
          var bold = row.querySelector(".font-bold");
          if (bold) titleTxt = bold.innerText || "";
        }
        var artistEl = row ? row.querySelector("span.text-secondary.block, span.text-secondary") : null;
        var artistTxt = artistEl ? (artistEl.innerText || artistEl.textContent || "").trim() : "";
        if (/^(added|public|private|rejected|eligible|monetiz|in review)$/i.test(artistTxt)) artistTxt = "";
        out.push({ btn: b, title: titleTxt.trim(), normTitle: norm(titleTxt), artist: artistTxt, isRejected: isRej, isNew: isNew });
      }
      return out;
    }
    function countMonetizeStates() {
      var txt = (document.body && document.body.innerText) || "";
      var rej = 0;
      var newEligible = 0;
      var btns = document.querySelectorAll("button");
      for (var i = 0; i < btns.length; i++) {
        var bt = (btns[i].innerText || "").trim();
        if (/^resubmit this track$/i.test(bt)) rej++;
        else if (/^monetize this track$/i.test(bt)) newEligible++;
      }
      var inRev = (txt.match(/Cancel Monetization/gi) || []).length;
      return { rej: rej, newEligible: newEligible, inReview: inRev };
    }
    function buildSummary() {
      var st = countMonetizeStates();
      var parts = [];
      if (introNote) parts.push(introNote);
      if (submitted > 0) parts.push(submitted + " yeni monetize başvurusu gönderildi");
      if (resubmitted > 0) parts.push(resubmitted + " reddedilen tekrar gönderildi");
      if (submitted === 0 && resubmitted === 0) {
        parts.push("Monetize kontrol edildi (bekleyen/reddedilen açık başvuru yok, " + st.inReview + " incelemede)");
      } else if (st.rej > 0 || failed > 0) {
        parts.push(failed + " satır atlandı");
      }
      return "✓ " + parts.join(" · ");
    }

    setStage((introNote ? introNote + " — " : "") + "Monetize listesi yükleniyor...");

    window.__scsMonetizeTimer = setInterval(function () {
      tries++;
      if (tries > 400) {
        finishMon(buildSummary(), true, null);
        return;
      }

      var bodyTxt = (document.body && document.body.innerText) || "";
      if (location.hostname !== "artists.soundcloud.com") {
        if (/sign in|log in|create an account/i.test(bodyTxt) || location.pathname.indexOf("signin") !== -1) {
          finishMon("", false, "artists.soundcloud.com oturumu kapalı — önce giriş yap.");
        }
        return;
      }

      if (/get paid for your plays on soundcloud/i.test(bodyTxt) && document.querySelector('a, button') && /get started/i.test(bodyTxt) && !document.querySelector('input[placeholder*="Search for tracks" i]')) {
        finishMon("✓ " + (introNote ? introNote + " · " : "") + "Bu hesapta Monetization planı etkin değil.", true, null);
        return;
      }

      var searchInp = document.querySelector('input[placeholder*="Search for tracks" i]');
      var hasRows = /Monetize this track|Resubmit this track|Cancel Monetization|No tracks found/i.test(bodyTxt);
      if (!searchInp || (!hasRows && waitLoadTicks < 28)) {
        waitLoadTicks++;
        return;
      }

      // 1. Açık Monetize modalını yönet
      var modal = findModal();
      if (activeModal) {
        if (!modal) {
          if (activeModal.submitted) {
            if (activeModal.isRejected) resubmitted++;
            else submitted++;
            setStage("Monetize gönderildi (" + (submitted + resubmitted) + "): " + (activeModal.title || "Parça"));
          }
          activeModal = null;
          return;
        }
        var mTxt = modal.innerText || "";
        if (/first request is still pending approval|once your first monetization request is approved/i.test(mTxt)) {
          var cancelB = Array.from(modal.querySelectorAll('button')).find(function (b) { return /^cancel$/i.test((b.innerText || "").trim()); });
          if (cancelB) cancelB.click();
          finishMon("✓ " + (submitted + resubmitted) + " gönderildi (İlk başvuru onay beklediği için sıradakiler bekletildi).", true, null);
          return;
        }
        if (/complete these one-time steps/i.test(mTxt)) {
          finishMon("", false, "Monetize öncesi ödeme/hesap doğrulama adımlarını tamamla.");
          return;
        }

        activeModal.ticks++;
        if (activeModal.submitted) {
          if (/already monetiz|error submitting|not eligible/i.test(mTxt) && activeModal.ticks - activeModal.submitAt > 6) {
            var cancelErr = Array.from(modal.querySelectorAll('button')).find(function (b) { return /^cancel$/i.test((b.innerText || "").trim()); });
            if (cancelErr) cancelErr.click();
            failed++;
            activeModal = null;
            return;
          }
          if (activeModal.ticks - activeModal.submitAt > 45) {
            var cancelTimeout = Array.from(modal.querySelectorAll('button')).find(function (b) { return /^cancel$/i.test((b.innerText || "").trim()); });
            if (cancelTimeout) cancelTimeout.click();
            failed++;
            activeModal = null;
          }
          return;
        }

        ensureArtistsTheme();
        var changedThisTick = false;

        // Contributors / Songwriters boş ise giriş yapan kullanıcının adını dinamik yaz
        var nameInputs = modal.querySelectorAll('input[name^="contributors."][name$=".name"], input[name^="songwriters."][name$=".name"]');
        var existingArtist = "";
        for (var ei = 0; ei < nameInputs.length; ei++) {
          var ev = (nameInputs[ei].value || "").trim();
          if (ev) { existingArtist = ev; break; }
        }
        var resolvedArtist = (
          existingArtist ||
          (activeModal && activeModal.artist) ||
          liveArtist ||
          window.__scsLiveArtist ||
          artistHint ||
          ""
        ).trim();
        var hasEmptyName = false;
        for (var ci = 0; ci < nameInputs.length; ci++) {
          if (!(nameInputs[ci].value || "").trim()) { hasEmptyName = true; break; }
        }
        if (hasEmptyName && !resolvedArtist) {
          if (activeModal.ticks < 8) return;
          resolvedArtist = "Artist";
        }
        for (var ni = 0; ni < nameInputs.length; ni++) {
          if (!(nameInputs[ni].value || "").trim()) {
            setReactValue(nameInputs[ni], resolvedArtist);
            changedThisTick = true;
          }
        }

        // Content rating "Select content rating" ise "Not Explicit" seç
        var optOpen = document.querySelector('[role="option"]');
        if (optOpen) {
          var opts = document.querySelectorAll('[role="option"]');
          for (var oi = 0; oi < opts.length; oi++) {
            if (/^not explicit$/i.test((opts[oi].innerText || "").trim())) {
              opts[oi].click();
              break;
            }
          }
          return;
        }
        var ratingBtn = Array.from(modal.querySelectorAll("button")).find(function (b) {
          return /select content rating/i.test((b.innerText || "").trim());
        });
        if (ratingBtn) {
          ratingBtn.click();
          return;
        }

        // Songwriter seçili değilse "Another artist/writer wrote the song" (value="false") seç
        var swRadios = Array.from(modal.querySelectorAll('input[type="radio"][name="songwriter"]'));
        if (swRadios.length && !swRadios.some(function (r) { return r.checked; })) {
          var nonSw = swRadios.find(function (r) { return r.value === "false"; }) || swRadios[0];
          nonSw.click();
          if (!nonSw.checked && nonSw.parentElement) nonSw.parentElement.click();
          changedThisTick = true;
        }

        // ISRC seçili değilse "No" seç
        var otherRadios = Array.from(modal.querySelectorAll('input[type="radio"]')).filter(function (r) {
          return r.name !== "songwriter";
        });
        if (otherRadios.length && !otherRadios.some(function (r) { return r.checked; })) {
          var noIsrc = otherRadios.find(function (r) {
            var wrapTxt = (r.parentElement && r.parentElement.innerText) || "";
            return r.value === "false" || /^no$/i.test(wrapTxt.trim()) || /\bno\b/i.test(wrapTxt);
          });
          if (noIsrc) {
            noIsrc.click();
            if (!noIsrc.checked && noIsrc.parentElement) noIsrc.parentElement.click();
            changedThisTick = true;
          }
        }

        // "I have the rights to monetize this track" kutusunu işaretle
        var cb = modal.querySelector('input[type="checkbox"][name="monetizeRightsConfirmed"]');
        if (!cb) {
          cb = Array.from(modal.querySelectorAll('input[type="checkbox"]')).find(function (c) {
            var l = (c.closest("label") || c.parentElement || {}).innerText || "";
            return /rights to monetize/i.test(l);
          });
        }
        if (cb && !cb.checked) {
          cb.click();
          if (!cb.checked && cb.parentElement) cb.parentElement.click();
          changedThisTick = true;
        }

        if (changedThisTick) return;

        var submitBtn = modal.querySelector('button[type="submit"]');
        if (activeModal.ticks >= 2 && submitBtn && !submitBtn.disabled) {
          submitBtn.click();
          activeModal.submitted = true;
          activeModal.submitAt = activeModal.ticks;
          setStage((activeModal.isRejected ? "Tekrar başvuruluyor: " : "Monetize gönderiliyor: ") + (activeModal.title || "Parça"));
        } else if (activeModal.ticks > 30) {
          var cancelSlow = Array.from(modal.querySelectorAll('button')).find(function (b) { return /^cancel$/i.test((b.innerText || "").trim()); });
          if (cancelSlow) cancelSlow.click();
          failed++;
          activeModal = null;
        }
        return;
      }

      // 2. Yeni yüklenen hedef parçayı bekle / bul
      var rows = collectRows();
      var nextRow = null;

      if (!targetHandled && targetNorm) {
        var shortTarget = targetNorm.slice(0, Math.min(22, targetNorm.length));
        nextRow = rows.find(function (r) {
          return r.normTitle === targetNorm || r.normTitle.indexOf(shortTarget) !== -1 || targetNorm.indexOf(r.normTitle) !== -1;
        });
        if (!nextRow) {
          var inDom = Array.from(document.querySelectorAll("span[title]")).some(function (s) {
            var nt = norm(s.getAttribute("title") || "");
            return nt === targetNorm || nt.indexOf(shortTarget) !== -1;
          });
          if (inDom) {
            targetHandled = true;
          } else {
            syncWaitTicks++;
            if (syncWaitTicks === 10 && !searchNudged && searchInp) {
              searchNudged = true;
              setReactValue(searchInp, " ");
              setTimeout(function () { setReactValue(searchInp, ""); }, 250);
            }
            if (syncWaitTicks < 20) {
              setStage("Yeni parça Monetize listesinde bekleniyor...");
              return;
            }
            targetHandled = true;
          }
        } else {
          targetHandled = true;
        }
      }

      // 3. Reddedilenleri (Resubmit) veya yeni uygunları (Monetize) sırayla işle
      if (!nextRow && resubmitRejected) {
        nextRow = rows.find(function (r) { return r.isRejected; });
      }
      if (!nextRow && submitUnsubmitted) {
        nextRow = rows.find(function (r) { return r.isNew; });
      }

      if (nextRow) {
        waitMoreTicks = 0;
        nextRow.btn.setAttribute("data-scs-done", "1");
        nextRow.btn.scrollIntoView({ block: "center" });
        nextRow.btn.click();
        activeModal = {
          title: nextRow.title,
          artist: nextRow.artist || "",
          isRejected: nextRow.isRejected,
          ticks: 0,
          submitted: false,
          submitAt: 0
        };
        setStage((nextRow.isRejected ? "Reddedilen açılıyor: " : "Başvuru açılıyor: ") + (nextRow.title || "Parça"));
        return;
      }

      // 4. Alt satırları yüklemek için gerekirse aşağı kaydır
      if ((resubmitRejected || submitUnsubmitted) && scrollRounds < 12) {
        var curH = document.body.scrollHeight;
        if (window.scrollY + window.innerHeight + 120 < curH || waitMoreTicks < 6) {
          if (curH !== lastHeight || waitMoreTicks === 0) {
            lastHeight = curH;
            window.scrollTo(0, curH);
            scrollRounds++;
          }
          waitMoreTicks++;
          setStage("Diğer parçalar kontrol ediliyor...");
          return;
        }
      }

      finishMon(buildSummary(), true, null);
    }, 450);
  };
})();
"##;

/// Tarayıcıdan gelen hesap ve yükleme bildirimlerini işler.
fn handle_ipc(state: &crate::state::AppState, page: &str, body: &str) {
    use std::sync::atomic::Ordering;

    let from_sc = page.starts_with("https://soundcloud.com/")
        || page == "https://soundcloud.com"
        || page.starts_with("https://artists.soundcloud.com/")
        || page == "https://artists.soundcloud.com";
    if !from_sc {
        return;
    }
    let Ok(v) = serde_json::from_str::<serde_json::Value>(body) else {
        return;
    };
    let msg_type = v.get("type").and_then(|t| t.as_str()).unwrap_or("");

    if msg_type == "upload_status" {
        let mut st = state.upload_status.blocking_write();
        st.active = v.get("active").and_then(|x| x.as_bool()).unwrap_or(false);
        st.ok = v.get("ok").and_then(|x| x.as_bool()).unwrap_or(false);
        st.stage = v.get("stage").and_then(|x| x.as_str()).unwrap_or("").to_string();
        st.error = v.get("error").and_then(|x| x.as_str()).map(str::to_string);
        return;
    }

    if msg_type == "upload_phase_done" {
        let title = v.get("title").and_then(|x| x.as_str()).unwrap_or("").trim().to_string();
        let note = v.get("note").and_then(|x| x.as_str()).unwrap_or("").trim().to_string();
        let artist_hint = state.auth.blocking_read().username.clone();
        {
            let mut st = state.upload_status.blocking_write();
            st.active = true;
            st.ok = false;
            st.error = None;
            st.stage = if note.is_empty() {
                "Monetize sayfasına geçiliyor...".into()
            } else {
                format!("{note} — Monetize başvurusuna geçiliyor...")
            };
        }
        let job = MonetizeJob {
            target_title: if title.is_empty() { None } else { Some(title) },
            resubmit_rejected: true,
            submit_unsubmitted: true,
            artist_hint,
            intro_note: note,
        };
        if let Ok(slot) = state.ui_tx.lock() {
            if let Some(proxy) = slot.as_ref() {
                let _ = proxy.send_event(UiEvent::ScStartMonetize(job));
            }
        }
        return;
    }

    if msg_type != "sc_user" {
        return;
    }
    let was_pending = state.login_pending.load(Ordering::SeqCst);
    let s = |k: &str| v.get(k).and_then(|x| x.as_str()).unwrap_or("").trim().to_string();
    let (id, username) = (s("id"), s("username"));
    if id.is_empty() || username.is_empty() {
        return;
    }

    let browser_is_open = state.browser_open.load(Ordering::Relaxed);
    let should_update = {
        let cur = state.auth.blocking_read();
        let allowed = was_pending
            || !cur.username.is_empty()
            || browser_is_open;
        let can_write = allowed && (was_pending || cur.web_session || cur.username.is_empty() || cur.user_id == id);
        can_write && (was_pending || cur.user_id != id || cur.username != username)
    };
    if !should_update {
        return;
    }

    let auth = {
        let mut cur = state.auth.blocking_write();
        if cur.user_id != id {
            // Başka bir hesaba geçildi: önceki hesabın API belirteçleri bu kimliğe ait değil.
            cur.access_token.clear();
            cur.refresh_token.clear();
            cur.expires_at = 0;
        }
        cur.user_id = id;
        cur.username = username;
        let av = s("avatar_url");
        if !av.is_empty() {
            cur.avatar_url = av;
        }
        let pm = s("permalink_url");
        if !pm.is_empty() {
            cur.permalink_url = pm;
        }
        if cur.access_token.is_empty() {
            cur.web_session = true;
        }
        cur.clone()
    };
    let _ = crate::auth::save(&auth);

    if was_pending {
        state.login_pending.store(false, Ordering::SeqCst);
        if let Ok(slot) = state.ui_tx.lock() {
            if let Some(proxy) = slot.as_ref() {
                let _ = proxy.send_event(UiEvent::LoginDetected);
            }
        }
    }
}

pub fn run(port: u16, state: Arc<crate::state::AppState>) -> ! {
    use std::sync::atomic::Ordering;

    let event_loop = EventLoopBuilder::<UiEvent>::with_user_event().build();

    // HTTP katmanı bu proxy üzerinden pencere açtırabiliyor.
    if let Ok(mut slot) = state.ui_tx.lock() {
        *slot = Some(event_loop.create_proxy());
    }

    let (initial_size, initial_pos, want_maximize) = initial_window_geometry(&event_loop, &state);

    let mut wb = WindowBuilder::new()
        .with_title("SC Studio")
        .with_inner_size(initial_size)
        .with_min_inner_size(Size::Physical(PhysicalSize::new(1000, 620)))
        .with_visible(false);
    if let Some(pos) = initial_pos {
        wb = wb.with_position(pos);
    }

    let main_window = match wb.build(&event_loop) {
        Ok(w) => w,
        Err(e) => {
            crate::winmsg::message_box(
                "SC Studio",
                &format!("Pencere oluşturulamadı:\n{e}"),
                true,
            );
            std::process::exit(1);
        }
    };

    if let Some(icon) = load_icon() {
        main_window.set_window_icon(Some(icon));
    }

    let main_hwnd = hwnd_of(&main_window);
    state.main_hwnd.store(main_hwnd, Ordering::Relaxed);
    crate::winmsg::style_dark_window(main_hwnd);

    let main_id = main_window.id();
    let url = format!("http://127.0.0.1:{}/", port);

    // WebView2 veri klasörü exe'nin yanında değil %APPDATA%'da olsun.
    let data_dir = crate::paths::data_dir().join("WebView2");
    let _ = crate::paths::ensure_dir(&data_dir);
    let mut web_context = wry::WebContext::new(Some(data_dir));

    let ipc_state = Arc::clone(&state);
    let main_webview = WebViewBuilder::new_with_web_context(&mut web_context)
        .with_url(&url)
        .with_ipc_handler(move |req| {
            let Ok(v) = serde_json::from_str::<serde_json::Value>(req.body()) else {
                return;
            };
            let kind = v.get("type").and_then(|t| t.as_str()).unwrap_or("");
            if let Ok(slot) = ipc_state.ui_tx.lock() {
                if let Some(proxy) = slot.as_ref() {
                    match kind {
                        "ui_ready" => {
                            let _ = proxy.send_event(UiEvent::UiReady);
                        }
                        "confirm_exit" => {
                            let _ = proxy.send_event(UiEvent::ForceExit);
                        }
                        "sc_view" => {
                            let visible = v.get("visible").and_then(|x| x.as_bool()).unwrap_or(false);
                            let x = v.get("x").and_then(|n| n.as_f64()).unwrap_or(214.0);
                            let y = v.get("y").and_then(|n| n.as_f64()).unwrap_or(48.0);
                            let w = v.get("w").and_then(|n| n.as_f64()).unwrap_or(800.0);
                            let h = v.get("h").and_then(|n| n.as_f64()).unwrap_or(600.0);
                            let _ = proxy.send_event(UiEvent::ScBounds { visible, x, y, w, h });
                        }
                        _ => {}
                    }
                }
            }
        })
        .with_devtools(cfg!(debug_assertions))
        .with_background_color((10, 10, 12, 255))
        .build(&main_window);

    let main_webview = match main_webview {
        Ok(wv) => wv,
        Err(e) => {
            crate::winmsg::message_box(
                "SC Studio — WebView2",
                &format!(
                    "Arayüz başlatılamadı.\n\n{e}\n\n\
                     Microsoft Edge WebView2 çalışma zamanı eksik olabilir:\n\
                     https://developer.microsoft.com/microsoft-edge/webview2/"
                ),
                true,
            );
            std::process::exit(1);
        }
    };

    let mut browser: Option<(Window, WebView)> = None;
    let mut sc_webview: Option<WebView> = None;
    let mut sc_visible = false;
    let mut sc_bounds: Option<(f64, f64, f64, f64)> = None;
    let mut upload_seq: u64 = 0;
    let mut pending_upload: Option<(UploadJob, u64, Option<Instant>)> = None;
    let mut monetize_seq: u64 = 0;
    let mut pending_monetize: Option<(MonetizeJob, u64, Option<Instant>)> = None;
    let mut auth_wall_since: Option<Instant> = None;
    // Tarayıcı penceresi giriş için mi açıldı? (Giriş bitince kendiliğinden kapanır.)
    let mut opened_for_login = false;
    // "Hesap ekle" sırasında oturumu kapatılan önceki hesap (iptal edilirse geri yüklenir).
    let mut pending_add_prev: Option<String> = None;
    let mut main_shown = false;
    let boot_at = Instant::now();
    let mut exit_prompt_at: Option<Instant> = None;

    event_loop.run(move |event, target, control_flow| {
        let show_main_now = |shown: &mut bool| {
            if *shown {
                return;
            }
            *shown = true;
            crate::winmsg::style_dark_window(main_hwnd);
            if want_maximize {
                main_window.set_maximized(true);
            }
            main_window.set_visible(true);
            main_window.set_focus();
        };

        // web_context bu closure'a ait; tüm webview'lar aynı profili paylaşıyor.
        match event {
            Event::WindowEvent {
                window_id,
                event: WindowEvent::CloseRequested,
                ..
            } => {
                if window_id == main_id {
                    let downloading = state
                        .curator
                        .try_read()
                        .map(|c| c.downloading)
                        .unwrap_or(false);

                    let second_click = exit_prompt_at
                        .map(|t| t.elapsed() < Duration::from_secs(4))
                        .unwrap_or(false);

                    if !downloading || second_click {
                        save_window_state(&main_window, &state);
                        browser = None;
                        sc_webview = None;
                        state.browser_open.store(false, Ordering::Relaxed);
                        cleanup_on_exit(&state);
                        *control_flow = ControlFlow::Exit;
                        return;
                    }

                    // İndirme aktif: kullanıcıya zarif kapatma onayı göster.
                    exit_prompt_at = Some(Instant::now());
                    main_window.set_minimized(false);
                    main_window.set_focus();
                    let _ = main_webview.evaluate_script(
                        "window.__scConfirmExit && window.__scConfirmExit()",
                    );
                } else {
                    // Tarayıcı penceresi kapatıldı; bekleyen giriş de iptal, eski adres temizlensin.
                    let was_pending = state.login_pending.swap(false, Ordering::SeqCst);
                    browser = None;
                    opened_for_login = false;
                    if was_pending {
                        if let Some(prev) = pending_add_prev.take() {
                            // Yeni hesap eklenmeden pencere kapandı: önceki hesabın oturumunu geri yükle.
                            if !restore_account_session(&state, &main_webview, sc_webview.as_ref(), &prev) {
                                *state.auth.blocking_write() = Default::default();
                                let _ = crate::auth::clear();
                            }
                        }
                    }
                    if !sc_visible {
                        state.browser_open.store(false, Ordering::Relaxed);
                    }
                    if let Ok(mut u) = state.browser_url.lock() {
                        u.clear();
                    }
                }
            }

            Event::WindowEvent {
                window_id,
                event: WindowEvent::Resized(_) | WindowEvent::ScaleFactorChanged { .. },
                ..
            } => {
                if window_id == main_id && sc_visible {
                    let _ = main_webview.evaluate_script(
                        "window.syncScWebviewBounds && window.syncScWebviewBounds()",
                    );
                }
            }

            Event::UserEvent(UiEvent::UiReady) => {
                show_main_now(&mut main_shown);
            }

            Event::UserEvent(UiEvent::ForceExit) => {
                save_window_state(&main_window, &state);
                browser = None;
                sc_webview = None;
                state.browser_open.store(false, Ordering::Relaxed);
                cleanup_on_exit(&state);
                *control_flow = ControlFlow::Exit;
                return;
            }

            Event::UserEvent(UiEvent::ScBounds { visible, x, y, w, h }) => {
                sc_visible = visible;
                if w >= 80.0 && h >= 80.0 {
                    sc_bounds = Some((x, y, w, h));
                }
                if visible && sc_webview.is_none() {
                    let rect = make_rect(sc_bounds.unwrap_or((214.0, 48.0, 960.0, 700.0)));
                    sc_webview = create_sc_child_webview(
                        &main_window,
                        &mut web_context,
                        "https://soundcloud.com/discover",
                        rect,
                        Arc::clone(&state),
                    );
                }
                if let Some(wv) = sc_webview.as_ref() {
                    if let Some(b) = sc_bounds {
                        let _ = wv.set_bounds(make_rect(b));
                    }
                    let _ = wv.set_visible(visible);
                }
                state
                    .browser_open
                    .store(visible || browser.is_some(), Ordering::Relaxed);
            }

            Event::UserEvent(UiEvent::ScNavigate(cmd)) => {
                if sc_webview.is_none() {
                    let start = if cmd.starts_with("https://") {
                        cmd.as_str()
                    } else {
                        "https://soundcloud.com/discover"
                    };
                    let rect = make_rect(sc_bounds.unwrap_or((214.0, 48.0, 960.0, 700.0)));
                    sc_webview = create_sc_child_webview(
                        &main_window,
                        &mut web_context,
                        start,
                        rect,
                        Arc::clone(&state),
                    );
                    if let Some(wv) = sc_webview.as_ref() {
                        let _ = wv.set_visible(sc_visible);
                    }
                } else if let Some(wv) = sc_webview.as_ref() {
                    match cmd.as_str() {
                        "back" => { let _ = wv.evaluate_script("history.back()"); }
                        "forward" => { let _ = wv.evaluate_script("history.forward()"); }
                        "reload" => { let _ = wv.evaluate_script("location.reload()"); }
                        url if url.starts_with("https://") => { let _ = wv.load_url(url); }
                        _ => {}
                    }
                }
            }

            Event::UserEvent(UiEvent::ScInjectUpload(job)) => {
                pending_monetize = None;
                upload_seq += 1;
                let fresh_url = format!("{UPLOAD_URL}?scs={upload_seq}");
                if sc_webview.is_none() {
                    let rect = make_rect(sc_bounds.unwrap_or((214.0, 48.0, 960.0, 700.0)));
                    sc_webview = create_sc_child_webview(
                        &main_window,
                        &mut web_context,
                        &fresh_url,
                        rect,
                        Arc::clone(&state),
                    );
                    if let Some(wv) = sc_webview.as_ref() {
                        let _ = wv.set_visible(sc_visible);
                    }
                    pending_upload = Some((job, upload_seq, None));
                } else if let Some(wv) = sc_webview.as_ref() {
                    let _ = wv.load_url(&fresh_url);
                    pending_upload = Some((job, upload_seq, None));
                }
            }

            Event::UserEvent(UiEvent::ScCancelUpload) => {
                pending_upload = None;
                pending_monetize = None;
                if let Some(wv) = sc_webview.as_ref() {
                    let _ = wv.evaluate_script(
                        "window.__scsResetUpload && window.__scsResetUpload(); if (window.__scsMonetizeTimer) { clearInterval(window.__scsMonetizeTimer); window.__scsMonetizeTimer = null; }",
                    );
                    if wv.url().map(|u| u.starts_with(UPLOAD_URL)).unwrap_or(false) {
                        let _ = wv.load_url("https://soundcloud.com/discover");
                    }
                }
            }

            Event::UserEvent(UiEvent::ScStartMonetize(mjob)) => {
                pending_upload = None;
                monetize_seq += 1;
                let fresh_url = format!("{MONETIZE_URL}?scs_m={monetize_seq}");
                if sc_webview.is_none() {
                    let rect = make_rect(sc_bounds.unwrap_or((214.0, 48.0, 960.0, 700.0)));
                    sc_webview = create_sc_child_webview(
                        &main_window,
                        &mut web_context,
                        &fresh_url,
                        rect,
                        Arc::clone(&state),
                    );
                    if let Some(wv) = sc_webview.as_ref() {
                        let _ = wv.set_visible(sc_visible);
                    }
                    pending_monetize = Some((mjob, monetize_seq, None));
                } else if let Some(wv) = sc_webview.as_ref() {
                    let _ = wv.load_url(&fresh_url);
                    pending_monetize = Some((mjob, monetize_seq, None));
                }
            }

            Event::UserEvent(UiEvent::AddAccount) => {
                // 1) Mevcut hesabın oturumunu kaydet (çıkış yapmadan önce, çerezler hâlâ yerinde).
                let cur = Identity::from(&*state.auth.blocking_read());
                if cur.is_valid() {
                    snapshot_account(&main_webview, &cur);
                    if pending_add_prev.is_none() {
                        pending_add_prev = Some(cur.user_id.clone());
                    }
                }
                // 2) Temiz oturum: yoksa SoundCloud giriş sayfası aynı hesaba otomatik girer.
                browser = None;
                sc_webview = None;
                sc_visible = false;
                pending_upload = None;
                pending_monetize = None;
                state.browser_open.store(false, Ordering::Relaxed);
                clear_webview_sc_session(&main_webview);
                // 3) Giriş penceresini aç; hesap algılanınca LoginDetected ile kapanır.
                state.login_pending.store(true, Ordering::SeqCst);
                if let Ok(slot) = state.ui_tx.lock() {
                    if let Some(proxy) = slot.as_ref() {
                        let _ = proxy.send_event(UiEvent::OpenBrowser(Some(SIGNIN_URL.to_string())));
                    }
                }
            }

            Event::UserEvent(UiEvent::SwitchAccount { from, to }) => {
                if from.is_valid() && from.user_id != to {
                    snapshot_account(&main_webview, &from);
                }
                browser = None;
                opened_for_login = false;
                pending_add_prev = None;
                pending_upload = None;
                pending_monetize = None;
                state.login_pending.store(false, Ordering::SeqCst);
                state.browser_open.store(sc_visible, Ordering::Relaxed);
                if !restore_account_session(&state, &main_webview, sc_webview.as_ref(), &to) {
                    // Kayıtlı oturum yüklenemedi: çıkış yapılmış gibi temiz başla.
                    clear_webview_sc_session(&main_webview);
                    *state.auth.blocking_write() = Default::default();
                    let _ = crate::auth::clear();
                }
            }

            Event::UserEvent(UiEvent::SnapshotAccount(id)) => {
                snapshot_account(&main_webview, &id);
            }

            Event::UserEvent(UiEvent::ScClearSession) => {
                pending_add_prev = None;
                sc_webview = None;
                sc_visible = false;
                browser = None;
                opened_for_login = false;
                pending_upload = None;
                pending_monetize = None;
                state.login_pending.store(false, Ordering::SeqCst);
                state.browser_open.store(false, Ordering::Relaxed);
                if let Ok(mut u) = state.browser_url.lock() {
                    u.clear();
                }
                clear_webview_sc_session(&main_webview);
            }

            Event::UserEvent(UiEvent::ScSetOauthCookie(tok)) => {
                pending_add_prev = None;
                let _ = set_soundcloud_oauth_cookie(&main_webview, &tok);
                browser = None;
                opened_for_login = false;
                state.login_pending.store(false, Ordering::SeqCst);
                if let Some(wv) = sc_webview.as_ref() {
                    let _ = wv.load_url("https://soundcloud.com/discover");
                }
            }

            Event::UserEvent(UiEvent::OpenBrowser(url)) => {
                opened_for_login = url.as_deref() == Some(SIGNIN_URL);
                if opened_for_login && !state.auth.blocking_read().is_signed_in() {
                    browser = None;
                    sc_webview = None;
                    sc_visible = false;
                    clear_webview_sc_session(&main_webview);
                }
                match browser.as_ref() {
                    Some((win, webview)) => {
                        if let Some(u) = url.as_deref() {
                            let _ = webview.load_url(u);
                        }
                        win.set_minimized(false);
                        win.set_focus();
                    }
                    None => {
                        // Aynı WebContext'i paylaş: aksi halde WebView2 exe'nin
                        // yanında ikinci bir "*.WebView2" klasörü açıyor.
                        let start = url.unwrap_or_else(|| "https://soundcloud.com/discover".into());
                        browser = create_browser_window(target, &mut web_context, &start, Arc::clone(&state));
                        state
                            .browser_open
                            .store(sc_visible || browser.is_some(), Ordering::Relaxed);
                    }
                }
            }

            Event::UserEvent(UiEvent::FocusMain) => {
                show_main_now(&mut main_shown);
                main_window.set_minimized(false);
                main_window.set_focus();
            }

            Event::UserEvent(UiEvent::LoginDetected) => {
                // Giriş yapılan (yeni) hesabın oturumunu hesap listesine kaydet.
                let id = Identity::from(&*state.auth.blocking_read());
                snapshot_account(&main_webview, &id);
                pending_add_prev = None;
                if opened_for_login {
                    browser = None;
                    opened_for_login = false;
                    state.browser_open.store(sc_visible, Ordering::Relaxed);
                    main_window.set_focus();
                }
            }

            _ => {}
        }

        // İlk açılış güvenliği: sayfa IPC gönderemezse bile 900 ms sonra pencere mutlaka görünsün.
        if !main_shown && boot_at.elapsed() >= Duration::from_millis(900) {
            show_main_now(&mut main_shown);
        }

        // Bekleyen parça yüklemesi: taze /upload?scs=<seq> sayfası açılınca enjekte et.
        if let (Some(wv), Some((ref job, seq, ref mut ready_at))) = (sc_webview.as_ref(), pending_upload.as_mut()) {
            let tag = format!("scs={seq}");
            let on_upload = wv
                .url()
                .map(|u| u.starts_with(UPLOAD_URL) && u.contains(&tag))
                .unwrap_or(false);
            if on_upload {
                let first_seen = ready_at.get_or_insert_with(Instant::now);
                if first_seen.elapsed() >= Duration::from_millis(900) {
                    inject_upload_job(wv, job);
                    pending_upload = None;
                }
            }
        }

        // artists.soundcloud.com oturum açtırmaya yönlendirdiyse (web-auth/signin) takılma, hatayı göster.
        if pending_monetize.is_some() {
            let on_wall = sc_webview
                .as_ref()
                .and_then(|wv| wv.url().ok())
                .map(|u| u.contains("secure.soundcloud.com/web-auth") || u.contains("soundcloud.com/signin"))
                .unwrap_or(false);
            if on_wall {
                let since = *auth_wall_since.get_or_insert_with(Instant::now);
                if since.elapsed() >= Duration::from_secs(6) {
                    pending_monetize = None;
                    auth_wall_since = None;
                    let mut st = state.upload_status.blocking_write();
                    st.active = false;
                    st.ok = false;
                    st.stage.clear();
                    st.error = Some("artists.soundcloud.com oturumu kapalı — SoundCloud sekmesindeki formdan bir kez giriş yap, sonra tekrar dene.".into());
                }
            } else {
                auth_wall_since = None;
            }
        } else {
            auth_wall_since = None;
        }

        // Bekleyen monetize işlemi: artists.soundcloud.com açılınca enjekte et.
        if let (Some(wv), Some((ref mjob, seq, ref mut ready_at))) = (sc_webview.as_ref(), pending_monetize.as_mut()) {
            let tag = format!("scs_m={seq}");
            let on_mon = wv
                .url()
                .map(|u| u.starts_with(MONETIZE_URL) && u.contains(&tag))
                .unwrap_or(false);
            if on_mon {
                let first_seen = ready_at.get_or_insert_with(Instant::now);
                if first_seen.elapsed() >= Duration::from_millis(1200) {
                    inject_monetize_job(wv, mjob);
                    pending_monetize = None;
                }
            }
        }

        // Açık dahili SoundCloud veya harici tarayıcıdaki adresi canlı oku.
        let active_url = if sc_visible {
            sc_webview.as_ref().and_then(|wv| wv.url().ok())
        } else {
            browser.as_ref().and_then(|(_, wv)| wv.url().ok())
        };
        if let Some(current) = active_url {
            if let Ok(mut slot) = state.browser_url.lock() {
                if *slot != current {
                    *slot = current;
                }
            }
        }

        let step_ms = if pending_upload.is_some() || pending_monetize.is_some() || sc_visible || browser.is_some() || !main_shown {
            220
        } else {
            600
        };
        *control_flow = ControlFlow::WaitUntil(Instant::now() + Duration::from_millis(step_ms));
    });
}

fn make_rect((x, y, w, h): (f64, f64, f64, f64)) -> wry::Rect {
    wry::Rect {
        position: wry::dpi::LogicalPosition::new(x, y).into(),
        size: wry::dpi::LogicalSize::new(w.max(100.0), h.max(100.0)).into(),
    }
}

fn create_sc_child_webview(
    parent: &Window,
    context: &mut wry::WebContext,
    start_url: &str,
    bounds: wry::Rect,
    state: Arc<crate::state::AppState>,
) -> Option<WebView> {
    WebViewBuilder::new_with_web_context(context)
        .with_url(start_url)
        .with_bounds(bounds)
        .with_visible(false)
        .with_initialization_script(SC_BRIDGE_JS)
        .with_new_window_req_handler(|url, _features| {
            if url.starts_with("https://") || url == "about:blank" {
                wry::NewWindowResponse::Allow
            } else {
                wry::NewWindowResponse::Deny
            }
        })
        .with_ipc_handler(move |req| {
            let page = req.uri().to_string();
            handle_ipc(&state, &page, req.body());
        })
        .with_devtools(cfg!(debug_assertions))
        .with_background_color((16, 16, 19, 255))
        .build_as_child(parent)
        .ok()
}

fn inject_upload_job(webview: &WebView, job: &UploadJob) {
    let _ = webview.evaluate_script("window.__scsResetUpload && window.__scsResetUpload()");
    for chunk in job.audio_b64.as_bytes().chunks(512 * 1024) {
        if let Ok(s) = std::str::from_utf8(chunk) {
            let js = format!("window.__scsAppendAudio && window.__scsAppendAudio(\"{}\")", s);
            let _ = webview.evaluate_script(&js);
        }
    }
    let fn_js = serde_json::to_string(&job.filename).unwrap_or_else(|_| "\"track.mp3\"".into());
    let title_js = serde_json::to_string(&job.title).unwrap_or_else(|_| "\"Track\"".into());
    let cover_js = match &job.cover_b64 {
        Some(c) => serde_json::to_string(c).unwrap_or_else(|_| "null".into()),
        None => "null".into(),
    };
    let auto_js = if job.auto_submit { "true" } else { "false" };
    let sharing_js = serde_json::to_string(&job.sharing).unwrap_or_else(|_| "\"public\"".into());
    let skip_mon_js = if job.skip_monetize { "true" } else { "false" };
    let commit = format!(
        "window.__scsCommitUpload && window.__scsCommitUpload({fn_js}, {title_js}, {cover_js}, {auto_js}, {sharing_js}, {skip_mon_js})"
    );
    let _ = webview.evaluate_script(&commit);
}

fn inject_monetize_job(webview: &WebView, job: &MonetizeJob) {
    let target_js = match &job.target_title {
        Some(t) => serde_json::to_string(t).unwrap_or_else(|_| "null".into()),
        None => "null".into(),
    };
    let rej_js = if job.resubmit_rejected { "true" } else { "false" };
    let new_js = if job.submit_unsubmitted { "true" } else { "false" };
    let artist_js = serde_json::to_string(&job.artist_hint).unwrap_or_else(|_| "\"\"".into());
    let note_js = serde_json::to_string(&job.intro_note).unwrap_or_else(|_| "\"\"".into());
    let script = format!(
        "window.__scsStartMonetize && window.__scsStartMonetize({target_js}, {rej_js}, {new_js}, {artist_js}, {note_js})"
    );
    let _ = webview.evaluate_script(&script);
}

fn create_browser_window(
    target: &EventLoopWindowTarget<UiEvent>,
    context: &mut wry::WebContext,
    start_url: &str,
    state: Arc<crate::state::AppState>,
) -> Option<(Window, WebView)> {
    let window = WindowBuilder::new()
        .with_title("SoundCloud — SC Studio")
        .with_inner_size(Size::Physical(PhysicalSize::new(1180, 820)))
        .with_min_inner_size(Size::Physical(PhysicalSize::new(860, 560)))
        .build(target)
        .ok()?;

    if let Some(icon) = load_icon() {
        window.set_window_icon(Some(icon));
    }
    crate::winmsg::style_dark_window(hwnd_of(&window));

    let webview = WebViewBuilder::new_with_web_context(context)
        .with_url(start_url)
        .with_initialization_script(SC_BRIDGE_JS)
        // wry yeni pencere isteklerini varsayılan olarak reddeder; SoundCloud'un
        // Facebook / Google / Apple girişleri açılır pencere kullandığı için
        // "Please enable popup windows" hatası veriyordu. WebView2'nin kendi
        // açılır penceresine izin ver (opener bağı korunur, giriş tamamlanır).
        .with_new_window_req_handler(|url, _features| {
            if url.starts_with("https://") || url == "about:blank" {
                wry::NewWindowResponse::Allow
            } else {
                wry::NewWindowResponse::Deny
            }
        })
        .with_ipc_handler(move |req| {
            let page = req.uri().to_string();
            handle_ipc(&state, &page, req.body());
        })
        .with_devtools(cfg!(debug_assertions))
        .with_background_color((14, 14, 16, 255))
        .build(&window)
        .ok()?;

    Some((window, webview))
}

/// Çerezleri ve tarama verisini siler (silme bitene kadar bekler).
fn clear_webview_sc_session(webview: &WebView) {
    wipe_session_blocking(webview);
}

/// Hesabın oturumunu kaydeder. Giriş çerezi yoksa (oturum kapalı) kayıtlı çerezleri
/// bozmaz, yalnızca kimliği günceller.
fn snapshot_account(webview: &WebView, id: &Identity) {
    if !id.is_valid() {
        return;
    }
    let recs = snapshot_cookies(webview);
    if crate::cookies::has_login_cookie(&recs) {
        crate::accounts::upsert_session(id, None, Some(&recs));
    } else {
        crate::accounts::upsert_session(id, None, None);
    }
}

/// Kayıtlı hesabın oturumunu (önce çerez anlık görüntüsü, olmazsa token) WebView2'ye yükler
/// ve uygulama kimliğini ayarlar. Kayıtlı oturum yoksa `false` döner.
fn restore_account_session(
    state: &crate::state::AppState,
    main_webview: &WebView,
    sc_webview: Option<&WebView>,
    user_id: &str,
) -> bool {
    let Some(entry) = crate::accounts::get(user_id) else {
        return false;
    };
    let mut restored = false;
    if let Some(recs) = crate::accounts::load_cookies(user_id) {
        restored = restore_cookies(main_webview, &recs) > 0;
    }
    if !restored {
        if let Some(tok) = crate::accounts::token_for(user_id) {
            restored = set_soundcloud_oauth_cookie(main_webview, &tok).is_ok();
        }
    }
    if !restored {
        return false;
    }
    let auth = Identity::from(&entry).to_auth();
    *state.auth.blocking_write() = auth.clone();
    let _ = crate::auth::save(&auth);
    if let Some(wv) = sc_webview {
        let _ = wv.load_url("https://soundcloud.com/discover");
    }
    true
}

fn initial_window_geometry(
    target: &EventLoopWindowTarget<UiEvent>,
    state: &crate::state::AppState,
) -> (Size, Option<PhysicalPosition<i32>>, bool) {
    let cfg = state.cfg.blocking_read();
    let prim = target.primary_monitor();
    let prim_pos = prim.as_ref().map(|m| m.position()).unwrap_or(PhysicalPosition::new(0, 0));
    let max_screen = prim
        .map(|m| m.size())
        .unwrap_or(PhysicalSize::new(1600, 1000));

    let max_inner_w = max_screen.width.saturating_sub(32).max(1000);
    let max_inner_h = max_screen.height.saturating_sub(96).max(620);

    let (cw, ch) = match (cfg.win_w, cfg.win_h) {
        (Some(w), Some(h)) if w >= 1000 && h >= 620 => (w.min(max_inner_w), h.min(max_inner_h)),
        _ => fit_to_screen(target, 0.84, (1440, 880), (1040, 660)),
    };
    let size = Size::Physical(PhysicalSize::new(cw, ch));

    let pos = match (cfg.win_x, cfg.win_y) {
        (Some(x), Some(y)) => {
            // Çoklu monitörden biri çıkarıldıysa pencere ekran dışında kalmasın;
            // ayrıca görev çubuğunun arkasında kalacak kadar aşağı taşmasın.
            let fits_monitor = target.available_monitors().find(|m| {
                let mp = m.position();
                let ms = m.size();
                x < mp.x + ms.width as i32 - 160
                    && x + 160 > mp.x
                    && y >= mp.y - 10
                    && y < mp.y + ms.height as i32 - 120
            });
            if let Some(m) = fits_monitor {
                let mp = m.position();
                let ms = m.size();
                let max_top = mp.y + (ms.height as i32 - 52 - (ch as i32 + 40)).max(8);
                Some(PhysicalPosition::new(x, y.clamp(mp.y, max_top)))
            } else {
                None
            }
        }
        _ => None,
    }
    .or_else(|| {
        // Varsayılan konum: görev çubuğunun üstünde temiz şekilde ortalı.
        let x = prim_pos.x + ((max_screen.width as i32 - (cw as i32 + 16)).max(16)) / 2;
        let y = prim_pos.y + ((max_screen.height as i32 - 52 - (ch as i32 + 40)).max(16)) / 2;
        Some(PhysicalPosition::new(x, y))
    });

    (size, pos, cfg.win_maximized)
}

fn save_window_state(window: &Window, state: &crate::state::AppState) {
    let maximized = window.is_maximized();
    let pos = window.outer_position().ok();
    let size = window.inner_size();

    let mut cfg = state.cfg.blocking_write();
    cfg.win_maximized = maximized;
    if !maximized && size.width >= 1000 && size.height >= 620 {
        cfg.win_w = Some(size.width);
        cfg.win_h = Some(size.height);
        if let Some(p) = pos {
            if p.x > -10_000 && p.y > -10_000 {
                cfg.win_x = Some(p.x);
                cfg.win_y = Some(p.y);
            }
        }
    }
    let _ = crate::config::save(&cfg);
}

fn cleanup_on_exit(state: &crate::state::AppState) {
    use std::sync::atomic::Ordering;
    state.cancel_scan.store(true, Ordering::SeqCst);
    state.cancel_download.store(true, Ordering::SeqCst);
    if let Ok(cfg) = state.cfg.try_read() {
        let _ = crate::download::cleanup_stale_parts(&cfg.target_dir());
    }
    crate::paths::cleanup_preview_cache();
}

/// Ekranın oranı kadar, verilen sınırlar içinde kalan pencere boyutu.
fn fit_to_screen(
    target: &EventLoopWindowTarget<UiEvent>,
    ratio: f64,
    max: (u32, u32),
    min: (u32, u32),
) -> (u32, u32) {
    let screen = target
        .primary_monitor()
        .map(|m| m.size())
        .unwrap_or(PhysicalSize::new(1600, 1000));

    let cap_w = max.0.min(screen.width.saturating_sub(32).max(min.0));
    let cap_h = max.1.min(screen.height.saturating_sub(96).max(min.1));
    let w = ((screen.width as f64 * ratio) as u32).clamp(min.0, cap_w);
    let h = ((screen.height as f64 * ratio) as u32).clamp(min.1, cap_h);
    (w, h)
}

fn load_icon() -> Option<tao::window::Icon> {
    let bytes = crate::assets::asset_bytes("icon.png")?;
    let img = image::load_from_memory(&bytes).ok()?.to_rgba8();
    let (w, h) = img.dimensions();
    tao::window::Icon::from_rgba(img.into_raw(), w, h).ok()
}
