//! Akıllı başlık üretimi.
//!
//! Orijinal `cover_generator.generate_smart_title` fonksiyonunun portu:
//! indirilen dosyanın ham adını temizler ve stil havuzundan rastgele bir
//! edit eki üretir. Böylece her şarkı "y2mate.com - xyz (320kbps)" gibi
//! çöp başlıklarla kalmaz.

use crate::rng::Rng;
use regex::Regex;
use std::sync::OnceLock;

pub const RANDOM_EDIT_SUFFIXES: &[&str] = &[
    "(Slowed + Reverb)",
    "[SLOWED & REVERB]",
    "(Super Slowed)",
    "[ULTRA SLOWED]",
    "(HARDTEKK EDIT)",
    "[HARDTEKK & BASS BOOSTED]",
    "(Pitched & Slowed)",
    "[LOW HONOR EDIT]",
    "(TikTok Viral Edit)",
    "(Bass Boosted Remix)",
    "[SPED UP + NIGHTCORE]",
    "(Slowed + Distorted)",
    "[BRAZILIAN PHONK EDIT]",
];

fn suffixes_for(style: &str) -> Option<&'static [&'static str]> {
    match style {
        "slowed" => Some(&["(Slowed + Reverb)", "[SLOWED & REVERB]", "(Slowed)"]),
        "hardtekk" => Some(&[
            "(HARDTEKK & BASS BOOSTED)",
            "[HARDTEKK EDIT]",
            "(Hardtekk Remix)",
        ]),
        "super_slowed" => Some(&[
            "(Super Slowed)",
            "[ULTRA SLOWED]",
            "(Super Slowed + Reverb)",
        ]),
        "phonk" => Some(&[
            "(TikTok Viral Edit)",
            "[BRAZILIAN PHONK]",
            "(Drift Phonk Edit)",
        ]),
        "pitched" => Some(&[
            "[PITCHED & SLOWED]",
            "(Pitched Slowed)",
            "[LOW HONOR EDIT]",
        ]),
        _ => None,
    }
}

struct Patterns {
    ext_strip: Regex,
    trailing_id: Regex,
    pipe_tail: Regex,
    bracket_tiktok: Regex,
    paren_tiktok: Regex,
    loop_words: Regex,
    bracket_edit: Regex,
    paren_edit: Regex,
    junk: Regex,
    seps: Regex,
    brackets: Regex,
    spaces: Regex,
    dash_tail: Regex,
    dashes: Regex,
    multi_dash: Regex,
    wtf: Regex,
}

fn patterns() -> &'static Patterns {
    static P: OnceLock<Patterns> = OnceLock::new();
    P.get_or_init(|| {
        const JUNK: &str = "(tik ?tok|viral|audio|edit|remix|even more bass|more bass|bass boosted|bassboosted|ultra slowed|super slowed|extremely slowed|slowed|reverb|sped up|speed up|nightcore|pitch boosted|pitched|distorted|brazilian phonk|brazilian|phonk|low honor|hardtekk|krushfunk|looped|loop|extended|full version|version|part|mp3|320kbps|320k)";
        Patterns {
            ext_strip: Regex::new(r"(?i)\.(mp3|wav|flac|m4a|webm|ogg)$").unwrap(),
            trailing_id: Regex::new(r"_[0-9]{6,}$").unwrap(),
            pipe_tail: Regex::new(r"\|.*$").unwrap(),
            bracket_tiktok: Regex::new(
                r"(?i)\[.*?(tiktok|viral|trend|song|full version|official).*?\]",
            )
            .unwrap(),
            paren_tiktok: Regex::new(
                r"(?i)\(.*?(tiktok|viral|trend|song|full version|official).*?\)",
            )
            .unwrap(),
            loop_words: Regex::new(
                r"(?i)\b(best part extended|best part loop|best part looped|full version|loop)\b",
            )
            .unwrap(),
            bracket_edit: Regex::new(
                r"(?i)\[.*?(slowed|reverb|hardtekk|bass boosted|sped up|speed up|pitched|krushfunk|distorted).*?\]",
            )
            .unwrap(),
            paren_edit: Regex::new(
                r"(?i)\(.*?(slowed|reverb|hardtekk|bass boosted|sped up|speed up|pitched|krushfunk|distorted).*?\)",
            )
            .unwrap(),
            junk: Regex::new(&format!(r"(?i)\b{}\b", JUNK)).unwrap(),
            seps: Regex::new(r"[+&,/]").unwrap(),
            brackets: Regex::new(r"[\(\)\[\]\{\}]").unwrap(),
            spaces: Regex::new(r"\s+").unwrap(),
            dash_tail: Regex::new(r"(?:\s-)+$").unwrap(),
            dashes: Regex::new(r"[-_]+").unwrap(),
            multi_dash: Regex::new(r"(?:\s*-\s*){2,}").unwrap(),
            wtf: Regex::new(r"(?i)\bwtf\b").unwrap(),
        }
    })
}

