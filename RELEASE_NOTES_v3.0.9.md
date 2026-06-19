# Release Notes — v3.0.9 (v3.0 Stable)

Consolidates patch releases v3.0.1–v3.0.8 into the stable v3.0 line.

## v3.0.1 — Stability
- CLI integration tests (`forge compile` + `forge run`)
- Windows `x64/Debug/run_tests.exe` binary discovery

## v3.0.2 — Scan
- Scan cache invalidates on header mtime change
- Conditional class/enum unit tests
- Optional libclang CI job

## v3.0.3 — Compile UX
- CMake error `hints` in compile failures
- `forge compile --from-probe <sdk_root>`

## v3.0.4 — Coverage
- Linux coverage pipeline test
- lcov CI artifact upload

## v3.0.5 — Mocks
- End-to-end mock generation for `test_sdk_cpp` Calculator::div
- `mock_<ClassName>.hpp` output naming

## v3.0.6 — Medium SDK
- New `test_sdk_medium/` fixture
- Integration: scan → probe → pkg-config compile → run

## v3.0.7 — Agent Docs
- forge.md / SKILL failure recovery and CMake error table
- REGISTER_AGENT `hints` field

## v3.0.8 — Performance
- `compile_duration_sec` in compile JSON output

## Upgrade

```bash
git pull && pip install -e .
```

Release title: **v3.0.9 — v3.0 Stable**
