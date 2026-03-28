// Advanced Repro for [ICE]: inconsistent resolution for an import (2026)
// This pattern focuses on glob-import shadowing and macro-generated re-exports.

pub mod a {
    pub struct Token;
}

pub mod b {
    pub use crate::a::Token;
}

macro_rules! bridge {
    () => {
        pub use crate::b::*;
    }
}

pub mod c {
    bridge!();
    // Path resolution here should conflict between glob(b) and direct-crate access
    // when expanded via bridge! in a nested scope.
    pub use crate::a::Token; 
}