fn strip_chars(s: &str, chars: &[char]) -> String {
    s.trim_matches(|c| chars.contains(&c)).to_string()
}

/// Ham dosya adını temizleyip stil ekiyle birleştirir.
pub fn generate_smart_title(raw: &str, style: &str, prefix: &str, rng: &mut Rng) -> String {
    let p = patterns();
    let mut name = raw.to_string();

    name = p.ext_strip.replace_all(&name, "").to_string();
    name = p.trailing_id.replace_all(&name, "").to_string();
    name = p.pipe_tail.replace_all(&name, "").to_string();
    name = p.bracket_tiktok.replace_all(&name, "").to_string();
    name = p.paren_tiktok.replace_all(&name, "").to_string();
    name = p.loop_words.replace_all(&name, "").to_string();
    name = p.bracket_edit.replace_all(&name, "").to_string();
    name = p.paren_edit.replace_all(&name, "").to_string();

    name = name.replace('｜', "|").replace('~', " ");

    name = p.pipe_tail.replace_all(&name, "").to_string();

    let mut cleaned = p.seps.replace_all(&name, " ").to_string();
    cleaned = cleaned.replace('_', " ");
    cleaned = p.junk.replace_all(&cleaned, " ").to_string();
    cleaned = p.wtf.replace_all(&cleaned, " ").to_string();
    cleaned = p.brackets.replace_all(&cleaned, " ").to_string();
    cleaned = p.spaces.replace_all(&cleaned, " ").to_string();
    cleaned = strip_chars(&cleaned, &[' ', '-', '_', '.']);
    cleaned = p.dash_tail.replace_all(&cleaned, "").to_string();
    cleaned = cleaned.trim().to_string();

    if cleaned.chars().count() >= 3 {
        name = cleaned;
    }

    name = p.brackets.replace_all(&name, " ").to_string();
    name = p.dashes.replace_all(&name, " - ").to_string();
    name = p.multi_dash.replace_all(&name, " - ").to_string();
    name = p.spaces.replace_all(&name, " ").to_string();
    name = strip_chars(&name, &[' ', '-', '_']);

    if name.is_empty() {
        name = "Viral Edit Track".to_string();
    }

    let chosen_suffix: String = if style == "smart_random" || style == "auto" || style.is_empty() {
        rng.pick(RANDOM_EDIT_SUFFIXES)
            .copied()
            .unwrap_or_default()
            .to_string()
    } else if let Some(pool) = suffixes_for(style) {
        rng.pick(pool).copied().unwrap_or_default().to_string()
    } else if style == "none" {
        String::new()
    } else {
        format!("({})", style)
    };

    let mut out = format!("{} {}", name, chosen_suffix).trim().to_string();

    let prefix = prefix.trim();
    if !prefix.is_empty() {
        out = format!("{} - {}", prefix, out);
    }

    // Sonuç ham addan farksızsa mutlaka bir varyasyon ekle.
    let raw_cleaned = p.ext_strip.replace_all(raw, "").trim().to_string();
    if out.to_lowercase().trim() == raw_cleaned.to_lowercase().trim() {
        let alt = rng
            .pick(RANDOM_EDIT_SUFFIXES)
            .copied()
            .unwrap_or_default();
        out = format!("{} {}", name, alt).trim().to_string();
    }

    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn t(raw: &str, style: &str) -> String {
        let mut rng = Rng::new();
        generate_smart_title(raw, style, "", &mut rng)
    }

    #[test]
    fn strips_junk_and_keeps_song_name() {
        let out = t("y2mate.com - MONTAGEM BAILE (TikTok Viral) [slowed + reverb] _ 320kbps", "slowed");
        assert!(out.starts_with("y2mate.com - MONTAGEM BAILE"), "{}", out);
        assert!(!out.to_lowercase().contains("320kbps"));
    }

    #[test]
    fn drops_trailing_numeric_id() {
        let out = t("hardtekk_2429976078.mp3", "none");
        assert_eq!(out, "hardtekk");
    }

    #[test]
    fn never_returns_empty() {
        assert!(!t("", "smart_random").is_empty());
        assert!(!t("(Slowed)", "slowed").is_empty());
    }

    #[test]
    fn prefix_is_applied() {
        let mut rng = Rng::new();
        let out = generate_smart_title("song", "none", "ARCHIVE", &mut rng);
        assert_eq!(out, "ARCHIVE - song");
    }
}
