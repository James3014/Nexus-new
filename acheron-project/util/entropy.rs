pub fn recursive_entropy(n: usize) -> Vec<usize> {
    if n == 0 {
        return vec![];
    }
    let mut res = recursive_entropy(n - 1);
    res.push(n);
    res
}
