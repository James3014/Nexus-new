// Acheron Paradox: Unsafe + Lifetime Contamination
pub struct GhostRef {
    ptr: *mut u8,
}

impl GhostRef {
    pub unsafe fn leak_to_python(&self) -> &'static mut u8 {
        // [SIGHTING] The root of spectral leak
        &mut *self.ptr
    }
}
