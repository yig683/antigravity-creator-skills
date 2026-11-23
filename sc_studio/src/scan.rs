//! "Yeni Parçalar Keşfet & Puanla" taraması.
//!
//! Orijinal `run_ai_scan_worker`'ın portu: kaynak havuzları paralel taranır,
//! adaylar puanlanır, daha önce görülenler elenir ve sonuç listesi döner.

use crate::score::{score_track, ScoreInput, DEFAULT_CHANNEL_NAMES, VIRAL_WEIGHTS};
use crate::sc::Track;
use crate::state::{save_seen, AppState, Candidate};
use anyhow::Result;
use chrono::{DateTime, Utc};
use std::collections::{HashMap, HashSet};
use std::sync::Arc;
use tokio::sync::Semaphore;
use tokio::task::JoinSet;

pub const SEARCH_POOLS: &[(&str, &[&str])] = &[
    (
        "all_viral",
        &[
            "phonk tiktok viral slowed",
            "hardtekk bass boosted ultra slowed",
            "slowed reverb viral tiktok remix",
            "montagem brazilian funk super slowed",
            "tiktok edit audio bass boosted loop",
            "krushfunk slowed reverb tiktok",
            "jumpstyle hardtekk slowed bass",
            "dark phonk gym viral slowed",
            "hardstyle slowed reverb tiktok edit",
        ],
    ),
    (
        "phonk",
        &[
            "brazilian phonk viral tiktok bass boosted",
            "montagem jumpstyle super slowed tiktok",
            "krushfunk slowed reverb viral",
            "aggressive drift phonk slowed bass",
            "brazilian funk phonk edit audio",
            "ultra slowed phonk tiktok trend",
            "mexican phonk viral remix slowed",
        ],
    ),
    (
        "hardtekk",
        &[
            "hardtekk bass boosted slowed reverb",
            "hardtekk ultra slowed low honor",
            "hardtekk pitched slowed best part loop",
            "schranz hardtekk slowed tiktok viral",
            "frenchcore hardtekk slowed reverb bass",
            "uptempo hardtekk bass boosted edit",
        ],
    ),
    (
        "slowed_reverb",
        &[
            "slowed reverb viral tiktok edit audio",
            "super slowed reverb bass boosted tiktok",
            "aesthetic slowed reverb tiktok trend",
            "nightcore slowed reverb viral remix",
            "sad slowed reverb tiktok edit song",
            "dark slowed reverb bass boosted loop",
        ],
    ),
];

pub const EXTRA_QUERIES: &[&str] = &[
    "ultra slowed bass boosted",
    "extremely slowed reverb",
    "hardtekk edit audio",
    "montagem slowed",
    "funk brasileiro slowed tiktok",
    "sped up tiktok viral",
    "phonk edit slowed",
    "jumpstyle slowed",
    "bass boosted viral edit audio",
    "nightcore sped up viral",
    "low honor edit",
    "super slowed reverb",
];

fn pool(name: &str) -> &'static [&'static str] {
    SEARCH_POOLS
        .iter()
        .find(|(k, _)| *k == name)
        .map(|(_, v)| *v)
        .unwrap_or(SEARCH_POOLS[0].1)
}

/// SoundCloud'un `filter.created_at` değerini gün sayısına çevirir.
pub fn created_filter(max_days: f64) -> Option<&'static str> {
    if max_days <= 0.0 {
        return None;
    }
    if max_days <= 1.0 {
        Some("last_day")
    } else if max_days <= 7.0 {
        Some("last_week")
    } else if max_days <= 30.0 {
        Some("last_month")
    } else {
        Some("last_year")
    }
}

pub fn days_since(created_at: Option<&str>, now: DateTime<Utc>) -> Option<f64> {
    let raw = created_at?;
    let parsed = DateTime::parse_from_rfc3339(raw).ok()?;
    Some((now - parsed.with_timezone(&Utc)).num_seconds() as f64 / 86_400.0)
}

pub fn format_relative_time(created_at: Option<&str>, now: DateTime<Utc>) -> String {
    let Some(days) = days_since(created_at, now) else {
        return "Yeni".into();
    };
    if days < 0.0 {
        return "Yeni".into();
    }
    if days < 1.0 {
        let secs = days * 86_400.0;
        let hours = ((secs / 3600.0) as i64).max(1);
        return format!("{}s önce", hours);
    }
    format!("{}g önce", days as i64)
}

pub fn format_duration(seconds: f64) -> String {
    if seconds <= 0.0 {
        return "2:30".into();
    }
    let total = seconds as i64;
    format!("{}:{:02}", total / 60, total % 60)
}

enum JobKind {
    Query(String),
    Tag(String),
}

struct Job {
    kind: JobKind,
    offset: usize,
    curated: bool,
}

type RawMap = HashMap<String, (Track, bool, f64)>;
type TaskResult = Result<(Vec<Track>, bool), String>;

/// Aralık genişletildiğinde bakılacak en eski parça yaşı (gün).
pub const EXPAND_DAYS: f64 = 365.0;
/// Genişletmede "benzer parçalar" için tur başına tohum sayısı ve en çok tur sayısı.
const RELATED_SEEDS: usize = 8;
const RELATED_ROUNDS: usize = 2;

