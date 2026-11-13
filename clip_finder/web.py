from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request, send_file

from clip_finder.compiler import CompilationPipeline
from clip_finder.editor import CamCorner, EditConfig, LayoutMode
from clip_finder.engine import ClipFinderEngine
from clip_finder.models import Clip
from clip_finder.pipeline import ClipFarmerPipeline

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>GTA 6 W-Speed Clip Farmer — Twitch & Kick</title>
  <style>
    :root {
      --bg: #0b0e14;
      --card: #141923;
      --border: #273040;
      --text: #e6edf3;
      --muted: #8b949e;
      --accent: #58a6ff;
      --wspeed: #f5c518;
      --twitch: #9146ff;
      --kick: #53fc18;
      --kick-text: #0b0e0f;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    header {
      padding: 18px 28px;
      border-bottom: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px;
      background: #0f141d;
    }
    header h1 { margin: 0; font-size: 20px; display: flex; align-items: center; gap: 8px; }
    header p { margin: 4px 0 0; color: var(--muted); font-size: 13px; }
    .tabs { display: flex; gap: 8px; }
    .tab-btn {
      background: #1c2331;
      color: var(--text);
      border: 1px solid var(--border);
      padding: 8px 16px;
      border-radius: 8px;
      cursor: pointer;
      font-weight: 600;
      font-size: 13px;
    }
    .tab-btn.active { background: var(--accent); color: #0b0e14; border-color: var(--accent); }
    .container { max-width: 1400px; margin: 0 auto; padding: 20px 24px; }
    .panel {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px;
      margin-bottom: 18px;
    }
    .filters {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 12px;
    }
    .farm-bar {
      margin-top: 14px;
      padding-top: 14px;
      border-top: 1px solid var(--border);
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px;
      align-items: end;
    }
    label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 6px; }
    input, select, button {
      width: 100%;
      padding: 9px 11px;
      border-radius: 8px;
      border: 1px solid var(--border);
      background: #0b0e14;
      color: var(--text);
      font-size: 13px;
    }
    button {
      background: var(--accent);
      color: #0b0e14;
      font-weight: 700;
      border: none;
      cursor: pointer;
    }
    button:hover { opacity: 0.92; }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    button.wspeed-btn {
      background: var(--wspeed);
      color: #0b0e14;
    }
    button.secondary {
      background: #1f2633;
      color: var(--text);
      border: 1px solid var(--border);
      width: auto;
      padding: 8px 14px;
    }
    .toolbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 14px;
      gap: 12px;
      flex-wrap: wrap;
    }
    .stats { color: var(--muted); font-size: 14px; }
    .status-banner {
      background: rgba(88, 166, 255, 0.12);
      border: 1px solid rgba(88, 166, 255, 0.4);
      color: #9ecbff;
      padding: 10px 14px;
      border-radius: 8px;
      margin-bottom: 14px;
      font-size: 13px;
      display: none;
    }
    .errors {
      background: rgba(248, 81, 73, 0.12);
      border: 1px solid rgba(248, 81, 73, 0.4);
      color: #ff7b72;
      padding: 10px 14px;
      border-radius: 8px;
      margin-bottom: 14px;
      font-size: 13px;
      display: none;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(310px, 1fr));
      gap: 16px;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      transition: transform 0.15s ease, border-color 0.15s ease;
    }
    .card:hover { transform: translateY(-2px); border-color: var(--accent); }
    .thumb-wrap { position: relative; aspect-ratio: 16 / 9; background: #000; }
    .thumb-wrap img { width: 100%; height: 100%; object-fit: cover; display: block; }
    .badge {
      position: absolute;
      top: 8px;
      left: 8px;
      padding: 3px 8px;
      border-radius: 6px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
    }
    .badge.twitch { background: var(--twitch); color: #fff; }
    .badge.kick { background: var(--kick); color: var(--kick-text); }
    .badge.done { left: auto; right: 8px; background: #238636; color: #fff; }
    .duration {
      position: absolute;
      bottom: 8px;
      right: 8px;
      background: rgba(0, 0, 0, 0.8);
      padding: 2px 7px;
      border-radius: 5px;
      font-size: 12px;
    }
    .card-body { padding: 14px; display: flex; flex-direction: column; gap: 8px; flex: 1; }
    .title {
      font-size: 15px;
      font-weight: 600;
      line-height: 1.35;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }
    .meta { font-size: 13px; color: var(--muted); display: flex; justify-content: space-between; }
    .actions {
      margin-top: auto;
      padding-top: 8px;
      display: flex;
      gap: 8px;
    }
    .actions a {
      flex: 1;
      text-align: center;
      text-decoration: none;
      padding: 9px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      background: #1f2633;
      color: var(--text);
      border: 1px solid var(--border);
    }
    .actions a:hover { border-color: var(--accent); color: var(--accent); }
    .actions button { flex: 1.3; padding: 9px; font-size: 13px; }
    .ready-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
      gap: 18px;
    }
    .ready-card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }
    .ready-card video {
      width: 100%;
      max-height: 460px;
      background: #000;
    }
    .ready-body { padding: 14px; display: flex; flex-direction: column; gap: 10px; }
    .copy-box {
      background: #0b0e14;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 8px 10px;
      font-size: 12px;
      color: #c9d1d9;
      white-space: pre-wrap;
      max-height: 90px;
      overflow-y: auto;
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>⚡ GTA 6 W-Speed Clip Farmer</h1>
      <p>Popüler klipleri bul, otomatik 9:16 + zoom/shake/SFX + dinamik altyazı ile Shorts/Reels/TikTok'a hazırla</p>
    </div>
    <div class="tabs">
      <button class="tab-btn active" id="tab-discover" onclick="switchTab('discover')">🔍 Klip Keşfet</button>
      <button class="tab-btn" id="tab-ready" onclick="switchTab('ready')">🎬 Hazır Videolar (<span id="ready-count">0</span>)</button>
      <button class="secondary" onclick="exportResults('json')">JSON</button>
      <button class="secondary" onclick="exportResults('csv')">CSV</button>
    </div>
  </header>

  <div class="container">
    <div id="status-banner" class="status-banner"></div>
    <div id="errors" class="errors"></div>

    <div id="view-discover">
      <div class="panel">
        <form class="filters" onsubmit="event.preventDefault(); searchClips();">
          <div>
            <label>Oyun / Kategori</label>
            <input id="category" value="Grand Theft Auto VI" placeholder="Örn: Grand Theft Auto VI" />
          </div>
          <div>
            <label>Platform</label>
            <select id="platform">
              <option value="twitch,kick" selected>Twitch + Kick</option>
              <option value="twitch">Sadece Twitch</option>
              <option value="kick">Sadece Kick</option>
            </select>
          </div>
          <div>
            <label>Zaman Aralığı</label>
            <select id="period">
              <option value="day">Son 24 Saat</option>
              <option value="week" selected>Son 7 Gün</option>
              <option value="month">Son 30 Gün</option>
              <option value="all">Tüm Zamanlar</option>
            </select>
          </div>
          <div>
            <label>Sıralama</label>
            <select id="sort_by">
              <option value="views" selected>En Çok İzlenen</option>
              <option value="virality">Virallik (İzlenme/Saat)</option>
              <option value="recent">En Yeni</option>
            </select>
          </div>
          <div>
            <label>Min. İzlenme</label>
            <input id="min_views" type="number" value="0" min="0" />
          </div>
          <div>
            <label>Maks. Süre (sn)</label>
            <input id="max_duration" type="number" value="90" placeholder="Örn: 60" min="1" />
          </div>
          <div>
            <label>Dil (Twitch)</label>
            <input id="language" placeholder="Örn: tr, en" />
          </div>
          <div>
            <label>Başlık Kelime Filtresi</label>
            <input id="keywords" placeholder="Örn: gta 6, trailer" />
          </div>
          <div>
            <label>&nbsp;</label>
            <button type="submit">Klipleri Bul</button>
          </div>
        </form>

        <div class="farm-bar">
          <div>
            <label>9:16 Dikey Düzen (Layout)</label>
            <select id="layout">
              <option value="auto" selected>Otomatik (Webcam Algıla + Tam Ekran)</option>
              <option value="center_crop">Center Crop (Tam Ekran 9:16)</option>
              <option value="split_cam">Split Cam (Üst Cam / Alt Oyun)</option>
              <option value="blur_stack">Blur Stack (Bulanık Arka Plan)</option>
            </select>
          </div>
          <div>
            <label>Cam Konumu (Split Cam için)</label>
            <select id="cam_corner">
              <option value="top_left" selected>Sol Üst</option>
              <option value="top_right">Sağ Üst</option>
              <option value="bottom_left">Sol Alt</option>
              <option value="bottom_right">Sağ Alt</option>
            </select>
          </div>
          <div>
            <label>Altyazı Whisper Modeli</label>
            <select id="whisper_model">
              <option value="tiny">tiny (Çok Hızlı)</option>
              <option value="base" selected>base (Dengeli)</option>
              <option value="small">small (Yüksek Kalite)</option>
            </select>
          </div>
          <div>
            <label>Toplu Farm Adedi</label>
            <input id="farm_count" type="number" value="3" min="1" max="10" />
          </div>
          <div>
            <label>Derleme Anlatımı</label>
            <select id="narration_lang">
              <option value="none" selected>Doğal Klip Sesi (AI Ses Kapalı - Önerilen)</option>
              <option value="tr">Türkçe TTS (Opsiyonel)</option>
              <option value="en">İngilizce TTS (Opsiyonel)</option>
            </select>
          </div>
          <div>
            <button type="button" class="wspeed-btn" onclick="compileMonetized()">💰 62+ sn Derleme Üret</button>
          </div>
          <div>
            <button type="button" onclick="batchFarm()">🚀 Tekli Farm (N Adet)</button>
          </div>
        </div>
      </div>

      <div class="toolbar">
        <div id="stats" class="stats">Arama yapılıyor...</div>
      </div>
      <div id="grid" class="grid"></div>
    </div>

    <div id="view-ready" style="display:none;">
      <div class="toolbar">
        <div class="stats">Render edilmiş, Shorts / Reels / TikTok paylaşımına hazır videolar</div>
        <button class="secondary" onclick="loadReady()">Yenile</button>
      </div>
      <div id="ready-grid" class="ready-grid"></div>
    </div>
  </div>

  <script>
    let lastClips = [];

    function switchTab(tab) {
      document.getElementById('view-discover').style.display = tab === 'discover' ? 'block' : 'none';
      document.getElementById('view-ready').style.display = tab === 'ready' ? 'block' : 'none';
      document.getElementById('tab-discover').classList.toggle('active', tab === 'discover');
      document.getElementById('tab-ready').classList.toggle('active', tab === 'ready');
      if (tab === 'ready') loadReady();
    }

    function formatNumber(n) {
      return new Intl.NumberFormat('tr-TR').format(n);
    }

    function escapeHtml(str) {
      return (str || '').replace(/[&<>"']/g, m => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      }[m]));
    }

    function showStatus(msg) {
      const el = document.getElementById('status-banner');
      el.textContent = msg;
      el.style.display = msg ? 'block' : 'none';
    }

    function showError(msg) {
      const el = document.getElementById('errors');
      el.textContent = msg;
      el.style.display = msg ? 'block' : 'none';
    }

    async function searchClips() {
      const stats = document.getElementById('stats');
      const grid = document.getElementById('grid');
      stats.textContent = 'Klipler çekiliyor...';
      showError('');

      const params = new URLSearchParams({
        category: document.getElementById('category').value.trim() || 'Grand Theft Auto VI',
        platforms: document.getElementById('platform').value,
        period: document.getElementById('period').value,
        sort_by: document.getElementById('sort_by').value,
        min_views: document.getElementById('min_views').value || '0',
        max_duration: document.getElementById('max_duration').value || '',
        language: document.getElementById('language').value.trim(),
        keywords: document.getElementById('keywords').value.trim(),
        limit: '30',
      });

      const res = await fetch('/api/clips?' + params.toString());
      const data = await res.json();
      lastClips = data.clips || [];

      if (data.errors && Object.keys(data.errors).length > 0) {
        showError('Uyarı: ' + JSON.stringify(data.errors));
      }

      stats.textContent = `${lastClips.length} klip bulundu.`;
      grid.innerHTML = lastClips.map((c, idx) => `
        <div class="card">
          <div class="thumb-wrap">
            <img src="${escapeHtml(c.thumbnail_url)}" alt="${escapeHtml(c.title)}" loading="lazy" />
            <span class="badge ${escapeHtml(c.platform)}">${escapeHtml(c.platform)}</span>
            ${c.already_farmed ? '<span class="badge done">HAZIR</span>' : ''}
            <span class="duration">${Math.round(c.duration_seconds)}s</span>
          </div>
          <div class="card-body">
            <div class="title" title="${escapeHtml(c.title)}">${escapeHtml(c.title)}</div>
            <div class="meta">
              <span>${escapeHtml(c.channel_name)}</span>
              <span>${formatNumber(c.views)} izlenme</span>
            </div>
            <div class="meta">
              <span>${formatNumber(Math.round(c.virality_score))}/saat hız</span>
              <span>${escapeHtml((c.created_at || '').slice(0, 10))}</span>
            </div>
            <div class="actions">
              <a href="${escapeHtml(c.url)}" target="_blank" rel="noopener">İzle</a>
              <button class="wspeed-btn" id="farm-btn-${idx}" onclick="farmSingle(${idx})">
                ${c.already_farmed ? '🔁 Tekrar Düzenle' : '⚡ W-Speed Düzenle'}
              </button>
            </div>
          </div>
        </div>
      `).join('');
    }

    async function farmSingle(idx) {
      const clip = lastClips[idx];
      const btn = document.getElementById(`farm-btn-${idx}`);
      btn.disabled = true;
      btn.textContent = '⏳ İşleniyor...';
      showError('');
      showStatus(`"${clip.title}" indiriliyor ve W-Speed tarzında otomatik düzenleniyor (altyazı + zoom/shake + SFX)...`);

      try {
        const res = await fetch('/api/farm-one', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            clip,
            layout: document.getElementById('layout').value,
            cam_corner: document.getElementById('cam_corner').value,
            whisper_model: document.getElementById('whisper_model').value,
            force: Boolean(clip.already_farmed),
          }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'İşlem başarısız');
        showStatus(`✅ Tamamlandı! Hazır video: ${data.output_path}`);
        clip.already_farmed = true;
        btn.textContent = '✅ Hazır';
        await loadReady();
      } catch (err) {
        showError('Hata: ' + err.message);
        btn.textContent = '⚡ W-Speed Düzenle';
      } finally {
        btn.disabled = false;
      }
    }

    async function batchFarm() {
      showError('');
      const count = parseInt(document.getElementById('farm_count').value || '3', 10);
      showStatus(`🚀 En popüler ${count} yeni klip seçiliyor, indiriliyor ve W-Speed tarzında düzenleniyor...`);
      try {
        const res = await fetch('/api/farm-batch', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            category: document.getElementById('category').value.trim() || 'Grand Theft Auto VI',
            platforms: document.getElementById('platform').value.split(',').map(s => s.trim()).filter(Boolean),
            period: document.getElementById('period').value,
            sort_by: document.getElementById('sort_by').value,
            min_views: parseInt(document.getElementById('min_views').value || '0', 10),
            max_duration: parseFloat(document.getElementById('max_duration').value || '90'),
            language: document.getElementById('language').value.trim() || null,
            keywords: document.getElementById('keywords').value.split(',').map(s => s.trim()).filter(Boolean),
            count,
            layout: document.getElementById('layout').value,
            cam_corner: document.getElementById('cam_corner').value,
            whisper_model: document.getElementById('whisper_model').value,
          }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Toplu farm başarısız');
        showStatus(`✅ ${data.processed_count} klip W-Speed tarzında hazırlandı! "Hazır Videolar" sekmesinden izleyebilirsin.`);
        if (data.errors && Object.keys(data.errors).length > 0) {
          showError('Bazı uyarılara denk gelindi: ' + JSON.stringify(data.errors));
        }
        await loadReady();
        await searchClips();
      } catch (err) {
        showError('Hata: ' + err.message);
      }
    }

    async function compileMonetized() {
      showError('');
      showStatus('💰 62+ sn para kazanma şartlarına uygun geri sayım derlemesi hazırlanıyor (Top N + sesli giriş + altyazı)...');
      try {
        const nar = document.getElementById('narration_lang').value;
        const res = await fetch('/api/compile', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            category: document.getElementById('category').value.trim() || 'Grand Theft Auto VI',
            platforms: document.getElementById('platform').value.split(',').map(s => s.trim()).filter(Boolean),
            period: document.getElementById('period').value,
            sort_by: document.getElementById('sort_by').value,
            min_views: parseInt(document.getElementById('min_views').value || '0', 10),
            language: document.getElementById('language').value.trim() || null,
            keywords: document.getElementById('keywords').value.split(',').map(s => s.trim()).filter(Boolean),
            layout: document.getElementById('layout').value,
            cam_corner: document.getElementById('cam_corner').value,
            whisper_model: document.getElementById('whisper_model').value,
            narration_lang: nar === 'none' ? null : nar,
          }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Derleme başarısız');
        showStatus(`✅ ${data.duration_seconds.toFixed(1)} sn derleme hazır (${data.clip_count} klip)! "Hazır Videolar" sekmesinden izleyebilirsin.`);
        await loadReady();
        await searchClips();
      } catch (err) {
        showError('Hata: ' + err.message);
      }
    }

    async function loadReady() {
      const res = await fetch('/api/ready');
      const data = await res.json();
      const items = data.items || [];
      document.getElementById('ready-count').textContent = items.length;
      const grid = document.getElementById('ready-grid');
      if (items.length === 0) {
        grid.innerHTML = '<div class="stats">Henüz render edilmiş video yok. Klip Keşfet sekmesinden bir klibi W-Speed düzenle!</div>';
        return;
      }
      grid.innerHTML = items.map((item, idx) => `
        <div class="ready-card">
          <video controls preload="metadata" src="/api/video?path=${encodeURIComponent(item.output_path)}"></video>
          <div class="ready-body">
            <div class="title">${escapeHtml(item.metadata.viral_title || item.title)}</div>
            <div class="meta">
              <span>${escapeHtml(item.platform.toUpperCase())} • ${escapeHtml(item.channel_name)}</span>
              <a style="color:var(--accent);" href="/api/video?path=${encodeURIComponent(item.output_path)}&download=1">MP4 İndir</a>
            </div>
            <label>YouTube Shorts Başlığı</label>
            <div class="copy-box" id="yt-${idx}">${escapeHtml(item.metadata.youtube_shorts_title || '')}</div>
            <button class="secondary" onclick="copyText('yt-${idx}')">Shorts Başlığını Kopyala</button>
            <label>TikTok / Reels Açıklaması & Hashtagler</label>
            <div class="copy-box" id="tt-${idx}">${escapeHtml(item.metadata.tiktok_caption || '')}</div>
            <button class="secondary" onclick="copyText('tt-${idx}')">TikTok / Reels Açıklamayı Kopyala</button>
          </div>
        </div>
      `).join('');
    }

    function copyText(id) {
      const txt = document.getElementById(id).textContent;
      navigator.clipboard.writeText(txt);
      showStatus('📋 Panoya kopyalandı!');
    }

    async function exportResults(fmt) {
      const params = new URLSearchParams({
        category: document.getElementById('category').value.trim() || 'Grand Theft Auto VI',
        platforms: document.getElementById('platform').value,
        period: document.getElementById('period').value,
        sort_by: document.getElementById('sort_by').value,
        min_views: document.getElementById('min_views').value || '0',
        max_duration: document.getElementById('max_duration').value || '',
        language: document.getElementById('language').value.trim(),
        format: fmt,
      });
      const res = await fetch('/api/export?' + params.toString());
      const data = await res.json();
      alert(`Dışa aktarıldı (${data.count} klip): ${data.path}`);
    }

    searchClips();
    loadReady();
  </script>
</body>
</html>
"""


def create_app(
    engine: ClipFinderEngine | None = None,
    pipeline: ClipFarmerPipeline | None = None,
) -> Flask:
    app = Flask(__name__)
    clip_engine = engine or ClipFinderEngine()
    farmer = pipeline or ClipFarmerPipeline(engine=clip_engine)

    @app.get("/")
    def index():
        return render_template_string(HTML_TEMPLATE)

    @app.get("/api/clips")
    def api_clips():
        category = request.args.get("category", "Grand Theft Auto VI")
        platforms = [p.strip() for p in request.args.get("platforms", "twitch,kick").split(",") if p.strip()]
        period = request.args.get("period", "week")
        sort_by = request.args.get("sort_by", "views")
        min_views = int(request.args.get("min_views") or 0)
        max_dur_raw = request.args.get("max_duration")
        max_duration = float(max_dur_raw) if max_dur_raw else None
        language = request.args.get("language") or None
        kw_raw = request.args.get("keywords", "")
        keywords = [k.strip() for k in kw_raw.split(",") if k.strip()] or None
        limit = int(request.args.get("limit") or 30)

        result = clip_engine.search(
            category=category,
            platforms=platforms,
            period=period,  # type: ignore[arg-type]
            limit_per_platform=limit,
            min_views=min_views,
            max_duration=max_duration,
            language=language,
            keywords=keywords,
            sort_by=sort_by,  # type: ignore[arg-type]
        )
        clips_payload = []
        for c in result.clips:
            d = c.to_dict()
            d["already_farmed"] = farmer.history.is_processed(c.platform, c.clip_id)
            clips_payload.append(d)

        return jsonify({
            "count": len(clips_payload),
            "errors": result.errors,
            "clips": clips_payload,
        })

    @app.post("/api/farm-one")
    def api_farm_one():
        payload = request.get_json(force=True) or {}
        clip_raw = payload.get("clip") or {}
        if not clip_raw.get("clip_id") or not clip_raw.get("url"):
            return jsonify({"error": "Geçersiz klip verisi."}), 400

        known_fields = set(Clip.__dataclass_fields__.keys())
        clip_kwargs = {k: v for k, v in clip_raw.items() if k in known_fields}
        clip = Clip(**clip_kwargs)

        layout: LayoutMode = payload.get("layout", "auto")
        cam_corner: CamCorner = payload.get("cam_corner", "top_left")
        whisper_model = payload.get("whisper_model", "base")
        force = bool(payload.get("force", False))

        try:
            res = farmer.process_clip(
                clip,
                whisper_model=whisper_model,
                edit_config=EditConfig(
                    layout=layout,
                    cam_corner=cam_corner,
                    punch_zoom=True,
                    camera_shake=True,
                    impact_flash=True,
                    add_sfx=True,
                ),
                force=force,
            )
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)}), 500

        return jsonify({
            "output_path": str(res.output_path.resolve()),
            "metadata": res.metadata.to_dict(),
            "hype_peaks": res.hype_peaks,
        })

    @app.post("/api/farm-batch")
    def api_farm_batch():
        payload = request.get_json(force=True) or {}
        layout: LayoutMode = payload.get("layout", "auto")
        cam_corner: CamCorner = payload.get("cam_corner", "top_left")
        whisper_model = payload.get("whisper_model", "base")

        results, errors = farmer.farm_top_clips(
            category=payload.get("category", "Grand Theft Auto VI"),
            platforms=payload.get("platforms") or ["twitch", "kick"],
            period=payload.get("period", "week"),
            sort_by=payload.get("sort_by", "views"),
            count=int(payload.get("count", 3)),
            min_views=int(payload.get("min_views", 0)),
            max_duration=payload.get("max_duration", 90.0),
            language=payload.get("language") or None,
            keywords=payload.get("keywords") or None,
            whisper_model=whisper_model,
            edit_config=EditConfig(
                layout=layout,
                cam_corner=cam_corner,
                punch_zoom=True,
                camera_shake=True,
                impact_flash=True,
                add_sfx=True,
            ),
        )
        return jsonify({
            "processed_count": len(results),
            "errors": errors,
            "items": [
                {
                    "output_path": str(r.output_path.resolve()),
                    "metadata": r.metadata.to_dict(),
                }
                for r in results
            ],
        })

    @app.post("/api/compile")
    def api_compile():
        payload = request.get_json(force=True) or {}
        layout: LayoutMode = payload.get("layout", "auto")
        cam_corner: CamCorner = payload.get("cam_corner", "top_left")
        whisper_model = payload.get("whisper_model", "base")
        compiler = CompilationPipeline(engine=clip_engine, history=farmer.history, downloader=farmer.downloader, output_dir=farmer.output_dir)

        try:
            comp = compiler.build_compilation(
                category=payload.get("category", "Grand Theft Auto VI"),
                platforms=payload.get("platforms") or ["twitch", "kick"],
                period=payload.get("period", "week"),
                sort_by=payload.get("sort_by", "views"),
                min_views=int(payload.get("min_views", 0)),
                language=payload.get("language") or None,
                keywords=payload.get("keywords") or None,
                whisper_model=whisper_model,
                narration_lang=payload.get("narration_lang") or None,
                edit_config=EditConfig(
                    layout=layout,
                    cam_corner=cam_corner,
                    punch_zoom=True,
                    camera_shake=True,
                    impact_flash=True,
                    add_sfx=True,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)}), 500

        return jsonify({
            "output_path": str(comp.output_path.resolve()),
            "duration_seconds": comp.duration_seconds,
            "clip_count": len(comp.clips_used),
            "title": comp.title,
            "monetization_checks": comp.monetization_checks,
        })

    @app.get("/api/ready")
    def api_ready():
        ready_items = []
        for entry in farmer.history.list_all():
            if entry.get("status") != "done":
                continue
            out_p = Path(entry.get("output_path", ""))
            if not out_p.exists():
                continue
            meta = {}
            meta_p = Path(entry.get("metadata_path", ""))
            if meta_p.exists():
                try:
                    meta = json.loads(meta_p.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    meta = {}
            ready_items.append({**entry, "metadata": meta})
        return jsonify({"items": ready_items})

    @app.get("/api/video")
    def api_video():
        raw_path = request.args.get("path", "")
        if not raw_path:
            return jsonify({"error": "Dosya yolu gerekli."}), 400
        target = Path(raw_path).resolve()
        ready_root = farmer.output_dir.resolve()
        if not target.is_relative_to(ready_root) or not target.exists():
            return jsonify({"error": "Video bulunamadı."}), 404
        as_att = request.args.get("download") == "1"
        return send_file(target, as_attachment=as_att)

    @app.get("/api/export")
    def api_export():
        fmt = request.args.get("format", "json").lower()
        category = request.args.get("category", "Grand Theft Auto VI")
        platforms = [p.strip() for p in request.args.get("platforms", "twitch,kick").split(",") if p.strip()]
        period = request.args.get("period", "week")
        sort_by = request.args.get("sort_by", "virality")
        min_views = int(request.args.get("min_views") or 0)
        max_dur_raw = request.args.get("max_duration")
        max_duration = float(max_dur_raw) if max_dur_raw else None
        language = request.args.get("language") or None

        result = clip_engine.search(
            category=category,
            platforms=platforms,
            period=period,  # type: ignore[arg-type]
            limit_per_platform=50,
            min_views=min_views,
            max_duration=max_duration,
            language=language,
            sort_by=sort_by,  # type: ignore[arg-type]
        )
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = Path("output")
        if fmt == "csv":
            path = clip_engine.export_csv(result.clips, out_dir / f"clips_{stamp}.csv")
        else:
            path = clip_engine.export_json(result.clips, out_dir / f"clips_{stamp}.json")

        return jsonify({"count": len(result.clips), "path": str(path.resolve())})

    return app


def run_web(host: str = "127.0.0.1", port: int = 5000) -> None:
    app = create_app()
    app.run(host=host, port=port, debug=False)
