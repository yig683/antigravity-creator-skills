//! "AI Küratör" puanlama motoru.
//!
//! Orijinal `ai_curator.py`'nin birebir portu; ağırlıklar ve eşikler
//! değiştirilmedi ki mevcut kullanıcıların alıştığı sıralama korunsun.

use serde::Serialize;

pub const VIRAL_WEIGHTS: &[(&str, i32)] = &[
    ("hardtekk", 38),
    ("slowed", 28),
    ("reverb", 28),
    ("phonk", 32),
    ("super slowed", 35),
    ("ultra slowed", 35),
    ("bass boosted", 30),
    ("bassboosted", 30),
    ("tik tok", 25),
    ("tiktok", 25),
    ("montagem", 30),
    ("brazilian", 22),
    ("funk", 20),
    ("sped up", 22),
    ("speed up", 22),
    ("hardstyle", 25),
    ("drill", 22),
    ("edit", 18),
    ("low honor", 35),
    ("jumpstyle", 28),
    ("krushfunk", 28),
];

pub const NEGATIVE_WEIGHTS: &[(&str, i32)] = &[
    ("1 hour", -70),
    ("10 hours", -70),
    ("full album", -60),
    ("podcast", -70),
    ("interview", -60),
    ("official video", -30),
    ("karaoke", -50),
    ("tutorial", -60),
    ("lofi study", -40),
];

pub const DEFAULT_CHANNEL_NAMES: &[&str] = &[
    "phonkinho",
    "arda doğan",
    "arda dogan",
    "big chunk",
    "bora",
    "low honor",
    "me0o0",
    "kewzy",
    "d3n_z",
    "userkyuv",
    "reverox",
    "jigsawdaemon",
];