/// Tür/etiket süzgeciyle aranacak etiketler. Anahtar kelime aramasından çok daha isabetli:
/// aynı aralıkta etiketli parçaların dinlenme sayısı belirgin biçimde daha yüksek çıkıyor.
pub const TAG_POOLS: &[(&str, &[&str])] = &[
    ("all_viral", &["hardtekk", "phonk", "slowed"]),
    ("phonk", &["phonk"]),
    ("hardtekk", &["hardtekk"]),
    ("slowed_reverb", &["slowed"]),
];

fn tags_for(source: &str) -> &'static [&'static str] {
    TAG_POOLS
        .iter()
        .find(|(k, _)| *k == source)
        .map(|(_, v)| *v)
        .unwrap_or(&[])
}

/// Başlıklardaki süslü Unicode harfleri (𝐒𝐥𝐨𝐰𝐞𝐝, 𝘴𝘭𝘰𝘸𝘦𝘥, ｓｌｏｗｅｄ ...) düz Latin harfe çevirip küçültür.
fn fold_text(s: &str) -> String {
    s.chars()
        .flat_map(|c| {
            let u = c as u32;
            let plain = match u {
                // Matematiksel alfanümerik harfler: her stil 52 harflik blok (A-Z, a-z).
                0x1D400..=0x1D6A3 => Some((b'a' + ((u - 0x1D400) % 26) as u8) as char),
                0xFF21..=0xFF3A => Some((b'a' + (u - 0xFF21) as u8) as char),
                0xFF41..=0xFF5A => Some((b'a' + (u - 0xFF41) as u8) as char),
                _ => None,
            };
            match plain {
                Some(p) => vec![p],
                None => c.to_lowercase().collect::<Vec<char>>(),
            }
        })
        .collect()
}

/// Tür açısından güçlü anahtar kelimeler (açıklama/etiketlerde tek başına yeterli sayılır).
const STRONG_KEYWORDS: &[&str] = &[
    "hardtekk", "tekk", "phonk", "slowed", "reverb", "bass boosted", "bassboosted", "low honor",
    "jumpstyle", "krushfunk", "montagem", "sped up", "speed up", "hardstyle",
];

/// Parça bu uygulamanın aradığı türden (edit / slowed / hardtekk / phonk ...) görünüyor mu?
/// Başlıkta herhangi bir viral anahtar kelime, referans kanal, ya da açıklama/etiket/türde
/// güçlü bir anahtar kelime olmalı. Yalnızca çok dinlenmiş olmak yetmez.
pub fn is_relevant(t: &Track) -> bool {
    let title = fold_text(&t.title);
    if VIRAL_WEIGHTS.iter().any(|(kw, _)| title.contains(kw)) {
        return true;
    }
    let uploader = fold_text(&t.uploader);
    if DEFAULT_CHANNEL_NAMES.iter().any(|n| uploader.contains(n)) {
        return true;
    }
    let meta = fold_text(&format!("{} {} {}", t.tags, t.genre, t.description));
    STRONG_KEYWORDS.iter().any(|kw| meta.contains(kw))
}

/// Seçilen aralığın dışındaki (daha eski) parçalar yalnızca türe uygunsa alınır; popüler ama
/// alakasız parçalar (dizi müzikleri, pop şarkıları ...) listeye girmesin.
pub fn passes_relevance_gate(t: &Track, curated: bool, days: f64, gate_days: f64) -> bool {
    gate_days <= 0.0 || days <= gate_days || curated || is_relevant(t)
}

/// Bir parçanın aday havuzuna girip girmeyeceğine karar verir; girerse yaşını (gün) döner.
/// `window_days <= 0` ise tarih sınırı yoktur.
pub fn accept_age(t: &Track, now: DateTime<Utc>, window_days: f64) -> Option<f64> {
    if t.permalink_url.is_empty() || t.blocked || !t.streamable {
        return None;
    }
    let days = match days_since(t.created_at.as_deref(), now) {
        Some(d) => d,
        // Tarihi olmayan parça yalnızca "filtresiz" modda kabul edilir.
        None if window_days <= 0.0 => 0.0,
        None => return None,
    };
    if window_days > 0.0 && days > window_days {
        return None;
    }
    if t.duration_secs > 0.0 && (t.duration_secs < 30.0 || t.duration_secs > 600.0) {
        return None;
    }
    Some(days)
}

#[derive(Clone, Copy)]
pub struct RankParams {
    pub min_views: i64,
    pub min_score: i32,
    pub max_days: f64,
}

/// 0 = seçilen aralıkta hem dinlenme hem skor eşiğini geçen (tam ölçüt),
/// 1 = aralığın dışında (genişletilmiş) ama dinlenme ve skor eşiğini geçen,
/// 2 = dinlenme eşiğini geçen ama skoru düşük,
/// 3 = diğerleri (en çok dinlenenlerle doldurma).
pub fn tier_of(c: &Candidate, p: &RankParams) -> u8 {
    let in_window = p.max_days <= 0.0 || c.days_ago <= p.max_days;
    let views_ok = c.views >= p.min_views;
    let score_ok = c.score >= p.min_score;
    if views_ok && score_ok {
        if in_window {
            0
        } else {
            1
        }
    } else if views_ok {
        2
    } else {
        3
    }
}

