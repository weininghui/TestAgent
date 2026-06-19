"""Scaffold forge test projects."""

from __future__ import annotations

from pathlib import Path


FORGE_YAML_TEMPLATE = """# SDK Test Forge project config (v4.1)
sdk_root: {sdk_root}
tests_dir: {tests_dir}
build_dir: {build_dir}

sdk_include_dirs:
{include_lines}
sdk_lib_dirs:
{lib_lines}
link_libraries:
{link_lines}

gtest_source: auto
gtest_version: auto

# Quality gate (v4.1)
scaffold_quality_gate: true
max_placeholder_ratio: 0.5
quality_gate_mode: warn
auto_report: true
"""


SAMPLE_TEST = """#include <gtest/gtest.h>

TEST(SampleTest, Placeholder) {{
    EXPECT_TRUE(true);
}}
"""


def init_project_impl(
    target_dir: str,
    sdk_root: str = "",
    project_name: str = "sdk_tests",
) -> dict:
    root = Path(target_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)

    tests_dir = root / "tests"
    build_dir = root / "build"
    tests_dir.mkdir(exist_ok=True)
    build_dir.mkdir(exist_ok=True)

    sample = tests_dir / f"{project_name}_test.cpp"
    if not sample.exists():
        sample.write_text(SAMPLE_TEST, encoding="utf-8")

    sdk = sdk_root or "../sdk"
    config_path = root / ".forge.yaml"
    if not config_path.exists():
        include_lines = f'  - "{sdk}/include"' if sdk else "  []"
        lib_lines = f'  - "{sdk}/build"' if sdk else "  []"
        link_lines = "  []"
        config_path.write_text(
            FORGE_YAML_TEMPLATE.format(
                sdk_root=sdk,
                tests_dir="tests",
                build_dir="build",
                include_lines=include_lines,
                lib_lines=lib_lines,
                link_lines=link_lines,
            ),
            encoding="utf-8",
        )

    return {
        "status": "ok",
        "project_root": str(root),
        "tests_dir": str(tests_dir),
        "build_dir": str(build_dir),
        "config_file": str(config_path),
        "sample_test": str(sample),
    }
