use pyo3::prelude::*;
use std::fs;
use std::path::Path;
use glob::Pattern;
use ignore::WalkBuilder;

#[pyclass]
#[derive(Clone, Debug)]
pub struct FileMetadata {
    #[pyo3(get)]
    pub path: String,
    #[pyo3(get)]
    pub size: u64,
    #[pyo3(get)]
    pub last_modified: f64,
    #[pyo3(get)]
    pub is_text: bool,
}

#[pyfunction]
pub fn fast_scan(py: Python<'_>, root: String, patterns: Vec<String>) -> PyResult<Vec<FileMetadata>> {
    // Release the GIL during physical filesystem traversal
    py.allow_threads(|| {
        let root_path = Path::new(&root);
        let mut results = Vec::new();

        // Compile glob patterns
        let glob_patterns: Vec<Pattern> = patterns
            .iter()
            .filter_map(|p| Pattern::new(p).ok())
            .collect();

        // ignore crate's WalkBuilder automatically respects .gitignore and ignores hidden files
        let walker = WalkBuilder::new(root_path)
            .hidden(true)       // Ignore hidden files and directories
            .git_ignore(true)   // Respect .gitignore
            .build();

        for entry in walker {
            let entry = match entry {
                Ok(e) => e,
                Err(_) => continue,
            };

            let path = entry.path();
            
            // Explicitly filter out build, dependency, scratch, and perplexity artifacts to align with Python and eliminate drift
            let has_ignored_component = path.components().any(|c| {
                let s = c.as_os_str().to_string_lossy();
                s.starts_with('.') || s == "target" || s == "scratch" || s == "perplexity"
            });
            if has_ignored_component {
                continue;
            }

            if !path.is_file() {
                continue;
            }

            // Extract relative path to match glob patterns
            let rel_path = match path.strip_prefix(root_path) {
                Ok(p) => p,
                Err(_) => continue,
            };
            let rel_path_str = rel_path.to_string_lossy();

            let is_match = if glob_patterns.is_empty() {
                true
            } else {
                glob_patterns.iter().any(|pat| pat.matches(&rel_path_str))
            };

            if is_match {
                let metadata = match fs::metadata(path) {
                    Ok(m) => m,
                    Err(_) => continue,
                };

                let size = metadata.len();
                let last_modified = metadata
                    .modified()
                    .ok()
                    .and_then(|t| t.duration_since(SystemTime::UNIX_EPOCH).ok())
                    .map(|d| d.as_secs_f64())
                    .unwrap_or(0.0);

                let is_text = is_text_file(path).unwrap_or(true);

                results.push(FileMetadata {
                    path: path.to_string_lossy().to_string(),
                    size,
                    last_modified,
                    is_text,
                });
            }
        }

        Ok(results)
    })
}

// Simple heuristic check for text file (first 1024 bytes containing no null characters)
fn is_text_file(path: &Path) -> std::io::Result<bool> {
    use std::io::Read;
    
    let mut file = fs::File::open(path)?;
    let mut buffer = [0; 1024];
    let n = file.read(&mut buffer)?;

    if n == 0 {
        return Ok(true);
    }

    for &b in &buffer[..n] {
        if b == 0 {
            return Ok(false);
        }
    }

    Ok(true)
}
use std::time::SystemTime;
