//! Windows'a özgü küçük yardımcılar.
//!
//! Uygulama `windows` alt sistemiyle derlendiği için konsol penceresi yok;
//! başlatma hatalarını kullanıcıya göstermenin tek yolu MessageBox.

/// Hata/uyarı penceresi gösterir. Konsol olmadığı için sessiz çökmeyi önler.
#[cfg(windows)]
pub fn message_box(title: &str, text: &str, is_error: bool) {
    use std::os::windows::ffi::OsStrExt;

    #[link(name = "user32")]
    extern "system" {
        fn MessageBoxW(
            hwnd: *mut core::ffi::c_void,
            text: *const u16,
            caption: *const u16,
            u_type: u32,
        ) -> i32;
    }

    fn wide(s: &str) -> Vec<u16> {
        std::ffi::OsStr::new(s)
            .encode_wide()
            .chain(std::iter::once(0))
            .collect()
    }

    // MB_ICONERROR = 0x10, MB_ICONINFORMATION = 0x40, MB_SETFOREGROUND = 0x10000
    let flags = if is_error { 0x10 } else { 0x40 } | 0x10000;
    let text = wide(text);
    let caption = wide(title);
    unsafe {
        MessageBoxW(
            std::ptr::null_mut(),
            text.as_ptr(),
            caption.as_ptr(),
            flags,
        );
    }
}

#[cfg(not(windows))]
pub fn message_box(title: &str, text: &str, _is_error: bool) {
    eprintln!("{title}: {text}");
}

/// WebView2 çalışma zamanı kurulu mu?
#[cfg(windows)]
pub fn webview2_available() -> bool {
    use std::ffi::OsStr;
    use std::os::windows::ffi::OsStrExt;

    #[link(name = "advapi32")]
    extern "system" {
        fn RegGetValueW(
            hkey: *mut core::ffi::c_void,
            sub_key: *const u16,
            value: *const u16,
            flags: u32,
            value_type: *mut u32,
            data: *mut core::ffi::c_void,
            data_size: *mut u32,
        ) -> i32;
    }

    const HKEY_LOCAL_MACHINE: *mut core::ffi::c_void = 0x8000_0002u64 as *mut core::ffi::c_void;
    const HKEY_CURRENT_USER: *mut core::ffi::c_void = 0x8000_0001u64 as *mut core::ffi::c_void;
    const RRF_RT_REG_SZ: u32 = 0x0000_0002;
    const ERROR_SUCCESS: i32 = 0;

    fn wide(s: &str) -> Vec<u16> {
        OsStr::new(s)
            .encode_wide()
            .chain(std::iter::once(0))
            .collect()
    }

    let sub = wide(r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}");
    let sub64 = wide(r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}");
    let name = wide("pv");
    let mut buf = [0u16; 64];
    let mut size = (buf.len() * 2) as u32;

    for hive in [HKEY_LOCAL_MACHINE, HKEY_CURRENT_USER] {
        for key in [&sub, &sub64] {
            let mut ty = 0u32;
            let rc = unsafe {
                RegGetValueW(
                    hive,
                    key.as_ptr(),
                    name.as_ptr(),
                    RRF_RT_REG_SZ,
                    &mut ty,
                    buf.as_mut_ptr() as *mut core::ffi::c_void,
                    &mut size,
                )
            };
            if rc == ERROR_SUCCESS {
                return true;
            }
        }
    }
    false
}

#[cfg(not(windows))]
pub fn webview2_available() -> bool {
    true
}

#[cfg(windows)]
fn wide_z(s: &str) -> Vec<u16> {
    use std::os::windows::ffi::OsStrExt;
    std::ffi::OsStr::new(s)
        .encode_wide()
        .chain(std::iter::once(0))
        .collect()
}

/// Oturum başına tek örnek. İlk örnek adlandırılmış bir mutex alır; süreç
/// kapanınca Windows mutex'i kendiliğinden bırakır.
#[cfg(windows)]
pub fn acquire_single_instance() -> bool {
    #[link(name = "kernel32")]
    extern "system" {
        fn CreateMutexW(
            attrs: *mut core::ffi::c_void,
            initial_owner: i32,
            name: *const u16,
        ) -> *mut core::ffi::c_void;
        fn GetLastError() -> u32;
    }
    const ERROR_ALREADY_EXISTS: u32 = 183;

    let name = wide_z(r"Local\SoundCloudStudio.SingleInstance");
    let handle = unsafe { CreateMutexW(std::ptr::null_mut(), 0, name.as_ptr()) };
    if handle.is_null() {
        // Mutex oluşturulamadıysa açılışı engelleme.
        return true;
    }
    // Tutamaç süreç boyunca açık kalmalı; bilerek kapatılmıyor.
    unsafe { GetLastError() != ERROR_ALREADY_EXISTS }
}

#[cfg(not(windows))]
pub fn acquire_single_instance() -> bool {
    true
}

/// Açık olan pencereyi (simge durumundaysa geri getirip) öne alır.
#[cfg(windows)]
pub fn focus_existing_window(title: &str) {
    #[link(name = "user32")]
    extern "system" {
        fn FindWindowW(class: *const u16, title: *const u16) -> *mut core::ffi::c_void;
        fn ShowWindow(hwnd: *mut core::ffi::c_void, cmd: i32) -> i32;
        fn SetForegroundWindow(hwnd: *mut core::ffi::c_void) -> i32;
        fn IsIconic(hwnd: *mut core::ffi::c_void) -> i32;
    }
    const SW_RESTORE: i32 = 9;

    let t = wide_z(title);
    // İlk örnek pencereyi henüz açıyor olabilir; kısa bir süre dene.
    for _ in 0..20 {
        let hwnd = unsafe { FindWindowW(std::ptr::null(), t.as_ptr()) };
        if !hwnd.is_null() {
            unsafe {
                if IsIconic(hwnd) != 0 {
                    ShowWindow(hwnd, SW_RESTORE);
                }
                SetForegroundWindow(hwnd);
            }
            return;
        }
        std::thread::sleep(std::time::Duration::from_millis(150));
    }
}

#[cfg(not(windows))]
pub fn focus_existing_window(_title: &str) {}
