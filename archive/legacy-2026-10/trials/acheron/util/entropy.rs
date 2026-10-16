// Acheron Paradox: Recursion Entropy
pub fn compute_entropy(n: u32) -> u32 {
    if n == 0 { return 1; }
    compute_entropy(n - 1) + 1 // [DEEP_STRETCH]
}