/// Günlük dinlenme hızı: yeni ve çok dinlenen parça, eski ama çok dinlenenden öne geçsin.
fn velocity(views: i64, days: f64) -> f64 {
    views as f64 / days.max(7.0)
}

/// Adaylar `(aday, türe uygun mu)` çiftleridir; sıralama bittikten sonra yalnızca aday döner.
pub fn rank(mut v: Vec<(Candidate, bool)>, p: &RankParams) -> Vec<Candidate> {
    use std::cmp::Ordering;
    v.sort_by(|(a, ra), (b, rb)| {
        let (ta, tb) = (tier_of(a, p), tier_of(b, p));
        ta.cmp(&tb).then_with(|| match ta {
            // Genişletilmiş aralık: önce günlük dinlenme hızı yüksek olanlar.
            1 => velocity(b.views, b.days_ago)
                .partial_cmp(&velocity(a.views, a.days_ago))
                .unwrap_or(Ordering::Equal)
                .then(b.score.cmp(&a.score)),
            // Doldurma: önce türe uygun olanlar, sonra en çok dinlenenler (skor yalnızca eşitlik bozar).
            3 => rb.cmp(ra).then(b.views.cmp(&a.views)).then(b.score.cmp(&a.score)),
            _ => b.score.cmp(&a.score).then(b.views.cmp(&a.views)),
        })
    });
    v.into_iter().map(|(c, _)| c).collect()
}

/// Seçilen aralıkta eşiği geçen, daha önce görülmemiş parça sayısı.
fn count_big_unseen(raw: &RawMap, seen: &HashSet<String>, min_views: i64) -> usize {
    raw.iter()
        .filter(|(url, (t, _, _))| t.views >= min_views && !seen.contains(*url))
        .count()
}

/// "Benzer parçalar" için tohumlar: günlük dinlenme hızı en yüksek parçalar (daha önce kullanılmayanlar).
fn pick_seeds(raw: &RawMap, used: &HashSet<String>, n: usize) -> Vec<String> {
    let mut v: Vec<(&Track, f64)> = raw
        .values()
        .map(|(t, _, days)| (t, velocity(t.views, *days)))
        .filter(|(t, _)| !t.id.is_empty() && !used.contains(&t.id))
        .collect();
    v.sort_by(|a, b| {
        b.1.partial_cmp(&a.1)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then(a.0.id.cmp(&b.0.id))
    });
    v.into_iter().take(n).map(|(t, _)| t.id.clone()).collect()
}

/// Geniş aralık (son 1 yıl) için ek arama işleri: etiketler daha isabetli olduğundan önce onlar.
fn expansion_jobs(queries: &[String], tags: &[&str]) -> Vec<Job> {
    let mut jobs = Vec::new();
    for tag in tags {
        for offset in [0usize, 50] {
            jobs.push(Job { kind: JobKind::Tag((*tag).to_string()), offset, curated: false });
        }
    }
    for q in queries.iter().take(6) {
        for offset in [0usize, 50] {
            jobs.push(Job { kind: JobKind::Query(q.clone()), offset, curated: false });
        }
    }
    jobs
}

/// Sonuç listesinin kullanıcıya gösterilen özeti.
pub fn summarize(list: &[Candidate], p: &RankParams, day_label: &str) -> String {
    if list.is_empty() {
        return "Şarkı bulunamadı. Tarih aralığını genişletmeyi deneyin.".into();
    }
    let total = list.len();
    let mut n = [0usize; 4];
    for c in list {
        n[tier_of(c, p) as usize] += 1;
    }
    if n[0] == total {
        return if p.min_views > 0 {
            format!("✓ {} şarkı bulundu (hepsi {}K+ dinlenme, {}).", total, p.min_views / 1000, day_label)
        } else {
            format!("✓ {} şarkı bulundu ({}).", total, day_label)
        };
    }

    let k = p.min_views / 1000;
    let mut parts: Vec<String> = Vec::new();
    if n[1] > 0 {
        let oldest = list
            .iter()
            .filter(|c| tier_of(c, p) == 1)
            .map(|c| c.days_ago)
            .fold(0.0f64, f64::max);
        parts.push(format!(
            "{} parça daha eski ({} güne kadar) ama {}K+ dinlenmeli ve yüksek puanlı",
            n[1],
            oldest.round() as i64,
            k
        ));
    }
    if n[2] > 0 {
        parts.push(format!("{} parça {}K+ dinlenmeli ama puanı daha düşük", n[2], k));
    }
    if n[3] > 0 {
        let lowest = list
            .iter()
            .filter(|c| tier_of(c, p) == 3)
            .map(|c| c.views)
            .min()
            .unwrap_or(0);
        parts.push(format!(
            "{} parça en çok dinlenenlerle dolduruldu (en düşük {:.1}K)",
            n[3],
            lowest as f64 / 1000.0
        ));
    }
    format!(
        "✓ {} şarkı listelendi. {} içinde {}K+ ve yüksek puanlı {} parça var; tamamlama: {}.",
        total,
        day_label,
        k,
        n[0],
        parts.join(", ")
    )
}