#[derive(Debug, Clone, Default)]
pub struct ScoreInput {
    pub title: String,
    pub uploader: String,
    pub description: String,
    pub duration: f64,
    pub view_count: i64,
    pub like_count: i64,
    pub repost_count: i64,
    pub is_from_curated: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct Score {
    pub total: i32,
    pub reasons: Vec<String>,
}

/// Bir parçanın TikTok/Reels edit vibe'ına uygunluğunu çok boyutlu puanlar.
pub fn score_track(input: &ScoreInput) -> Score {
    let title = input.title.to_lowercase();
    let uploader = input.uploader.to_lowercase();
    let description = input.description.to_lowercase();
    let duration = input.duration;
    let views = input.view_count;
    let likes = input.like_count;
    let reposts = input.repost_count;

    let mut score: i32 = 0;
    let mut reasons: Vec<String> = Vec::new();

    // 1) Referans kanal bonusu
    let from_reference = input.is_from_curated
        || DEFAULT_CHANNEL_NAMES
            .iter()
            .any(|name| uploader.contains(name));
    if from_reference {
        score += 40;
        reasons.push("Referans Kanal (+40)".into());
    }

    // 2) Viral anahtar kelimeler
    let mut matched_positives = 0usize;
    let mut kw_score: i32 = 0;
    for (kw, weight) in VIRAL_WEIGHTS {
        if title.contains(kw) {
            kw_score += weight;
            reasons.push(format!("{} (+{})", kw.to_uppercase(), weight));
            matched_positives += 1;
        } else if matched_positives < 2 && description.contains(kw) {
            let half = weight / 2;
            kw_score += half;
            reasons.push(format!("Etiket:{} (+{})", kw, half));
            matched_positives += 1;
        }
    }

    if matched_positives >= 3 {
        kw_score += 15;
        reasons.push("Çoklu Edit Kombo (+15)".into());
    } else if matched_positives == 2 {
        kw_score += 8;
        reasons.push("İkili Edit Uyumu (+8)".into());
    }
    score += kw_score.min(45);

    // 3) Olumsuz anahtar kelimeler
    for (nkw, nweight) in NEGATIVE_WEIGHTS {
        if title.contains(nkw) {
            score += nweight;
            reasons.push(format!("Elendi:{} ({})", nkw, nweight));
        }
    }

    // 4) Süre
    if (50.0..=270.0).contains(&duration) {
        score += 10;
        reasons.push("İdeal Süre (+10)".into());
    } else if duration > 500.0 {
        score -= 45;
        reasons.push("Çok Uzun (-45)".into());
    } else if duration > 0.0 && duration < 30.0 {
        score -= 25;
        reasons.push("Çok Kısa (-25)".into());
    }

    // 5) Dinlenme kademeleri
    let k = views / 1000;
    if views >= 1_000_000 {
        score += 85;
        reasons.push("1M+ Mega Hit (+85)".into());
    } else if views >= 500_000 {
        score += 70;
        reasons.push(format!("{}K Zirve Hit (+70)", k));
    } else if views >= 200_000 {
        score += 55;
        reasons.push(format!("{}K Büyük Hit (+55)", k));
    } else if views >= 100_000 {
        score += 45;
        reasons.push(format!("{}K Hit (+45)", k));
    } else if views >= 50_000 {
        score += 35;
        reasons.push(format!("{}K Viral (+35)", k));
    } else if views >= 20_000 {
        score += 20;
        reasons.push(format!("{}K Dinlenme (+20)", k));
    } else if views >= 10_000 {
        score += 10;
        reasons.push(format!("{}K Dinlenme (+10)", k));
    } else if views < 3_000 {
        score -= 45;
        reasons.push("Düşük Dinlenme (-45)".into());
    } else if views < 1_000 {
        score -= 75;
        reasons.push("Ölü Dinlenme (-75)".into());
    }

    // 6) Beğeni kademeleri
    if likes >= 5_000 {
        score += 25;
        reasons.push("5K+ Beğeni (+25)".into());
    } else if likes >= 2_000 {
        score += 15;
        reasons.push("2K+ Beğeni (+15)".into());
    } else if likes >= 500 {
        score += 10;
        reasons.push("500+ Beğeni (+10)".into());
    }

    // 7) Beğeni oranı
    if views > 300 && likes > 0 {
        let like_ratio = likes as f64 / views as f64 * 100.0;
        if like_ratio >= 3.0 {
            score += 15;
            reasons.push(format!("Süper Beğeni Oranı %{:.1} (+15)", like_ratio));
        } else if like_ratio >= 1.8 {
            score += 8;
            reasons.push(format!("İyi Beğeni Oranı %{:.1} (+8)", like_ratio));
        }
    }

    // 8) Repost
    if reposts >= 50 {
        score += 10;
        reasons.push(format!("Yüksek Repost ({}) (+10)", reposts));
    }

    Score {
        total: score,
        reasons,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn viral_hardtekk_track_scores_high() {
        let s = score_track(&ScoreInput {
            title: "SOMETIMES HARDTEKK (Slowed + Reverb)".into(),
            uploader: "bora".into(),
            duration: 140.0,
            view_count: 620_000,
            like_count: 9_400,
            repost_count: 80,
            ..Default::default()
        });
        assert!(s.total >= 85, "beklenen yüksek skor, gelen {}", s.total);
    }

    #[test]
    fn podcast_is_penalised() {
        let s = score_track(&ScoreInput {
            title: "Podcast 1 hour interview".into(),
            duration: 3600.0,
            view_count: 900,
            ..Default::default()
        });
        assert!(s.total < 0, "podcast elenmeliydi: {}", s.total);
    }

    #[test]
    fn kw_bonus_is_capped() {
        let s = score_track(&ScoreInput {
            title: "hardtekk slowed reverb phonk montagem brazilian funk".into(),
            duration: 100.0,
            view_count: 5_000,
            ..Default::default()
        });
        // kelime bonusu 45'te kapanır + ideal süre 10 = 55
        assert_eq!(s.total, 55);
    }
}
