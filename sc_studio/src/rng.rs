//! Küçük, bağımlılıksız rastgele sayı üreteci.
//!
//! `rand` crate'i yerine xorshift64* kullanıyoruz: kapak seçimi ve başlık
//! varyasyonları için istatistiksel kalite fazlasıyla yeterli, ek bağımlılık
//! gerektirmiyor.

use std::time::{SystemTime, UNIX_EPOCH};

pub struct Rng(u64);

impl Rng {
    pub fn new() -> Self {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_nanos() as u64)
            .unwrap_or(0x9E3779B97F4A7C15);
        // Aynı nanos değeri iki kez gelirse bile farklı akış üret.
        let seed = nanos ^ (std::process::id() as u64).wrapping_mul(0x2545F4914F6CDD1D);
        Self(if seed == 0 { 0x9E3779B97F4A7C15 } else { seed })
    }

    /// Sabit tohumdan üretecin (testlerde tekrarlanabilir sonuç için).
    #[cfg(test)]
    pub fn from_seed(seed: u64) -> Self {
        // splitmix64: küçük/ardışık tohumlar bile iyi dağılmış bir başlangıç durumu verir.
        let mut z = seed.wrapping_add(0x9E37_79B9_7F4A_7C15);
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^= z >> 31;
        Self(if z == 0 { 0x9E37_79B9_7F4A_7C15 } else { z })
    }

    /// `[0, 1)` aralığında kayan nokta.
    pub fn unit(&mut self) -> f32 {
        ((self.next_u64() >> 40) as f32) / (1u64 << 24) as f32
    }

    /// `[lo, hi)` aralığında kayan nokta.
    pub fn between(&mut self, lo: f32, hi: f32) -> f32 {
        lo + (hi - lo) * self.unit()
    }

    /// Verilen olasılıkla `true`.
    pub fn chance(&mut self, p: f32) -> bool {
        self.unit() < p
    }

    /// Yaklaşık standart normal dağılım (4 düzgün sayının toplamı).
    pub fn gauss(&mut self) -> f32 {
        let s = self.unit() + self.unit() + self.unit() + self.unit();
        (s - 2.0) * 1.732_050_8 // sqrt(3): varyansı 1'e getirir
    }

    pub fn next_u64(&mut self) -> u64 {
        let mut x = self.0;
        x ^= x >> 12;
        x ^= x << 25;
        x ^= x >> 27;
        self.0 = x;
        x.wrapping_mul(0x2545F4914F6CDD1D)
    }

    /// `0..n` aralığında değer (n == 0 ise 0).
    pub fn below(&mut self, n: usize) -> usize {
        if n == 0 {
            0
        } else {
            (self.next_u64() % n as u64) as usize
        }
    }

    pub fn pick<'a, T>(&mut self, items: &'a [T]) -> Option<&'a T> {
        if items.is_empty() {
            None
        } else {
            Some(&items[self.below(items.len())])
        }
    }

}

impl Default for Rng {
    fn default() -> Self {
        Self::new()
    }
}