fn spawn_job(
    set: &mut JoinSet<TaskResult>,
    state: &Arc<AppState>,
    sem: &Arc<Semaphore>,
    job: Job,
    filter: Option<String>,
) {
    let state = Arc::clone(state);
    let sem = Arc::clone(sem);
    set.spawn(async move {
        let _permit = sem.acquire().await.ok();
        let res = match &job.kind {
            JobKind::Query(q) => state.sc.search(q, filter.as_deref(), job.offset).await,
            JobKind::Tag(t) => state.sc.search_tag(t, filter.as_deref(), job.offset).await,
        };
        res.map(|tracks| (tracks, job.curated)).map_err(|e| e.to_string())
    });
}

fn spawn_related(set: &mut JoinSet<TaskResult>, state: &Arc<AppState>, sem: &Arc<Semaphore>, track_id: String) {
    let state = Arc::clone(state);
    let sem = Arc::clone(sem);
    set.spawn(async move {
        let _permit = sem.acquire().await.ok();
        state
            .sc
            .related(&track_id, 50)
            .await
            .map(|tracks| (tracks, false))
            .map_err(|e| e.to_string())
    });
}

struct Drained {
    cancelled: bool,
    errors: usize,
}

/// Verilen işlerin sonuçlarını toplar; ilerlemeyi günceller ve iptali izler.
async fn drain(
    state: &Arc<AppState>,
    mut set: JoinSet<TaskResult>,
    raw: &mut RawMap,
    now: DateTime<Utc>,
    window_days: f64,
    gate_days: f64,
    stage: &str,
    progress: (f32, f32),
) -> Drained {
    use std::sync::atomic::Ordering;

    let total = set.len().max(1);
    let mut errors = 0usize;
    let mut done = 0usize;
    let mut cancel_poll = tokio::time::interval(std::time::Duration::from_millis(120));

    loop {
        if state.cancel_scan.load(Ordering::SeqCst) {
            set.abort_all();
            return Drained { cancelled: true, errors };
        }
        let next = tokio::select! {
            res = set.join_next() => res,
            _ = cancel_poll.tick() => continue,
        };
        let Some(joined) = next else { break };
        done += 1;

        {
            let mut c = state.curator.write().await;
            c.batch_index = done;
            c.progress = progress.0 + (done as f32 / total as f32) * (progress.1 - progress.0);
            c.stage = format!("{} {}/{} ({} parça)", stage, done, total, raw.len());
        }

        let Ok(result) = joined else {
            errors += 1;
            continue;
        };
        let (tracks, curated) = match result {
            Ok(v) => v,
            Err(_) => {
                errors += 1;
                continue;
            }
        };

        for t in tracks {
            if raw.contains_key(&t.permalink_url) {
                continue;
            }
            let Some(days) = accept_age(&t, now, window_days) else {
                continue;
            };
            if !passes_relevance_gate(&t, curated, days, gate_days) {
                continue;
            }
            raw.insert(t.permalink_url.clone(), (t, curated, days));
        }
    }
    Drained { cancelled: false, errors }
}

