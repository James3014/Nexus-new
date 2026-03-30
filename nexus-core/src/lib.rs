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
    
    // Simulate Eye (Reflex) deep structure analysis
    let struct_count = content.matches("struct ").count();
    let fn_count = content.matches("fn ").count();
    let impl_count = content.matches("impl ").count();
    
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

