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
