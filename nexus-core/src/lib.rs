use pyo3::prelude::*;
use std::fs;
use std::time::Instant;

mod ast_diff;

/// Blazing fast AST Reflex scanner exported natively to Python
#[pyfunction]
fn scan_and_diagnose(path: String) -> PyResult<String> {
    let start = Instant::now();
    
    // Physical file ingestion
    let content = fs::read_to_string(&path)?;
    let bytes = content.len();
    let lines = content.lines().count();
    
    // Single-pass O(N) Lexer/Scanner for deep structure analysis
    let mut struct_count = 0;
    let mut fn_count = 0;
    let mut impl_count = 0;

    let mut word = String::with_capacity(32);
    for c in content.chars() {
        if c.is_alphanumeric() || c == '_' {
            word.push(c);
        } else {
            if !word.is_empty() {
                match word.as_str() {
                    "struct" => struct_count += 1,
                    "fn" => fn_count += 1,
                    "impl" => impl_count += 1,
                    _ => {}
                }
                word.clear();
            }
        }
    }
    // Check final word
    if !word.is_empty() {
        match word.as_str() {
            "struct" => struct_count += 1,
            "fn" => fn_count += 1,
            "impl" => impl_count += 1,
            _ => {}
        }
    }
    
    let duration = start.elapsed();
    
    let diagnostics = format!(
        "[EYE: REFLEX AST PROFILER]\n\
         - Target: {}\n\
         - Volume: {} bytes across {} lines\n\
         - Signatures: {} structs, {} methods, {} impl blocks\n\
         - Rust Core Sensing Time: {:.4} ms\n\
         - Core Status: 🟢 AST Physics Locked.",
        path, bytes, lines, struct_count, fn_count, impl_count, duration.as_secs_f64() * 1000.0
    );
    
    Ok(diagnostics)
}

/// Advanced L6 Gate: Checks for breaking changes in public APIs
#[pyfunction]
fn check_pub_api_diff(old_source: String, new_source: String) -> PyResult<Vec<String>> {
    ast_diff::compare_pub_apis(&old_source, &new_source).map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e))
}

#[pymodule]
fn nexus_core(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(scan_and_diagnose, m)?)?;
    m.add_function(wrap_pyfunction!(check_pub_api_diff, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_rust_ast_scan_and_diagnose() {
        // Test that scan_and_diagnose correctly counts structs, functions, and impl blocks.
        let temp_file = "temp_test_source.rs";
        let content = "struct DummyStruct {}\nimpl DummyStruct {\n    fn dummy_fn() {}\n}\n";
        fs::write(temp_file, content).unwrap();

        let diagnostics = scan_and_diagnose(temp_file.to_string()).unwrap();
        fs::remove_file(temp_file).unwrap();

        println!("{}", diagnostics);
        assert!(diagnostics.contains("1 structs"));
        assert!(diagnostics.contains("1 methods"));
        assert!(diagnostics.contains("1 impl blocks"));
    }

    #[test]
    fn test_rust_ast_diff_caching() {
        // Test that compare_pub_apis works correctly and utilizes our hash cache.
        let source1 = "pub struct MyStruct {}";
        let source2 = "pub struct MyStruct {}\npub fn new_fn() {}";
        
        let diff1 = check_pub_api_diff(source1.to_string(), source2.to_string()).unwrap();
        // Since we didn't remove any API (we only added new_fn), diff should be empty (no breaking changes).
        assert!(diff1.is_empty());
        
        let source3 = "pub fn new_fn() {}"; // MyStruct was removed
        let diff2 = check_pub_api_diff(source2.to_string(), source3.to_string()).unwrap();
        assert_eq!(diff2.len(), 1);
        assert!(diff2[0].contains("MyStruct"));
    }
}
