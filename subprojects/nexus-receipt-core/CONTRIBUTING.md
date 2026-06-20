# Contributing to nexus-receipt-core

Thank you for your interest in `nexus-receipt-core`. This document outlines the process for contributing.

## Getting Started

1. Fork the repository
2. Clone locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/nexus-receipt-core.git
   cd nexus-receipt-core
   ```
3. Build and run tests:
   ```bash
   cargo test
   ```

## Making Changes

### Code Style

- Follow standard Rust conventions (`cargo fmt`, `cargo clippy`)
- All new functionality must include tests
- Integration tests must pass for all existing fixtures

### Testing

Before submitting a PR:

```bash
cargo test --lib          # unit tests
cargo test --test integration  # integration tests
python3 schemas/python/check_parity.py  # Rust-Python parity
```

### Adding Fixtures

New fixtures should be placed in `schemas/python/fixtures/` and must:
- Be valid JSON (unless specifically testing parse errors)
- Include a corresponding test case in `integration.rs`
- Document expected behavior in `verification-evidence/fixture-manifest.md`

### Commit Messages

Follow conventional commits:
```
feat: add support for X
fix: resolve hash comparison issue
test: add integration test for edge case
docs: update README with new usage examples
```

## Pull Request Process

1. Ensure all tests pass
2. Update documentation if changing public API
3. Submit PR with description of changes
4. Maintainers will review and merge

## License

By contributing, you agree that your contributions will be licensed under the Apache License, Version 2.0.
