//! Derleme zamanında gömülen varlıklar (arayüz + kapak havuzu).

use rust_embed::RustEmbed;

#[derive(RustEmbed)]
#[folder = "assets/"]
pub struct Assets;

pub fn asset_bytes(path: &str) -> Option<Vec<u8>> {
    Assets::get(path).map(|f| f.data.to_vec())
}

pub fn asset_text(path: &str) -> Option<String> {
    Assets::get(path).map(|f| String::from_utf8_lossy(&f.data).to_string())
}
