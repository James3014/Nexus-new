// Repro for rust-lang/rust Issue #154296 (March 2026)
// [ICE]: inconsistent resolution for an import

mod m1 {
    mod inner { 
        pub struct S; 
    }
    pub use self::inner::*;
    
    // In Rust 2024, this shadowing combined with glob re-export 
    // triggers an inconsistency in the resolver table during macro expansion.
    pub struct S;
}

use m1::*;

fn main() {
    let _ = S;
}
