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

/// Windows 10/11 başlık çubuğunu koyu tema ve SC Studio arka plan rengine (#0d0d10) uyarlar.
#[cfg(windows)]
pub fn style_dark_window(hwnd: isize) {
    if hwnd == 0 {
        return;
    }
    #[link(name = "dwmapi")]
    extern "system" {
        fn DwmSetWindowAttribute(
            hwnd: *mut core::ffi::c_void,
            attr: u32,
            pv_attribute: *const core::ffi::c_void,
            cb_attribute: u32,
        ) -> i32;
    }

    let hwnd_ptr = hwnd as *mut core::ffi::c_void;
    let set_u32 = |attr: u32, val: u32| unsafe {
        let _ = DwmSetWindowAttribute(
            hwnd_ptr,
            attr,
            &val as *const u32 as *const core::ffi::c_void,
            std::mem::size_of::<u32>() as u32,
        );
    };

    // DWMWA_USE_IMMERSIVE_DARK_MODE: Win11/Win10 2004+ (20), eski Win10 (19)
    set_u32(20, 1);
    set_u32(19, 1);
    // DWMWA_WINDOW_CORNER_PREFERENCE = 33 -> DWMWCP_ROUND = 2
    set_u32(33, 2);
    // COLORREF biçimi: 0x00BBGGRR
    // DWMWA_BORDER_COLOR = 34 (#232429 -> 0x00292423)
    set_u32(34, 0x0029_2423);
    // DWMWA_CAPTION_COLOR = 35 (#0d0d10 -> 0x00100d0d)
    set_u32(35, 0x0010_0d0d);
    // DWMWA_TEXT_COLOR = 36 (#f2f2f4 -> 0x00f4f2f2)
    set_u32(36, 0x00f4_f2f2);
}

#[cfg(not(windows))]
pub fn style_dark_window(_hwnd: isize) {}

