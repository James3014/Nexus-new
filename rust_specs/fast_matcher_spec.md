# Rust Module Spec: FastMatcher (Phase 1)
# ID: NEXUS-RUST-001
# Target: lib.rs / scanner.rs

## 1. Problem Statement
Current Python implementation performs redundant directory tree walks (O(K*N)) for every task phase to extract file metadata and search for patterns. 
- **Avg Impact**: 8.2s per task.
- **Root Cause**: Python's `os.walk` and string matching lack the parallel efficiency of native OS level file scanning.

## 2. Technical Objective
Implement a high-performance file scanner in Rust to replace the Python-based tree walker.
- **Architecture**: Rust multithreaded (Rayon) parallel iterator.
- **Binding**: PyO3 for seamless Python integration.
- **Data Flow**: Python passes (Root Dir, Glob Patterns) -> Rust returns (Flat list of Matched Files + Metadata).

## 3. API Contract (Draft)
```rust
#[pyfunction]
fn fast_scan(root: String, patterns: Vec<String>) -> PyResult<Vec<FileMetadata>> {
    // 1. Initialize parallel scanner
    // 2. Filter using ignore list (.gitignore, .nexus-ignore)
    // 3. Match glob patterns
    // 4. Return metadata struct
}

#[pyclass]
struct FileMetadata {
    path: String,
    size: u64,
    last_modified: f64,
    is_text: bool,
}
```

## 4. Safety & Governance
- **Read-Only**: The module MUST NOT have write permissions to the workspace.
- **Memory Bounded**: Implementation must limit the number of open file descriptors.
- **Ignore-Aware**: Must strictly respect `.gitignore` to avoid scanning unwanted artifacts.

## 5. Success Metrics
- **Performance**: Scan time < 500ms for 100k files.
- **Memory**: Peak RSS increase < 50MB.
- **Integrity**: 100% path parity with existing Python scanner.
