//! Alt süreç yaşam döngüsü.
//!
//! İndirme sırasında ffmpeg alt süreç olarak çalışır. Kullanıcı pencereyi
//! kapatınca süreç sonlanır ama Windows alt süreçleri kendiliğinden öldürmez;
//! ffmpeg arka planda indirmeye devam eder.
//!
//! Çözüm: uygulamayı `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` bayraklı bir Job
//! Object'e koymak. Job'un son handle'ı kapandığında (yani süreç çıktığında)
//! Windows job içindeki tüm süreçleri öldürür.

#[cfg(windows)]
pub fn kill_children_on_exit() {
    use std::ffi::c_void;

    const JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE: u32 = 0x0000_2000;
    const JOB_OBJECT_EXTENDED_LIMIT_INFORMATION: i32 = 9;

    #[repr(C)]
    #[derive(Default, Clone, Copy)]
    struct BasicLimit {
        per_process_user_time: i64,
        per_job_user_time: i64,
        limit_flags: u32,
        min_working_set: usize,
        max_working_set: usize,
        active_process_limit: u32,
        affinity: usize,
        priority_class: u32,
        scheduling_class: u32,
    }

    #[repr(C)]
    #[derive(Default, Clone, Copy)]
    struct IoCounters {
        read_operations: u64,
        write_operations: u64,
        other_operations: u64,
        read_bytes: u64,
        write_bytes: u64,
        other_bytes: u64,
    }

    #[repr(C)]
    #[derive(Default, Clone, Copy)]
    struct ExtendedLimit {
        basic: BasicLimit,
        io: IoCounters,
        process_memory_limit: usize,
        job_memory_limit: usize,
        peak_process_memory_used: usize,
        peak_job_memory_used: usize,
    }

    #[link(name = "kernel32")]
    extern "system" {
        fn CreateJobObjectW(attributes: *mut c_void, name: *const u16) -> *mut c_void;
        fn SetInformationJobObject(
            job: *mut c_void,
            info_class: i32,
            info: *mut c_void,
            info_len: u32,
        ) -> i32;
        fn AssignProcessToJobObject(job: *mut c_void, process: *mut c_void) -> i32;
        fn GetCurrentProcess() -> *mut c_void;
    }

    unsafe {
        let job = CreateJobObjectW(std::ptr::null_mut(), std::ptr::null());
        if job.is_null() {
            return;
        }

        let mut info = ExtendedLimit::default();
        info.basic.limit_flags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;

        let ok = SetInformationJobObject(
            job,
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            &mut info as *mut _ as *mut c_void,
            std::mem::size_of::<ExtendedLimit>() as u32,
        );
        if ok == 0 {
            return;
        }

        // Süreç zaten başka bir job içindeyse bu çağrı başarısız olur (ör. bazı
        // başlatıcılar). O durumda sessizce devam ediyoruz.
        let _ = AssignProcessToJobObject(job, GetCurrentProcess());

        // Handle'ı bilerek sızdırıyoruz: süreç çıkarken OS kapatacak ve
        // KILL_ON_JOB_CLOSE devreye girecek.
    }
}

#[cfg(not(windows))]
pub fn kill_children_on_exit() {}
