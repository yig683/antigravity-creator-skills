//! Minimal ID3v2.3 yazıcı.
//!
//! Sadece ihtiyacımız olan çerçeveleri (TIT2 / TPE1 / TALB / TCON / APIC)
//! yazıyoruz. Harici bir etiket kütüphanesine göre avantajı: ne yazdığımız
//! tamamen bizim kontrolümüzde ve ffmpeg'in bıraktığı eski etiketler her
//! seferinde temizleniyor.

use anyhow::{Context, Result};
use std::io::Write;
use std::path::Path;

const FRAME_TITLE: &str = "TIT2";
const FRAME_ARTIST: &str = "TPE1";
const FRAME_ALBUM: &str = "TALB";
const FRAME_GENRE: &str = "TCON";
const FRAME_PICTURE: &str = "APIC";

pub struct Tags<'a> {
    pub title: &'a str,
    pub artist: &'a str,
    pub album: &'a str,
    pub genre: &'a str,
    pub cover: Option<&'a [u8]>,
}

/// Baştaki ID3v2 etiketini (varsa) atlar.
fn strip_existing(data: &[u8]) -> &[u8] {
    if data.len() > 10 && &data[0..3] == b"ID3" {
        let size = syncsafe(&data[6..10]);
        let has_footer = data[5] & 0x10 != 0;
        let total = 10 + size + if has_footer { 10 } else { 0 };
        if total <= data.len() {
            return &data[total..];
        }
    }
    data
}

fn syncsafe(bytes: &[u8]) -> usize {
    ((bytes[0] as usize & 0x7f) << 21)
        | ((bytes[1] as usize & 0x7f) << 14)
        | ((bytes[2] as usize & 0x7f) << 7)
        | (bytes[3] as usize & 0x7f)
}

fn encode_syncsafe(mut n: usize) -> [u8; 4] {
    let mut out = [0u8; 4];
    for i in (0..4).rev() {
        out[i] = (n & 0x7f) as u8;
        n >>= 7;
    }
    out
}

/// UTF-16 (BOM'lu) metin çerçevesi gövdesi.
fn text_payload(value: &str) -> Vec<u8> {
    let mut out = Vec::with_capacity(3 + value.len() * 2);
    out.push(0x01); // UTF-16 with BOM
    out.extend_from_slice(&[0xFF, 0xFE]);
    for unit in value.encode_utf16() {
        out.extend_from_slice(&unit.to_le_bytes());
    }
    out
}

fn frame(id: &str, payload: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(10 + payload.len());
    out.extend_from_slice(id.as_bytes());
    out.extend_from_slice(&(payload.len() as u32).to_be_bytes());
    out.extend_from_slice(&[0, 0]); // flags
    out.extend_from_slice(payload);
    out
}

fn build_tag(tags: &Tags) -> Vec<u8> {
    let mut frames: Vec<u8> = Vec::new();

    for (id, value) in [
        (FRAME_TITLE, tags.title),
        (FRAME_ARTIST, tags.artist),
        (FRAME_ALBUM, tags.album),
        (FRAME_GENRE, tags.genre),
    ] {
        if !value.trim().is_empty() {
            frames.extend_from_slice(&frame(id, &text_payload(value)));
        }
    }

    if let Some(cover) = tags.cover {
        let mut payload = Vec::with_capacity(cover.len() + 32);
        payload.push(0x00); // ISO-8859-1
        payload.extend_from_slice(b"image/jpeg\x00");
        payload.push(0x03); // front cover
        payload.push(0x00); // empty description
        payload.extend_from_slice(cover);
        frames.extend_from_slice(&frame(FRAME_PICTURE, &payload));
    }

    let mut tag = Vec::with_capacity(frames.len() + 10);
    tag.extend_from_slice(b"ID3");
    tag.extend_from_slice(&[0x03, 0x00, 0x00]); // v2.3.0, no flags
    tag.extend_from_slice(&encode_syncsafe(frames.len()));
    tag.extend_from_slice(&frames);
    tag
}

/// MP3 dosyasına etiketleri yazar (dosya yerinde güncellenir).
pub fn write_tags(path: &Path, tags: &Tags) -> Result<()> {
    let data = std::fs::read(path).with_context(|| format!("okunamadı: {}", path.display()))?;
    // Etiket yenilemek dosyayı kütüphanede "yeni" gibi göstermesin.
    let original_mtime = std::fs::metadata(path).and_then(|m| m.modified()).ok();
    let audio = strip_existing(&data);
    let tag = build_tag(tags);

    let tmp = path.with_extension("mp3.tmp");
    {
        let mut out = std::fs::File::create(&tmp)?;
        out.write_all(&tag)?;
        out.write_all(audio)?;
        out.flush()?;
        if let Some(t) = original_mtime {
            let _ = out.set_modified(t);
        }
    }
    std::fs::rename(&tmp, path)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn syncsafe_roundtrip() {
        for n in [0usize, 1, 127, 128, 16_383, 16_384, 1_000_000] {
            assert_eq!(syncsafe(&encode_syncsafe(n)), n);
        }
    }

    #[test]
    fn tag_starts_with_id3_header() {
        let tag = build_tag(&Tags {
            title: "Deneme",
            artist: "Sanatçı",
            album: "Arşiv",
            genre: "Phonk",
            cover: Some(b"\xff\xd8\xff\xd9"),
        });
        assert_eq!(&tag[0..3], b"ID3");
        assert_eq!(tag[3], 3);
        assert!(tag.len() > 10);
    }

    #[test]
    fn strip_existing_removes_old_tag() {
        let mut data = build_tag(&Tags {
            title: "x",
            artist: "",
            album: "",
            genre: "",
            cover: None,
        });
        data.extend_from_slice(b"\xff\xfb\x90\x00audio");
        let audio = strip_existing(&data);
        assert_eq!(audio, b"\xff\xfb\x90\x00audio");
    }
}
