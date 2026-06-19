# Release Notes — v4.5.2 (Agent-First Hardening)

Consolidates **v4.1–v4.5.2**: quality gate, scan/codegen depth, benchmark, toolchain auto-install, full Agent environment setup.

## Highlights

### Quality gate (v4.1)
- `.forge.yaml`: `scaffold_quality_gate`, `max_placeholder_ratio`, `quality_gate_mode: warn|block`
- `build_tests` runs gate before compile; `scaffold_quality_blocked` when ratio too high
- CLI `--skip-quality-gate`; smart scaffold E2E without manual EXPECT edits

### Scan & codegen (v4.2–v4.3)
- Template functions, enum `members`, per-symbol `namespace`; plan dedup
- Class methods, GMock EXPECT_CALL, typedef smoke, 2-param TEST_P, sanitizer hints

### Benchmark (v4.4)
- `forge bench` → `.forge/cache/bench_last.json`
- `examples/yaml_cpp_bench/` + CI bench job

### Toolchain & honest reports (v4.5.1)
- Detect MSVC (PATH + vswhere) and MinGW; `compiler_not_found` before CMake
- HTML **Toolchain** section — no fake PASS from generated source alone

### Full Agent environment (v4.5.2)
- **`ensure_forge_environment`** — doctor + auto-install compiler (winget/apt/brew)
- **`build_tests(auto_setup_toolchain=true)`** — default on MCP
- **`setup_cxx_toolchain(agent_mode=true)`** — no manual confirm for forge Agent
- Agent docs: start with `ensure_forge_environment`, never ask user to install VS manually

## Upgrade from v4.0.0

```bash
pip install -e .
# OpenCode plugin: robocopy / reinstall sdk-test-forge, restart OpenCode
forge doctor
ensure_forge_environment   # MCP
```

## Workflow (testers)

```
ensure_forge_environment → scan → plan → scaffold(smart) → enrich
→ build_tests(max_retries=3) → open html_path
```

---

Release title: **v4.5.2 — Agent-First Hardening**
