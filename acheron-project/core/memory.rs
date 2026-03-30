use super::quantum::FoldedFuture;
use std::cell::RefCell;

pub struct MemoryMirror {
    pub future: FoldedFuture,
    pub phantom: RefCell<String>,  // 幽靈字段，會被宏覆寫
}

impl MemoryMirror {
    pub fn new() -> Self {
        Self {
            future: FoldedFuture::new(),
            phantom: RefCell::new("ghost".to_string()),
        }
    }
}