/// Modern Windows Klasör Seçme iletişim kutusunu (IFileOpenDialog, FOS_PICKFOLDERS) açar.
#[cfg(windows)]
pub fn pick_folder_dialog(
    owner_hwnd: isize,
    title: &str,
    initial_dir: Option<&std::path::Path>,
) -> Option<String> {
    use core::ffi::c_void;

    #[repr(C)]
    #[derive(Clone, Copy)]
    struct Guid {
        data1: u32,
        data2: u16,
        data3: u16,
        data4: [u8; 8],
    }

    #[link(name = "ole32")]
    extern "system" {
        fn CoInitializeEx(pv_reserved: *mut c_void, dw_co_init: u32) -> i32;
        fn CoUninitialize();
        fn CoCreateInstance(
            rclsid: *const Guid,
            p_unk_outer: *mut c_void,
            dw_cls_context: u32,
            riid: *const Guid,
            ppv: *mut *mut c_void,
        ) -> i32;
        fn CoTaskMemFree(pv: *mut c_void);
    }

    #[link(name = "shell32")]
    extern "system" {
        fn SHCreateItemFromParsingName(
            psz_path: *const u16,
            pbc: *mut c_void,
            riid: *const Guid,
            ppv: *mut *mut c_void,
        ) -> i32;
    }

    struct ComGuard(bool);
    impl Drop for ComGuard {
        fn drop(&mut self) {
            if self.0 {
                unsafe { CoUninitialize() };
            }
        }
    }

    struct ComPtr(*mut c_void);
    impl ComPtr {
        #[inline]
        unsafe fn vtbl(&self) -> *const *const c_void {
            *(self.0 as *const *const *const c_void)
        }
    }
    impl Drop for ComPtr {
        fn drop(&mut self) {
            if !self.0.is_null() {
                unsafe {
                    let rel: extern "system" fn(*mut c_void) -> u32 =
                        std::mem::transmute(*self.vtbl().add(2));
                    rel(self.0);
                }
            }
        }
    }

    const CLSID_FILE_OPEN_DIALOG: Guid = Guid {
        data1: 0xdc1c_5a9c,
        data2: 0xe88a,
        data3: 0x4dde,
        data4: [0xa5, 0xa1, 0x60, 0xf8, 0x2a, 0x20, 0xae, 0xf7],
    };
    const IID_I_FILE_OPEN_DIALOG: Guid = Guid {
        data1: 0xd57c_7288,
        data2: 0xd4ad,
        data3: 0x4768,
        data4: [0xbe, 0x02, 0x9d, 0x96, 0x95, 0x32, 0xd9, 0x60],
    };
    const IID_I_SHELL_ITEM: Guid = Guid {
        data1: 0x4382_6d1e,
        data2: 0xe718,
        data3: 0x42ee,
        data4: [0xbc, 0x55, 0xa1, 0xe2, 0x61, 0xc3, 0x7b, 0xfe],
    };

    const COINIT_APARTMENTTHREADED: u32 = 0x2;
    const COINIT_DISABLE_OLE1DDE: u32 = 0x4;
    const CLSCTX_INPROC_SERVER: u32 = 0x1;
    const FOS_PICKFOLDERS: u32 = 0x0000_0020;
    const FOS_FORCEFILESYSTEM: u32 = 0x0000_0040;
    const FOS_PATHMUSTEXIST: u32 = 0x0000_0800;
    const SIGDN_FILESYSPATH: u32 = 0x8005_8000;

    unsafe {
        let hr_init = CoInitializeEx(
            std::ptr::null_mut(),
            COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE,
        );
        // S_OK (0) ya da S_FALSE (1) durumunda Drop sırasında CoUninitialize gerekir.
        let _com = ComGuard(hr_init == 0 || hr_init == 1);
        if hr_init < 0 && hr_init != -2147417850i32 {
            // RPC_E_CHANGED_MODE değilse hata
            return None;
        }

        let mut dlg_raw: *mut c_void = std::ptr::null_mut();
        let hr = CoCreateInstance(
            &CLSID_FILE_OPEN_DIALOG,
            std::ptr::null_mut(),
            CLSCTX_INPROC_SERVER,
            &IID_I_FILE_OPEN_DIALOG,
            &mut dlg_raw,
        );
        if hr < 0 || dlg_raw.is_null() {
            return None;
        }
        let dlg = ComPtr(dlg_raw);

        // Mevcut seçenekleri al ve klasör seçme bayraklarını ekle
        let get_options: extern "system" fn(*mut c_void, *mut u32) -> i32 =
            std::mem::transmute(*dlg.vtbl().add(10));
        let set_options: extern "system" fn(*mut c_void, u32) -> i32 =
            std::mem::transmute(*dlg.vtbl().add(9));
        let mut opts = 0u32;
        if get_options(dlg.0, &mut opts) >= 0 {
            let _ = set_options(dlg.0, opts | FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST);
        }

        // Pencere başlığı
        let wtitle = wide_z(title);
        let set_title: extern "system" fn(*mut c_void, *const u16) -> i32 =
            std::mem::transmute(*dlg.vtbl().add(17));
        let _ = set_title(dlg.0, wtitle.as_ptr());

        // Başlangıç klasörü
        if let Some(dir) = initial_dir.filter(|p| p.exists()) {
            let wdir = wide_z(&dir.to_string_lossy());
            let mut folder_raw: *mut c_void = std::ptr::null_mut();
            if SHCreateItemFromParsingName(
                wdir.as_ptr(),
                std::ptr::null_mut(),
                &IID_I_SHELL_ITEM,
                &mut folder_raw,
            ) >= 0
                && !folder_raw.is_null()
            {
                let folder_item = ComPtr(folder_raw);
                let set_folder: extern "system" fn(*mut c_void, *mut c_void) -> i32 =
                    std::mem::transmute(*dlg.vtbl().add(12));
                let _ = set_folder(dlg.0, folder_item.0);
            }
        }

        // Show(hwndOwner)
        let show: extern "system" fn(*mut c_void, *mut c_void) -> i32 =
            std::mem::transmute(*dlg.vtbl().add(3));
        if show(dlg.0, owner_hwnd as *mut c_void) < 0 {
            return None; // İptal veya hata
        }

        // GetResult(&shell_item)
        let mut item_raw: *mut c_void = std::ptr::null_mut();
        let get_result: extern "system" fn(*mut c_void, *mut *mut c_void) -> i32 =
            std::mem::transmute(*dlg.vtbl().add(20));
        if get_result(dlg.0, &mut item_raw) < 0 || item_raw.is_null() {
            return None;
        }
        let item = ComPtr(item_raw);

        // IShellItem::GetDisplayName(SIGDN_FILESYSPATH, &ptr)
        let mut path_ptr: *mut u16 = std::ptr::null_mut();
        let get_display_name: extern "system" fn(*mut c_void, u32, *mut *mut u16) -> i32 =
            std::mem::transmute(*item.vtbl().add(5));
        if get_display_name(item.0, SIGDN_FILESYSPATH, &mut path_ptr) < 0 || path_ptr.is_null() {
            return None;
        }

        let mut len = 0usize;
        while *path_ptr.add(len) != 0 {
            len += 1;
        }
        let slice = std::slice::from_raw_parts(path_ptr, len);
        let result = String::from_utf16_lossy(slice);
        CoTaskMemFree(path_ptr as *mut c_void);
        if result.trim().is_empty() {
            None
        } else {
            Some(result)
        }
    }
}

#[cfg(not(windows))]
pub fn pick_folder_dialog(
    _owner_hwnd: isize,
    _title: &str,
    _initial_dir: Option<&std::path::Path>,
) -> Option<String> {
    None
}
