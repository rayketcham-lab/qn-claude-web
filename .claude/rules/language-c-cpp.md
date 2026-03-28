# C/C++ Standards

- Build system: CMake or Make
- Compile with `-Werror` — zero warnings
- Use vetted crypto libraries only (OpenSSL, libsodium, mbedTLS)
- No `gets()`, `sprintf()`, or other unsafe string functions — use bounded variants
- Valgrind/ASan for memory testing
