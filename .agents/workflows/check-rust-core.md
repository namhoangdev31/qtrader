---
description: description: Test and check Rust core modules
---

This workflow validates the `rust_core` library utilizing standard rust toolchains.

// turbo-all

1. Format Rust code: `cd rust_core && cargo fmt`
2. Lint Rust code: `cd rust_core && cargo clippy -- -D warnings`
3. Run Rust unit tests: `cd rust_core && cargo test`
