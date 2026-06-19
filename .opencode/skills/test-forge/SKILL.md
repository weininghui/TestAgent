---
name: test-forge
description: Scan C/C++ SDK headers, generate smart GTest code, compile and run tests with SDK linking
---

# SDK Test Forge Skill (v4.0)

## Communication / 交流语言

- **Reply in Chinese by default** when talking to the user.
- Switch to English only when the user explicitly asks in the chat.

## Workflow

### 1. Doctor + Scan + Plan

```
forge_doctor
scan_headers: { sdk_root: /path/to/sdk }
suggest_test_plan: { scan_json: ..., project_dir: ./my_tests, max_targets: 20 }
```

### 2. Smart Scaffold + Enrich

```
generate_test_skeleton: {
  output_dir: ./my_tests/tests,
  plan_json: ...,
  fidelity: smart,
  overwrite: true
}
enrich_test_cases: { project_dir: ./my_tests }
```

Agent fills `// AGENT:` markers using header excerpts from enrich briefs.

```
analyze_scaffold_quality: { project_dir: ./my_tests }
```

If `placeholder_ratio > 0.5`, continue editing before build.

### 3. Build + Auto Report

```
build_tests: { project_dir: ./my_tests, max_retries: 3 }
```

Tell user to open `html_path`. No manual `forge_report` needed.

### 4. Coverage expand (optional)

```
analyze_plan_gap: { project_dir: ./my_tests }
coverage_expand: { project_dir: ./my_tests, threshold_pct: 80 }
build_tests: { project_dir: ./my_tests }
```

### 5. Failures (confirmation gate)

```
analyze_test_failures → propose_test_fixes → apply_test_fixes(confirm=true)
```

## CLI equivalents

- `forge scaffold --fidelity smart`
- `forge enrich --project-dir .`
- `forge quality --project-dir .`
- `forge coverage-expand --project-dir .`