#[allow(clippy::too_many_arguments)]
pub async fn run_scan(
    state: Arc<AppState>,
    source_type: String,
    custom_input: String,
    min_score: i32,
    target_count: usize,
    max_days: f64,
    min_views: i64,
    expand: bool,
) -> Result<()> {
    use std::sync::atomic::Ordering;

    state.cancel_scan.store(false, Ordering::SeqCst);
    {
        let mut c = state.curator.write().await;
        c.scanning = true;
        c.candidates.clear();
        c.error = None;
        c.progress = 0.05;
        c.stage = "Kaynaklar hazırlanıyor".into();
        c.current.clear();
        c.current_url.clear();
    }

    let day_label = if max_days > 0.0 {
        format!("son {} gün", max_days as i64)
    } else {
        "tüm zamanlar".into()
    };
    state
        .set_log(format!(
            "AI Küratör taranıyor ({}, {} şarkı)...",
            day_label, target_count
        ))
        .await;

    let now = Utc::now();
    let filter = created_filter(max_days);
    let seen_snapshot = state.seen.read().await.clone();
    // Genişletme açıkken seçilen aralığın dışındaki (daha eski) parçalar da havuza alınır;
    // sıralamada aralık içindekiler her zaman önce gelir.
    let window_days = if max_days <= 0.0 {
        0.0
    } else if expand {
        max_days.max(EXPAND_DAYS)
    } else {
        max_days
    };

    // --- İş listesini kur ---
    let mut jobs: Vec<Job> = Vec::new();
    let mut queries: Vec<String> = Vec::new();
    let mut channel_urls: Vec<String> = Vec::new();
    let custom_is_url = custom_input.trim().starts_with("http");

    // "Beğenilerim": giriş yapılmışsa hesabın beğenileri; değilse kullanıcının
    // verdiği profil linkinin herkese açık beğenileri (giriş gerekmez).
    let mut likes_user: Option<String> = None;
    if source_type == "my_likes" {
        let auth = state.auth.read().await.clone();
        if !auth.user_id.is_empty() {
            likes_user = Some(auth.user_id);
        } else if custom_is_url {
            let profile = custom_input
                .trim()
                .split(['?', '#'])
                .next()
                .unwrap_or("")
                .trim_end_matches('/')
                .trim_end_matches("/likes")
                .to_string();
            channel_urls = vec![format!("{}/likes", profile)];
        } else {
            let mut c = state.curator.write().await;
            c.scanning = false;
            c.log = "Beğenileri taramak için SoundCloud profil linkinizi girin \
                     (ör. https://soundcloud.com/kullanici-adi)."
                .into();
            c.error = Some("Profil linki girilmedi.".into());
            return Ok(());
        }
    }

    if source_type == "my_likes" {
        // Arama sorgusu yok; beğeniler ayrı bir görev olarak ekleniyor.
    } else if source_type == "curated_creators" {
        channel_urls = state.cfg.read().await.channels.clone();
    } else if source_type == "custom_url" && custom_is_url {
        channel_urls = vec![custom_input.trim().to_string()];
    } else {
        queries = if source_type == "custom_url" {
            vec![custom_input.trim().to_string()]
        } else {
            let mut q: Vec<String> = pool(&source_type).iter().map(|s| s.to_string()).collect();
            for extra in EXTRA_QUERIES {
                if !q.iter().any(|x| x == extra) {
                    q.push((*extra).to_string());
                }
            }
            q
        };

        for q in &queries {
            for offset in [0usize, 50, 100] {
                jobs.push(Job { kind: JobKind::Query(q.clone()), offset, curated: false });
            }
        }
        for tag in tags_for(&source_type) {
            for offset in [0usize, 50, 100] {
                jobs.push(Job { kind: JobKind::Tag((*tag).to_string()), offset, curated: false });
            }
        }
    }

    // Referans kanal bonusu yalnızca küratörlü kanallardan gelenlerde uygulanır
    // (orijinal davranış: özel link ve aramalar bu bonusu almaz).
    let curated_flag = source_type == "curated_creators";

    // --- Kanal işlerini paralel çalıştır ---
    let sem = Arc::new(Semaphore::new(6));
    let mut set: JoinSet<TaskResult> = JoinSet::new();

    for url in channel_urls {
        let state = Arc::clone(&state);
        let sem = Arc::clone(&sem);
        set.spawn(async move {
            let _permit = sem.acquire().await.ok();
            state
                .sc
                .tracks_from_url(&url)
                .await
                .map(|tracks| (tracks, curated_flag))
                .map_err(|e| e.to_string())
        });
    }

    if let Some(uid) = likes_user {
        let state = Arc::clone(&state);
        let sem = Arc::clone(&sem);
        set.spawn(async move {
            let _permit = sem.acquire().await.ok();
            state
                .sc
                .user_likes(&uid, 50)
                .await
                .map(|tracks| (tracks, false))
                .map_err(|e| e.to_string())
        });
    }

    for job in jobs {
        spawn_job(&mut set, &state, &sem, job, filter.map(str::to_string));
    }

    let total_tasks = set.len().max(1);
    {
        let mut c = state.curator.write().await;
        c.log = format!("{} kaynak paralel taranıyor...", total_tasks);
        c.stage = format!("Kaynaklar 0/{}", total_tasks);
        c.batch_index = 0;
        c.batch_total = total_tasks;
        c.progress = 0.08;
    }

    // --- Sonuçları topla ---
    let mut raw: RawMap = HashMap::new();
    let first = drain(&state, set, &mut raw, now, window_days, max_days, "Kaynaklar", (0.08, 0.88)).await;
    let mut source_errors = first.errors;
    let mut cancelled = first.cancelled;

    // --- Genişletme: seçilen aralıkta yeterli popüler parça yoksa ---
    // Yeni parça azaldıkça listeler en az dinlenenlerle doluyordu. Burada önce "benzer parçalar"
    // (SoundCloud'un öneri listesi) ve son 1 yıllık etiket/anahtar kelime aramaları taranır.
    let searchy = !queries.is_empty();
    let mut expanded_rounds = 0usize;
    if expand && max_days > 0.0 && searchy && !cancelled {
        let mut used_seeds: HashSet<String> = HashSet::new();
        for round in 0..RELATED_ROUNDS {
            if count_big_unseen(&raw, &seen_snapshot, min_views) >= target_count {
                break;
            }
            let mut set: JoinSet<TaskResult> = JoinSet::new();
            if round == 0 {
                for job in expansion_jobs(&queries, tags_for(&source_type)) {
                    spawn_job(&mut set, &state, &sem, job, Some("last_year".to_string()));
                }
            }
            for id in pick_seeds(&raw, &used_seeds, RELATED_SEEDS) {
                used_seeds.insert(id.clone());
                spawn_related(&mut set, &state, &sem, id);
            }
            if set.is_empty() {
                break;
            }
            expanded_rounds += 1;
            {
                let mut c = state.curator.write().await;
                c.log = format!(
                    "{} içinde yeterli popüler parça yok; benzer ve daha eski parçalar taranıyor...",
                    day_label
                );
                c.stage = "Aralık genişletiliyor".into();
                c.batch_index = 0;
                c.batch_total = set.len();
                c.progress = 0.88;
            }
            let d = drain(&state, set, &mut raw, now, window_days, max_days, "Genişletiliyor", (0.88, 0.92)).await;
            source_errors += d.errors;
            if d.cancelled {
                cancelled = true;
                break;
            }
        }
    }
    let _ = expanded_rounds;

    if cancelled {
        let mut c = state.curator.write().await;
        c.scanning = false;
        c.progress = 0.0;
        c.batch_index = 0;
        c.batch_total = 0;
        c.stage.clear();
        c.log = "Tarama durduruldu.".into();
        return Ok(());
    }

    if raw.is_empty() {
        let mut c = state.curator.write().await;
        c.scanning = false;
        c.progress = 0.0;
        c.batch_index = 0;
        c.batch_total = 0;
        c.stage.clear();
        c.log = if source_errors > 0 {
            format!(
                "Hiç sonuç alınamadı ({} kaynak hata verdi). Tarih aralığını genişletmeyi deneyin.",
                source_errors
            )
        } else {
            "Şarkı bulunamadı. Tarih aralığını genişletmeyi deneyin.".into()
        };
        return Ok(());
    }

    {
        let mut c = state.curator.write().await;
        c.stage = "AI puanlama".into();
        c.progress = 0.92;
    }

    // --- Daha önce görülenleri ele ---
    let mut fresh: RawMap = raw
        .iter()
        .filter(|(url, _)| !seen_snapshot.contains(*url))
        .map(|(k, v)| (k.clone(), v.clone()))
        .collect();

    if fresh.len() < target_count {
        for (url, v) in raw.iter() {
            fresh.entry(url.clone()).or_insert_with(|| v.clone());
        }
    }

    // --- Puanla ---
    let mut scored: Vec<(Candidate, bool)> = Vec::with_capacity(fresh.len());
    for (url, (t, curated, days)) in fresh {
        let score_input = ScoreInput {
            title: t.title.clone(),
            uploader: t.uploader.clone(),
            description: t.description.clone(),
            duration: t.duration_secs,
            view_count: t.views,
            like_count: t.likes,
            repost_count: t.reposts,
            is_from_curated: curated,
        };
        let mut score = score_track(&score_input);
        if days <= 2.0 {
            score.total += 15;
            score.reasons.push("Çok Yeni (+15)".into());
        } else if days <= 7.0 {
            score.total += 10;
            score.reasons.push("Son 1 Hafta (+10)".into());
        }

        let clamped = score.total.clamp(40, 99);
        let thumbnail = t
            .artwork_url
            .clone()
            .unwrap_or_else(|| "/static/icon.png".to_string());

        let relevant = curated || is_relevant(&t);
        let cand = Candidate {
            id: t.id.clone(),
            title: t.title.clone(),
            uploader: t.uploader.clone(),
            url,
            thumbnail,
            duration_str: format_duration(t.duration_secs),
            date_str: format_relative_time(t.created_at.as_deref(), now),
            days_ago: (days * 10.0).round() / 10.0,
            views: t.views,
            likes: t.likes,
            score: clamped,
            reasons: score.reasons.iter().take(3).cloned().collect(),
        };
        scored.push((cand, relevant));
    }

    let params = RankParams { min_views, min_score, max_days };
    let final_list: Vec<Candidate> = rank(scored, &params).into_iter().take(target_count).collect();
    let summary = summarize(&final_list, &params, &day_label);

    // --- Görüldü olarak işaretle ---
    {
        let mut seen = state.seen.write().await;
        for c in &final_list {
            seen.insert(c.url.clone());
        }
        save_seen(&seen);
    }

    let mut c = state.curator.write().await;
    c.scanning = false;
    c.progress = 1.0;
    c.batch_index = 0;
    c.batch_total = 0;
    c.stage.clear();
    c.candidates = final_list;
    c.seen_count = state.seen.read().await.len();
    c.log = summary;

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn track(id: &str, views: i64, created: Option<&str>) -> Track {
        Track {
            id: id.into(),
            title: format!("t{id}"),
            uploader: "u".into(),
            permalink_url: format!("https://soundcloud.com/u/{id}"),
            duration_secs: 120.0,
            views,
            likes: 0,
            reposts: 0,
            artwork_url: None,
            created_at: created.map(str::to_string),
            description: String::new(),
            genre: String::new(),
            tags: String::new(),
            streamable: true,
            blocked: false,
            transcodings: Vec::new(),
            track_authorization: String::new(),
        }
    }

    fn cand(id: &str, views: i64, score: i32, days: f64) -> Candidate {
        Candidate {
            id: id.into(),
            title: id.into(),
            uploader: "u".into(),
            url: format!("https://soundcloud.com/u/{id}"),
            thumbnail: String::new(),
            duration_str: "2:00".into(),
            date_str: String::new(),
            days_ago: days,
            views,
            likes: 0,
            score,
            reasons: Vec::new(),
        }
    }

    /// `rank` girdisi: (aday, türe uygun mu)
    fn rc(id: &str, views: i64, score: i32, days: f64, relevant: bool) -> (Candidate, bool) {
        (cand(id, views, score, days), relevant)
    }

    fn params() -> RankParams {
        RankParams { min_views: 100_000, min_score: 85, max_days: 14.0 }
    }

    fn ids(v: &[Candidate]) -> Vec<&str> {
        v.iter().map(|c| c.id.as_str()).collect()
    }

    fn iso(now: DateTime<Utc>, days_ago: f64) -> String {
        (now - chrono::Duration::seconds((days_ago * 86_400.0) as i64)).to_rfc3339()
    }

    #[test]
    fn accept_age_applies_window_duration_and_flags() {
        let now = Utc::now();
        let old = iso(now, 40.0);
        let fresh = iso(now, 3.0);
        assert!((accept_age(&track("a", 1, Some(&fresh)), now, 14.0).unwrap() - 3.0).abs() < 0.01);
        assert!(accept_age(&track("a", 1, Some(&old)), now, 14.0).is_none(), "pencere dışı");
        assert!(accept_age(&track("a", 1, Some(&old)), now, 365.0).is_some(), "geniş pencerede kabul");
        assert!(accept_age(&track("a", 1, Some(&old)), now, 0.0).is_some(), "sınırsız");
        // tarihsiz: yalnızca sınırsız modda
        assert!(accept_age(&track("a", 1, None), now, 14.0).is_none());
        assert_eq!(accept_age(&track("a", 1, None), now, 0.0), Some(0.0));
        // süre / engelli / akışsız / adressiz
        let mut t = track("a", 1, Some(&fresh));
        t.duration_secs = 20.0;
        assert!(accept_age(&t, now, 14.0).is_none());
        t.duration_secs = 700.0;
        assert!(accept_age(&t, now, 14.0).is_none());
        let mut t = track("a", 1, Some(&fresh));
        t.blocked = true;
        assert!(accept_age(&t, now, 14.0).is_none());
        let mut t = track("a", 1, Some(&fresh));
        t.streamable = false;
        assert!(accept_age(&t, now, 14.0).is_none());
        let mut t = track("a", 1, Some(&fresh));
        t.permalink_url.clear();
        assert!(accept_age(&t, now, 14.0).is_none());
    }

    #[test]
    fn tiers_follow_window_views_and_score() {
        let p = params();
        assert_eq!(tier_of(&cand("a", 200_000, 90, 5.0), &p), 0);
        assert_eq!(tier_of(&cand("a", 200_000, 90, 60.0), &p), 1, "aralık dışı ama eşiği geçiyor");
        assert_eq!(tier_of(&cand("a", 200_000, 70, 5.0), &p), 2, "skor düşük");
        assert_eq!(tier_of(&cand("a", 5_000, 99, 1.0), &p), 3, "dinlenme düşük");
        // sınırsız aralıkta "aralık dışı" yoktur
        let all = RankParams { max_days: 0.0, ..p };
        assert_eq!(tier_of(&cand("a", 200_000, 90, 900.0), &all), 0);
        // dinlenme eşiği 0 ise düşük dinlenme katmanı oluşmaz
        let no_views = RankParams { min_views: 0, ..p };
        assert_eq!(tier_of(&cand("a", 3, 50, 1.0), &no_views), 2);
    }

    #[test]
    fn rank_puts_exact_matches_first_then_fast_older_hits_then_most_listened_fill() {
        let p = params();
        let list = vec![
            rc("low_new", 40, 60, 0.2, true),         // doldurma: çok yeni ama kimse dinlememiş
            rc("low_best", 9_000, 55, 10.0, true),    // doldurma: en çok dinlenen
            rc("old_slow", 400_000, 95, 300.0, true), // genişletilmiş: yavaş (günde ~1.3K)
            rc("old_fast", 300_000, 90, 20.0, true),  // genişletilmiş: hızlı (günde 15K)
            rc("exact", 150_000, 92, 4.0, true),      // tam ölçüt
            rc("big_lowscore", 500_000, 60, 3.0, true),
        ];
        let out = rank(list, &p);
        assert_eq!(ids(&out), vec!["exact", "old_fast", "old_slow", "big_lowscore", "low_best", "low_new"]);
    }

    #[test]
    fn fill_is_sorted_by_views_not_by_freshness_bonus() {
        // Eskiden doldurma skora göre sıralanıyordu: "Çok Yeni" bonusu alan, hiç dinlenmemiş
        // parçalar en çok dinlenenin önüne geçiyordu.
        let p = params();
        let out = rank(vec![rc("fresh_dead", 30, 70, 0.1, true), rc("popular", 8_000, 45, 12.0, true)], &p);
        assert_eq!(ids(&out), vec!["popular", "fresh_dead"]);
    }

    #[test]
    fn fill_prefers_on_genre_tracks_over_more_listened_off_genre_ones() {
        let p = params();
        let out = rank(
            vec![
                rc("generic_pop", 40_000, 40, 5.0, false),
                rc("edit_small", 3_000, 60, 5.0, true),
                rc("edit_bigger", 9_000, 60, 5.0, true),
            ],
            &p,
        );
        assert_eq!(ids(&out), vec!["edit_bigger", "edit_small", "generic_pop"]);
    }

    #[test]
    fn fancy_unicode_titles_are_folded_to_plain_letters() {
        assert_eq!(fold_text("𝐖𝐨𝐫𝐫𝐲 (𝐒𝐥𝐨𝐰𝐞𝐝)"), "worry (slowed)");
        assert_eq!(fold_text("𝘴𝘯𝘰𝘸𝘻𝘺𝘻𝘻"), "snowzyzz");
        assert_eq!(fold_text("ＨＡＲＤＴＥＫＫ ｅｄｉｔ"), "hardtekk edit");
        assert_eq!(fold_text("Ural Mountains"), "ural mountains");
    }

    #[test]
    fn relevance_needs_genre_signals_not_just_views() {
        let mut t = track("a", 5_000_000, None);
        t.title = "Alvida Alvida | Dar-E-Nijaat | OST".into();
        assert!(!is_relevant(&t), "popüler ama alakasız dizi müziği");
        t.title = "Guzarish by Satinder Sartaaj".into();
        assert!(!is_relevant(&t));
        t.title = "TIKI TIKI (Slowed)".into();
        assert!(is_relevant(&t));
        t.title = "𝐖𝐨𝐫𝐫𝐲 (𝐒𝐥𝐨𝐰𝐞𝐝 𝐓𝐨 𝐏𝐞𝐫𝐟𝐞𝐜𝐭𝐢𝐨𝐧)".into();
        assert!(is_relevant(&t), "süslü harfli başlık");
        // başlıkta yok ama etiket/açıklamada güçlü anahtar kelime var
        t.title = "ural mountains".into();
        assert!(!is_relevant(&t));
        t.tags = "viral fyp hardtekk".into();
        assert!(is_relevant(&t));
        t.tags.clear();
        t.description = "best part looped, slowed + reverb".into();
        assert!(is_relevant(&t));
        // referans kanal
        t.description.clear();
        t.uploader = "Phonkinho".into();
        assert!(is_relevant(&t));
    }

    #[test]
    fn relevance_gate_only_applies_beyond_the_chosen_window() {
        let mut off = track("a", 5_000_000, None);
        off.title = "Bairan - Banjaare Viral song".into();
        // aralık içinde: eskisi gibi kapı yok
        assert!(passes_relevance_gate(&off, false, 5.0, 14.0));
        // aralık dışında alakasızsa elenir, alakalıysa girer
        assert!(!passes_relevance_gate(&off, false, 100.0, 14.0));
        let mut on = off.clone();
        on.title = "montagem x (slowed)".into();
        assert!(passes_relevance_gate(&on, false, 100.0, 14.0));
        // küratörlü kanal her zaman girer; tarih sınırı yoksa kapı da yok
        assert!(passes_relevance_gate(&off, true, 100.0, 14.0));
        assert!(passes_relevance_gate(&off, false, 900.0, 0.0));
    }

    #[test]
    fn summarize_describes_what_the_list_contains() {
        let p = params();
        assert_eq!(summarize(&[], &p, "son 14 gün"), "Şarkı bulunamadı. Tarih aralığını genişletmeyi deneyin.");
        let all_exact = vec![cand("a", 150_000, 92, 3.0), cand("b", 120_000, 90, 5.0)];
        assert!(summarize(&all_exact, &p, "son 14 gün").contains("hepsi 100K+ dinlenme"));
        let mixed = vec![
            cand("a", 150_000, 92, 3.0),
            cand("b", 300_000, 90, 120.0),
            cand("c", 2_500, 50, 1.0),
        ];
        let s = summarize(&mixed, &p, "son 14 gün");
        assert!(s.contains("3 şarkı listelendi"), "{s}");
        assert!(s.contains("yüksek puanlı 1 parça var"), "{s}");
        assert!(s.contains("1 parça daha eski (120 güne kadar)"), "{s}");
        assert!(s.contains("en düşük 2.5K"), "{s}");
    }

    #[test]
    fn related_seeds_prefer_fast_recent_hits_and_skip_used_ones() {
        let mut raw: RawMap = HashMap::new();
        let mut put = |id: &str, views: i64, days: f64| {
            let t = track(id, views, None);
            raw.insert(t.permalink_url.clone(), (t, false, days));
        };
        put("slow_mega", 2_000_000, 300.0); // günde ~6.7K
        put("fast_new", 300_000, 10.0);     // günde 30K
        put("mid", 90_000, 30.0);           // günde 3K
        put("tiny", 100, 1.0);
        let none = HashSet::new();
        assert_eq!(pick_seeds(&raw, &none, 2), vec!["fast_new", "slow_mega"]);
        let used: HashSet<String> = ["fast_new".to_string()].into_iter().collect();
        assert_eq!(pick_seeds(&raw, &used, 2), vec!["slow_mega", "mid"]);
    }

    #[test]
    fn big_unseen_counts_only_unseen_tracks_above_the_threshold() {
        let mut raw: RawMap = HashMap::new();
        for (id, v) in [("a", 200_000), ("b", 150_000), ("c", 10_000)] {
            let t = track(id, v, None);
            raw.insert(t.permalink_url.clone(), (t, false, 5.0));
        }
        let mut seen = HashSet::new();
        assert_eq!(count_big_unseen(&raw, &seen, 100_000), 2);
        seen.insert("https://soundcloud.com/u/a".to_string());
        assert_eq!(count_big_unseen(&raw, &seen, 100_000), 1);
        assert_eq!(count_big_unseen(&raw, &seen, 0), 2);
    }

    #[test]
    fn tag_pools_cover_every_search_pool() {
        for (source, _) in SEARCH_POOLS {
            assert!(!tags_for(source).is_empty(), "{source} için etiket yok");
        }
        assert!(tags_for("curated_creators").is_empty());
        assert!(tags_for("bilinmeyen").is_empty());
    }

    #[test]
    fn expansion_jobs_start_with_tags_and_cap_the_queries() {
        let queries: Vec<String> = (0..20).map(|i| format!("q{i}")).collect();
        let jobs = expansion_jobs(&queries, &["hardtekk", "phonk"]);
        assert_eq!(jobs.len(), 2 * 2 + 6 * 2);
        assert!(matches!(jobs[0].kind, JobKind::Tag(_)));
        assert!(matches!(jobs.last().unwrap().kind, JobKind::Query(_)));
    }
}
