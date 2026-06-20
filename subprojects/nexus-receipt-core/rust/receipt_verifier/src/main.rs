//! Minimal CLI: `receipt verify <file>` (always strict)
//!
//! Usage:
//!   receipt verify <file>                    # full verification (hash + schema + evidence)
//!   receipt verify <file> --skip-hash        # skip hash check, still check schema + evidence
//!
//! Exit codes:
//!   0 — is_valid() is true (all checks passed)
//!   1 — verification failed or file not found

use std::fs;
use receipt_verifier::{verify_receipt, REQUIRED_FIELDS, EVIDENCE_REQUIRED_FIELDS};

fn print_usage() {
    eprintln!("Usage:");
    eprintln!("  receipt verify <file>                    Full verification (default)");
    eprintln!("  receipt verify <file> --skip-hash        Skip hash check, check schema + evidence");
    std::process::exit(1);
}

fn main() {
    let args: Vec<String> = std::env::args().collect();

    if args.len() < 3 || args[1] != "verify" {
        print_usage();
    }

    let filepath = &args[2];
    let skip_hash = args.iter().any(|a| a == "--skip-hash");

    let content = match fs::read_to_string(filepath) {
        Ok(c) => c,
        Err(e) => {
            eprintln!("Error reading {}: {}", filepath, e);
            std::process::exit(1);
        }
    };

    let claimed_hash: Option<String> = if skip_hash {
        None
    } else {
        serde_json::from_str::<serde_json::Value>(&content)
            .ok()
            .and_then(|v| v.get("claimed_hash").and_then(|h| h.as_str().map(String::from)))
    };

    let result = verify_receipt(
        &content,
        claimed_hash.as_deref(),
        REQUIRED_FIELDS,
        EVIDENCE_REQUIRED_FIELDS,
    );

    // Output JSON result
    let output = serde_json::to_string_pretty(&result).unwrap();
    println!("{}", output);

    // Exit code: 0 if valid, 1 if failed
    if result.is_valid() {
        std::process::exit(0);
    } else {
        std::process::exit(1);
    }
}
