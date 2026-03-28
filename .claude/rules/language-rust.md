# Rust Standards

- `cargo clippy -- -D warnings` — zero warnings policy
- Error handling: `thiserror` for library errors, `anyhow` for application errors
- No hand-rolled crypto — use `ring`, `rustls`, or `openssl` crate
- Format with `cargo fmt` before commit
- Prefer `&str` over `String` in function parameters where possible
- Use `#[must_use]` on functions returning Result/Option that callers should handle
