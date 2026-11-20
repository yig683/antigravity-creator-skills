//! Kapak çeşitlendirme.
//!
//! Havuz sınırlı olduğu için aynı kaynak görsel eninde sonunda yeniden çıkar.
//! Burada her kapağa rastgele kırpma, renk işleme, tane ve vinyet uygulanır;
//! böylece aynı görselden bile her seferinde farklı görünen bir kapak üretilir.

use crate::rng::Rng;
use image::{imageops::FilterType, DynamicImage, RgbImage};

pub const SIZE: u32 = 800;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CoverStyle {
    /// Görsel olduğu gibi (yalnızca ortadan kare kırpılır).
    Original,
    /// Hafif kırpma + renk tonu + tane (varsayılan).
    Varied,
    /// Güçlü kırpma ve renk dönüşümü.
    Bold,
}

impl CoverStyle {
    pub fn parse(s: &str) -> Self {
        match s.trim() {
            "original" => Self::Original,
            "bold" => Self::Bold,
            _ => Self::Varied,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Treatment {
    None,
    Tint,
    Duotone,
    HueShift,
    Mono,
}

struct Plan {
    zoom: f32,
    treat: Treatment,
    glitch: bool,
    contrast: f32,
    brightness: f32,
    vignette: f32,
    grain: f32,
}

/// Phonk / hardtekk estetiğine yakışan vurgu renk tonları (derece).
const ACCENTS: &[f32] = &[
    2.0, 350.0, 12.0, 28.0, 48.0, 100.0, 160.0, 188.0, 212.0, 255.0, 275.0, 292.0, 318.0,
];

struct Stats {
    sat: f32,
}

pub fn render(src: &DynamicImage, style: CoverStyle, rng: &mut Rng) -> RgbImage {
    render_sized(src, style, rng, SIZE)
}

/// `render` ile aynı, çıktı kenarı ayarlanabilir (testler küçük boyutla hızlı çalışır).
pub fn render_sized(src: &DynamicImage, style: CoverStyle, rng: &mut Rng, size: u32) -> RgbImage {
    if style == CoverStyle::Original {
        return src.resize_to_fill(size, size, FilterType::Lanczos3).to_rgb8();
    }

    let thumb = src.resize_exact(32, 32, FilterType::Triangle).to_rgb8();
    let stats = Stats { sat: mean_saturation(&thumb) };
    let plan = make_plan(style, &stats, rng);

    let mut img = crop_zoom(src, plan.zoom, size, rng);
    let before = mean_luma_sampled(&img);
    match plan.treat {
        Treatment::None => {}
        Treatment::Tint => tint(&mut img, rng),
        Treatment::Duotone => duotone(&mut img, rng),
        Treatment::HueShift => hue_shift(&mut img, rng),
        Treatment::Mono => mono(&mut img, rng),
    }
    if plan.glitch {
        glitch(&mut img, rng);
    }
    keep_visible(&mut img, before);
    finish(&mut img, &plan, rng);
    img
}

fn make_plan(style: CoverStyle, st: &Stats, rng: &mut Rng) -> Plan {
    let bold = style == CoverStyle::Bold;
    let colorful = st.sat > 0.22;

    let zoom = if bold {
        rng.between(1.2, 1.75)
    } else if rng.chance(0.55) {
        rng.between(1.08, 1.4)
    } else {
        1.0
    };

    // (işlem, ağırlık)
    let table: [(Treatment, u32); 5] = if bold {
        [
            (Treatment::None, 0),
            (Treatment::Tint, 15),
            (Treatment::Duotone, 32),
            (Treatment::HueShift, if colorful { 26 } else { 0 }),
            (Treatment::Mono, 22),
        ]
    } else {
        [
            (Treatment::None, 18),
            (Treatment::Tint, 26),
            (Treatment::Duotone, 22),
            (Treatment::HueShift, if colorful { 20 } else { 0 }),
            (Treatment::Mono, 14),
        ]
    };
    let total: u32 = table.iter().map(|t| t.1).sum();
    let mut roll = rng.below(total as usize) as u32;
    let mut treat = Treatment::None;
    for (t, w) in table {
        if roll < w {
            treat = t;
            break;
        }
        roll -= w;
    }

    Plan {
        zoom,
        treat,
        glitch: rng.chance(if bold { 0.28 } else { 0.08 }),
        contrast: rng.between(0.94, if bold { 1.18 } else { 1.1 }),
        brightness: rng.between(0.95, 1.05),
        vignette: if rng.chance(0.75) {
            rng.between(0.12, if bold { 0.5 } else { 0.34 })
        } else {
            0.0
        },
        grain: rng.between(3.0, if bold { 13.0 } else { 8.0 }),
    }
}

/// Ortadaki kareden `zoom` kat yakınlaştırılmış, rastgele kaydırılmış bir parça alır.
/// Birkaç aday kırpma denenir; boş/simsiyah alana yakınlaşmamak için içeriği
/// zengin olanlar arasından rastgele biri seçilir.
fn crop_zoom(src: &DynamicImage, zoom: f32, size: u32, rng: &mut Rng) -> RgbImage {
    let (w, h) = (src.width() as f32, src.height() as f32);
    let side = w.min(h);
    let s = (side / zoom.max(1.0)).max(8.0).min(side);
    let slack = (side - s) / 2.0;
    let side_px = (s.round() as u32).max(1);
    let attempts = if slack > 0.5 { 6 } else { 1 };

    let mut cands: Vec<(f32, u32, u32)> = Vec::with_capacity(attempts);
    for _ in 0..attempts {
        let dx = if slack > 0.5 { rng.between(-0.85, 0.85) * slack } else { 0.0 };
        let dy = if slack > 0.5 { rng.between(-0.85, 0.85) * slack } else { 0.0 };
        let x = (w / 2.0 - s / 2.0 + dx).round().clamp(0.0, (w - s).max(0.0)) as u32;
        let y = (h / 2.0 - s / 2.0 + dy).round().clamp(0.0, (h - s).max(0.0)) as u32;
        let score = if attempts > 1 { crop_interest(src, x, y, side_px) } else { 0.0 };
        cands.push((score, x, y));
    }
    let best = cands.iter().map(|c| c.0).fold(0.0f32, f32::max);
    cands.retain(|c| c.0 >= best * 0.7);
    let (_, x, y) = cands[rng.below(cands.len())];

    src.crop_imm(x, y, side_px, side_px)
        .resize_exact(size, size, FilterType::Lanczos3)
        .to_rgb8()
}

/// Kırpmanın "ilginçliği": ortalama parlaklık + parlaklık dağılımı (düz siyah/beyaz düşük puan alır).
fn crop_interest(src: &DynamicImage, x: u32, y: u32, side: u32) -> f32 {
    let t = src.crop_imm(x, y, side, side).resize_exact(24, 24, FilterType::Triangle).to_luma8();
    let n = t.as_raw().len() as f32;
    let mean = t.as_raw().iter().map(|v| *v as f32 / 255.0).sum::<f32>() / n;
    let var = t.as_raw().iter().map(|v| (*v as f32 / 255.0 - mean).powi(2)).sum::<f32>() / n;
    mean * 0.6 + var.sqrt()
}

// ------------------------------------------------------------------ renk yardımcıları

fn luma(r: f32, g: f32, b: f32) -> f32 {
    0.299 * r + 0.587 * g + 0.114 * b
}

fn smoothstep(a: f32, b: f32, x: f32) -> f32 {
    let t = ((x - a) / (b - a)).clamp(0.0, 1.0);
    t * t * (3.0 - 2.0 * t)
}

fn lerp(a: f32, b: f32, t: f32) -> f32 {
    a + (b - a) * t
}

/// h: derece, s/v: 0..1 → 0..1 RGB
fn hsv_to_rgb(h: f32, s: f32, v: f32) -> [f32; 3] {
    let h = h.rem_euclid(360.0) / 60.0;
    let c = v * s;
    let x = c * (1.0 - ((h % 2.0) - 1.0).abs());
    let (r, g, b) = match h as u32 {
        0 => (c, x, 0.0),
        1 => (x, c, 0.0),
        2 => (0.0, c, x),
        3 => (0.0, x, c),
        4 => (x, 0.0, c),
        _ => (c, 0.0, x),
    };
    let m = v - c;
    [r + m, g + m, b + m]
}

/// 0..1 RGB → (h derece, s, v)
fn rgb_to_hsv(r: f32, g: f32, b: f32) -> (f32, f32, f32) {
    let max = r.max(g).max(b);
    let min = r.min(g).min(b);
    let d = max - min;
    let h = if d < 1e-6 {
        0.0
    } else if max == r {
        60.0 * (((g - b) / d).rem_euclid(6.0))
    } else if max == g {
        60.0 * ((b - r) / d + 2.0)
    } else {
        60.0 * ((r - g) / d + 4.0)
    };
    let s = if max < 1e-6 { 0.0 } else { d / max };
    (h, s, max)
}

fn mean_saturation(img: &RgbImage) -> f32 {
    let mut acc = 0.0;
    let mut wsum = 0.0;
    for p in img.pixels() {
        let (_, s, v) = rgb_to_hsv(p[0] as f32 / 255.0, p[1] as f32 / 255.0, p[2] as f32 / 255.0);
        acc += s * v;
        wsum += v;
    }
    if wsum < 1e-3 {
        0.0
    } else {
        acc / wsum
    }
}

fn to_u8(v: f32) -> u8 {
    (v * 255.0).round().clamp(0.0, 255.0) as u8
}

fn accent(rng: &mut Rng) -> f32 {
    *rng.pick(ACCENTS).unwrap_or(&2.0)
}

// ------------------------------------------------------------------ renk işlemleri

/// Parlaklığı koruyarak rastgele bir vurgu rengine doğru kaydırır.
fn tint(img: &mut RgbImage, rng: &mut Rng) {
    let h = accent(rng);
    let tint = hsv_to_rgb(h, rng.between(0.65, 0.95), 1.0);
    let a = rng.between(0.3, 0.6);
    for p in img.pixels_mut() {
        let (r, g, b) = (p[0] as f32 / 255.0, p[1] as f32 / 255.0, p[2] as f32 / 255.0);
        let l = (luma(r, g, b) * 1.18).min(1.0);
        p[0] = to_u8(lerp(r, tint[0] * l, a));
        p[1] = to_u8(lerp(g, tint[1] * l, a));
        p[2] = to_u8(lerp(b, tint[2] * l, a));
    }
}

/// Gölgeleri koyu bir tona, ışıkları parlak bir tona boyar (gradyan haritası).
fn duotone(img: &mut RgbImage, rng: &mut Rng) {
    let h1 = accent(rng);
    let offsets = [0.0, 24.0, -24.0, 60.0, 150.0, 180.0];
    let h2 = h1 + *rng.pick(&offsets).unwrap_or(&0.0);
    let shadow = hsv_to_rgb(h1, 0.85, rng.between(0.03, 0.12));
    let high = hsv_to_rgb(h2, rng.between(0.25, 0.85), rng.between(0.9, 1.0));
    let strength = rng.between(0.72, 0.95);
    for p in img.pixels_mut() {
        let (r, g, b) = (p[0] as f32 / 255.0, p[1] as f32 / 255.0, p[2] as f32 / 255.0);
        let l = smoothstep(0.04, 0.96, luma(r, g, b));
        p[0] = to_u8(lerp(r, lerp(shadow[0], high[0], l), strength));
        p[1] = to_u8(lerp(g, lerp(shadow[1], high[1], l), strength));
        p[2] = to_u8(lerp(b, lerp(shadow[2], high[2], l), strength));
    }
}

fn hue_shift(img: &mut RgbImage, rng: &mut Rng) {
    let delta = rng.between(50.0, 310.0);
    for p in img.pixels_mut() {
        let (h, s, v) = rgb_to_hsv(p[0] as f32 / 255.0, p[1] as f32 / 255.0, p[2] as f32 / 255.0);
        let c = hsv_to_rgb(h + delta, s, v);
        p[0] = to_u8(c[0]);
        p[1] = to_u8(c[1]);
        p[2] = to_u8(c[2]);
    }
}

/// Siyah-beyaza çevirir, kontrastı artırır ve ışıkları tek bir renge boyar.
fn mono(img: &mut RgbImage, rng: &mut Rng) {
    let h = accent(rng);
    let color = hsv_to_rgb(h, rng.between(0.8, 1.0), 1.0);
    let contrast = rng.between(1.12, 1.45);
    let k = rng.between(0.6, 0.9);
    for p in img.pixels_mut() {
        let l = luma(p[0] as f32 / 255.0, p[1] as f32 / 255.0, p[2] as f32 / 255.0);
        let g = ((l - 0.5) * contrast + 0.5).clamp(0.0, 1.0);
        p[0] = to_u8(lerp(g, color[0] * g, k));
        p[1] = to_u8(lerp(g, color[1] * g, k));
        p[2] = to_u8(lerp(g, color[2] * g, k));
    }
}

/// RGB kanallarını kaydırır ve birkaç yatay şeridi yana iter.
fn glitch(img: &mut RgbImage, rng: &mut Rng) {
    let (w, h) = (img.width() as i32, img.height() as i32);
    let k = w as f32 / SIZE as f32; // piksel değerleri 800 px'e göre; boyuta ölçeklenir
    let dx = ((rng.between(3.0, 9.0) * k).round() as i32).max(1);
    let src = img.clone();
    for y in 0..h {
        for x in 0..w {
            let xr = (x + dx).clamp(0, w - 1) as u32;
            let xb = (x - dx).clamp(0, w - 1) as u32;
            let p = img.get_pixel_mut(x as u32, y as u32);
            p[0] = src.get_pixel(xr, y as u32)[0];
            p[2] = src.get_pixel(xb, y as u32)[2];
        }
    }
    let bands = 3 + rng.below(4);
    for _ in 0..bands {
        let y0 = rng.below(h as usize) as i32;
        let hh = ((rng.between(6.0, 40.0) * k).round() as i32).max(1);
        let shift = ((rng.between(12.0, 70.0) * k).round() as i32).max(1) * if rng.chance(0.5) { 1 } else { -1 };
        let copy = img.clone();
        for y in y0..(y0 + hh).min(h) {
            for x in 0..w {
                let sx = (x - shift).rem_euclid(w) as u32;
                let v = *copy.get_pixel(sx, y as u32);
                img.put_pixel(x as u32, y as u32, v);
            }
        }
    }
}

/// Ortalama parlaklık (her 7. piksel örneklenir).
fn mean_luma_sampled(img: &RgbImage) -> f32 {
    let mut acc = 0.0f32;
    let mut n = 0u32;
    for p in img.pixels().step_by(7) {
        acc += luma(p[0] as f32 / 255.0, p[1] as f32 / 255.0, p[2] as f32 / 255.0);
        n += 1;
    }
    if n == 0 {
        0.0
    } else {
        acc / n as f32
    }
}

/// Renk işlemleri koyu görselleri neredeyse siyaha çevirebilir; görüntü orijinalinin
/// parlaklığının en az ~%80'ini korusun (yumuşak eğri: kırpma yok, ışıklar patlamaz).
fn keep_visible(img: &mut RgbImage, before: f32) {
    let after = mean_luma_sampled(img);
    let target = (before * 0.8).clamp(0.10, 0.5);
    if after >= target {
        return;
    }
    let g = (target / after.max(0.005)).clamp(1.0, 6.0);
    let mut lut = [0u8; 256];
    for (i, o) in lut.iter_mut().enumerate() {
        let v = i as f32 / 255.0;
        *o = to_u8(v * g / (1.0 + (g - 1.0) * v));
    }
    for p in img.pixels_mut() {
        p[0] = lut[p[0] as usize];
        p[1] = lut[p[1] as usize];
        p[2] = lut[p[2] as usize];
    }
}

/// Kontrast/parlaklık oynatması, vinyet ve film tanesi.
fn finish(img: &mut RgbImage, plan: &Plan, rng: &mut Rng) {
    let (w, h) = (img.width() as f32, img.height() as f32);
    let (cx, cy) = (w / 2.0, h / 2.0);
    let maxr = (cx * cx + cy * cy).sqrt();
    for (x, y, p) in img.enumerate_pixels_mut() {
        let dxn = (x as f32 - cx) / maxr;
        let dyn_ = (y as f32 - cy) / maxr;
        let r = (dxn * dxn + dyn_ * dyn_).sqrt();
        let vig = 1.0 - plan.vignette * smoothstep(0.3, 0.95, r);

        let n = rng.gauss() * plan.grain;
        let nc = [n + rng.gauss() * plan.grain * 0.25, n, n + rng.gauss() * plan.grain * 0.25];
        for c in 0..3 {
            let v = p[c] as f32 / 255.0;
            let v = ((v - 0.5) * plan.contrast + 0.5) * plan.brightness * vig;
            p[c] = (v * 255.0 + nc[c]).round().clamp(0.0, 255.0) as u8;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use image::Rgb;

    fn sample(w: u32, h: u32) -> DynamicImage {
        let mut im = RgbImage::new(w, h);
        for (x, y, p) in im.enumerate_pixels_mut() {
            *p = Rgb([
                (x * 255 / w) as u8,
                (y * 255 / h) as u8,
                (((x + y) * 255) / (w + h)) as u8,
            ]);
        }
        DynamicImage::ImageRgb8(im)
    }

    fn diff(a: &RgbImage, b: &RgbImage) -> f64 {
        a.as_raw()
            .iter()
            .zip(b.as_raw())
            .map(|(x, y)| (*x as f64 - *y as f64).abs())
            .sum::<f64>()
            / a.as_raw().len() as f64
    }

    const T: u32 = 160; // testlerde küçük çıktı boyutu

    #[test]
    fn original_keeps_plain_fill() {
        let src = sample(640, 480);
        let mut rng = Rng::from_seed(1);
        let out = render_sized(&src, CoverStyle::Original, &mut rng, T);
        assert_eq!((out.width(), out.height()), (T, T));
        let plain = src.resize_to_fill(T, T, FilterType::Lanczos3).to_rgb8();
        assert_eq!(out.as_raw(), plain.as_raw());
    }

    #[test]
    fn full_size_render_is_800() {
        let out = render(&sample(300, 300), CoverStyle::Varied, &mut Rng::from_seed(9));
        assert_eq!((out.width(), out.height()), (SIZE, SIZE));
    }

    #[test]
    fn varied_is_deterministic_per_seed_and_differs_between_seeds() {
        let src = sample(512, 512);
        let a1 = render_sized(&src, CoverStyle::Varied, &mut Rng::from_seed(7), T);
        let a2 = render_sized(&src, CoverStyle::Varied, &mut Rng::from_seed(7), T);
        assert_eq!(a1.as_raw(), a2.as_raw());
        // Aynı kaynaktan farklı tohumlarla üretilen kapaklar birbirinden belirgin farklı olmalı.
        let mut worst = f64::MAX;
        for s in 10..30u64 {
            let b = render_sized(&src, CoverStyle::Varied, &mut Rng::from_seed(s), T);
            worst = worst.min(diff(&a1, &b));
        }
        assert!(worst > 1.5, "kapaklar birbirine fazla benziyor: {worst}");
    }

    #[test]
    fn bold_changes_more_than_original() {
        let src = sample(700, 500);
        let plain = render_sized(&src, CoverStyle::Original, &mut Rng::from_seed(1), T);
        let mut total = 0.0;
        for s in 0..12u64 {
            total += diff(&plain, &render_sized(&src, CoverStyle::Bold, &mut Rng::from_seed(100 + s), T));
        }
        assert!(total / 12.0 > 12.0, "cesur stil yeterince farklı değil: {}", total / 12.0);
    }

    #[test]
    fn handles_tiny_and_extreme_images() {
        for (w, h) in [(1, 1), (3, 200), (900, 4), (64, 64)] {
            let src = sample(w, h);
            for style in [CoverStyle::Original, CoverStyle::Varied, CoverStyle::Bold] {
                let out = render_sized(&src, style, &mut Rng::from_seed(3), T);
                assert_eq!((out.width(), out.height()), (T, T), "{w}x{h} {style:?}");
            }
        }
    }

    #[test]
    fn dark_images_stay_visible() {
        // Çoğu siyah, birkaç parlak çizgi: renk işlemleri bunu eziyordu.
        let mut im = RgbImage::from_pixel(240, 240, Rgb([3, 3, 4]));
        for i in 0..240u32 {
            for t in 0..9u32 {
                if i + t < 240 {
                    im.put_pixel(i + t, i, Rgb([200, 200, 210]));
                    im.put_pixel(239 - i - t.min(239 - i), i, Rgb([180, 180, 190]));
                }
            }
        }
        let src = DynamicImage::ImageRgb8(im);
        let reference = mean_luma_sampled(&render_sized(&src, CoverStyle::Original, &mut Rng::from_seed(1), T));
        for s in 0..24u64 {
            for style in [CoverStyle::Varied, CoverStyle::Bold] {
                let out = render_sized(&src, style, &mut Rng::from_seed(500 + s), T);
                let l = mean_luma_sampled(&out);
                // Vinyet/kontrast biraz karartabilir ama görüntü orijinalin yarısından az parlak olmamalı.
                assert!(l >= 0.5 * reference, "çok koyu: seed {s} {style:?} ort. {l} (orijinal {reference})");
            }
        }
    }

    #[test]
    fn hsv_roundtrip() {
        for (r, g, b) in [(0.2, 0.5, 0.9), (1.0, 0.0, 0.0), (0.3, 0.3, 0.3), (0.9, 0.8, 0.1)] {
            let (h, s, v) = rgb_to_hsv(r, g, b);
            let c = hsv_to_rgb(h, s, v);
            assert!((c[0] - r).abs() < 1e-3 && (c[1] - g).abs() < 1e-3 && (c[2] - b).abs() < 1e-3);
        }
    }

    #[test]
    fn style_parse_defaults_to_varied() {
        assert_eq!(CoverStyle::parse("original"), CoverStyle::Original);
        assert_eq!(CoverStyle::parse("bold"), CoverStyle::Bold);
        assert_eq!(CoverStyle::parse("varied"), CoverStyle::Varied);
        assert_eq!(CoverStyle::parse("???"), CoverStyle::Varied);
    }
}
