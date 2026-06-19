# yaml-cpp Benchmark (v4.4)

Repeatable benchmark for SDK Test Forge smart scaffold quality and build pass rate.

## Quick start (bundled SDK)

Uses `examples/test_sdk_cpp` as a stand-in. Build the SDK first:

```bash
cmake -S ../test_sdk_cpp -B ../test_sdk_cpp/build
cmake --build ../test_sdk_cpp/build
```

Run the benchmark from this directory:

```bash
forge bench --project-dir .
```

Output: `.forge/cache/bench_last.json`

## Metrics JSON

| Field | Meaning |
|-------|---------|
| `placeholder_ratio` | Share of TODO/AGENT/EXPECT_TRUE lines in generated tests |
| `quality_gate.passed` | Whether ratio is below `max_placeholder_ratio` |
| `build_status` | Final pipeline status (`ok`, `compile_error`, etc.) |
| `test_pass_rate` | passed / total from GTest run |

## Real yaml-cpp

1. Clone and build [yaml-cpp](https://github.com/jbeder/yaml-cpp).
2. Edit `.forge.yaml`: set `sdk_root`, `sdk_include_dirs`, `sdk_lib_dirs`, `link_libraries`.
3. Run `forge bench --project-dir .`

## CI

Optional Linux job runs `forge bench --no-build` on unit-test matrix (see `.github/workflows/ci.yml`).
