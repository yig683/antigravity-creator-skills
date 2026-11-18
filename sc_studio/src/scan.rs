//! "Yeni Parçalar Keşfet & Puanla" taraması.
//!
//! Orijinal `run_ai_scan_worker`'ın portu: kaynak havuzları paralel taranır,
//! adaylar puanlanır, daha önce görülenler elenir ve sonuç listesi döner.

use crate::score::{score_track, ScoreInput};
use crate::sc::Track;
use crate::state::{save_seen, AppState, Candidate};
use anyhow::Result;
use chrono::{DateTime, Utc};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::Semaphore;

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

struct Job {
    query: String,
    offset: usize,
    curated: bool,
}

pub async fn run_scan(
    state: Arc<AppState>,
    source_type: String,
    custom_input: String,
    min_score: i32,
    target_count: usize,
    max_days: f64,
    min_views: i64,
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

    let cfg = state.cfg.read().await.clone();
    let now = Utc::now();
    let filter = created_filter(max_days);
    let seen_snapshot = state.seen.read().await.clone();

    // --- İş listesini kur ---
    let mut jobs: Vec<Job> = Vec::new();
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
        channel_urls = cfg.channels.clone();
    } else if source_type == "custom_url" && custom_is_url {
        channel_urls = vec![custom_input.trim().to_string()];
    } else {
        let queries: Vec<String> = if source_type == "custom_url" {
            vec![custom_input.trim().to_string()]
        } else if source_type == "curated_creators" {
            pool("all_viral").iter().take(4).map(|s| s.to_string()).collect()
        } else {
            let mut q: Vec<String> = pool(&source_type).iter().map(|s| s.to_string()).collect();
            for extra in EXTRA_QUERIES {
                if !q.iter().any(|x| x == extra) {
                    q.push((*extra).to_string());
                }
            }
            q
        };

        for q in queries {
            for offset in [0usize, 50, 100] {
                jobs.push(Job {
                    query: q.clone(),
                    offset,
                    curated: false,
                });
            }
        }
    }

    // Referans kanal bonusu yalnızca küratörlü kanallardan gelenlerde uygulanır
    // (orijinal davranış: özel link ve aramalar bu bonusu almaz).
    let curated_flag = source_type == "curated_creators";

    // --- Kanal işlerini paralel çalıştır ---
    let sem = Arc::new(Semaphore::new(6));
    let mut set: tokio::task::JoinSet<Result<(Vec<Track>, bool), String>> = tokio::task::JoinSet::new();

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
        let state = Arc::clone(&state);
        let sem = Arc::clone(&sem);
        let filter = filter.map(str::to_string);
        set.spawn(async move {
            let _permit = sem.acquire().await.ok();
            state
                .sc
                .search(&job.query, filter.as_deref(), job.offset)
                .await
                .map(|tracks| (tracks, job.curated))
                .map_err(|e| e.to_string())
        });
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
    let mut raw: HashMap<String, (Track, bool, f64)> = HashMap::new();
    let mut source_errors = 0usize;
    let mut done_tasks = 0usize;
    let mut cancelled = false;
    let mut cancel_poll = tokio::time::interval(std::time::Duration::from_millis(120));

    loop {
        if state.cancel_scan.load(Ordering::SeqCst) {
            cancelled = true;
            set.abort_all();
            break;
        }
        let next = tokio::select! {
            res = set.join_next() => res,
            _ = cancel_poll.tick() => {
                if state.cancel_scan.load(Ordering::SeqCst) {
                    cancelled = true;
                    set.abort_all();
                    break;
                }
                continue;
            }
        };
        let Some(joined) = next else { break };
        done_tasks += 1;

        {
            let mut c = state.curator.write().await;
            c.batch_index = done_tasks;
            c.progress = 0.08 + (done_tasks as f32 / total_tasks as f32) * 0.80;
            c.stage = format!("Kaynaklar {}/{} ({} parça)", done_tasks, total_tasks, raw.len());
        }

        let Ok(result) = joined else {
            source_errors += 1;
            continue;
        };
        let (tracks, curated) = match result {
            Ok(v) => v,
            Err(_) => {
                source_errors += 1;
                continue;
            }
        };

        for t in tracks {
            if t.permalink_url.is_empty() || raw.contains_key(&t.permalink_url) {
                continue;
            }
            if t.blocked || !t.streamable {
                continue;
            }
            let days = match days_since(t.created_at.as_deref(), now) {
                Some(d) => d,
                // Tarihi olmayan parça yalnızca "filtresiz" modda kabul edilir.
                None if max_days <= 0.0 => 0.0,
                None => continue,
            };
            if max_days > 0.0 && days > max_days {
                continue;
            }
            if t.duration_secs > 0.0 && (t.duration_secs < 30.0 || t.duration_secs > 600.0) {
                continue;
            }
            raw.insert(t.permalink_url.clone(), (t, curated, days));
        }
    }

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
    let mut fresh: HashMap<String, (Track, bool, f64)> = raw
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
    let mut scored: Vec<Candidate> = Vec::with_capacity(fresh.len());
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

        scored.push(Candidate {
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
        });
    }

    // Tier: 0 = hem dinlenme hem skor eşiğini geçen, 1 = sadece dinlenme, 2 = diğerleri
    let tier = |c: &Candidate| -> u8 {
        if c.views >= min_views && c.score >= min_score {
            0
        } else if c.views >= min_views {
            1
        } else {
            2
        }
    };

    scored.sort_by(|a, b| {
        tier(a)
            .cmp(&tier(b))
            .then(b.score.cmp(&a.score))
            .then(b.views.cmp(&a.views))
    });

    let final_list: Vec<Candidate> = scored.into_iter().take(target_count).collect();
    // "Katı" sayım, listeye girenler üzerinden yapılır (orijinal davranış).
    let strict = final_list.iter().filter(|c| tier(c) == 0).count();
    let lowest_views = final_list.iter().map(|c| c.views).min().unwrap_or(0);

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
    c.candidates = final_list.clone();
    c.seen_count = state.seen.read().await.len();

    c.log = if final_list.is_empty() {
        "Şarkı bulunamadı. Tarih aralığını genişletmeyi deneyin.".into()
    } else if strict == final_list.len() {
        if min_views > 0 {
            format!(
                "✓ {} şarkı bulundu (hepsi {}K+ dinlenme, {}).",
                final_list.len(),
                min_views / 1000,
                day_label
            )
        } else {
            format!(
                "✓ {} şarkı bulundu ({}).",
                final_list.len(),
                day_label
            )
        }
    } else {
        format!(
            "✓ {} şarkı listelendi. {} içinde {}K+ olan yalnızca {} parça var; \
             kalanlar en çok dinlenenlerle dolduruldu (en düşük {:.1}K).",
            final_list.len(),
            day_label,
            min_views / 1000,
            strict,
            lowest_views as f64 / 1000.0
        )
    };

    Ok(())
}
