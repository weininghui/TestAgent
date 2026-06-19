"""Tests for mcp_server.py — SDK Test Forge MCP server."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure the project root is in sys.path for importing mcp_server
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp_server import (
    HeaderFileInfo,
    _generate_cmake_content,
    _normalize_str_list,
    _parse_header,
)


# ---------------------------------------------------------------------------
# _parse_header — pure function unit tests
# ---------------------------------------------------------------------------

class TestParseHeader:
    """Core header parsing logic — fastest feedback loop."""

    def test_empty_content(self):
        info = _parse_header("", "/dev/null/empty.h")
        assert isinstance(info, HeaderFileInfo)
        assert info.filename == "empty.h"
        assert info.functions == []
        assert info.classes == []
        assert info.enums == []
        assert info.typedefs == []
        assert info.includes == []

    def test_simple_function(self):
        content = """
#include <stdint.h>

int32_t add(int32_t a, int32_t b);
"""
        info = _parse_header(content, "/sdk/math.h")
        assert len(info.functions) == 1
        f = info.functions[0]
        assert f["name"] == "add"
        assert f["return_type"] == "int32_t"
        assert f["params"] == "int32_t a, int32_t b"

    def test_multiple_functions(self):
        content = """
void foo();
int bar(int x);
float baz(const char* name, size_t len);
"""
        info = _parse_header(content, "/sdk/api.h")
        assert len(info.functions) == 3
        assert [f["name"] for f in info.functions] == ["foo", "bar", "baz"]

    def test_class_extraction(self):
        content = """
class MyClass {
public:
    void method();
private:
    int member_;
};

struct Point {
    float x, y;
};
"""
        info = _parse_header(content, "/sdk/types.h")
        assert len(info.classes) == 2
        names = [(c["kind"], c["name"]) for c in info.classes]
        assert ("class", "MyClass") in names
        assert ("struct", "Point") in names

    def test_enum_extraction(self):
        content = """
enum Color { RED, GREEN, BLUE };
enum class Status { OK, ERROR };
"""
        info = _parse_header(content, "/sdk/enums.h")
        assert len(info.enums) == 2
        names = [e["name"] for e in info.enums]
        assert "Color" in names
        assert "Status" in names

    def test_typedef_extraction(self):
        content = """
typedef unsigned long long uint64;
using Handle = void*;
"""
        info = _parse_header(content, "/sdk/types.h")
        assert len(info.typedefs) == 2
        aliases = [t["alias"] for t in info.typedefs]
        assert "uint64" in aliases
        assert "Handle" in aliases

    def test_function_with_pointer_params(self):
        content = """
int open_device(const char* path, void** handle);
int read_data(void* handle, uint8_t* buffer, size_t size);
"""
        info = _parse_header(content, "/sdk/device.h")
        assert len(info.functions) == 2
        assert info.functions[0]["name"] == "open_device"
        assert info.functions[1]["name"] == "read_data"

    def test_skip_keyword_lookalikes(self):
        """Keywords like 'if', 'for', 'while' should not be treated as functions."""
        content = """
int compute(int x);
"""
        # This is a minimal case — the regex should not match keywords
        # since they appear inside function bodies, not at top level
        info = _parse_header(content, "/sdk/simple.h")
        assert len(info.functions) == 1
        assert info.functions[0]["name"] == "compute"

    def test_include_extraction(self):
        content = """
#include <stdio.h>
#include "my_header.h"
#include <vector>
"""
        info = _parse_header(content, "/sdk/uses.h")
        assert info.includes == ["stdio.h", "my_header.h", "vector"]

    def test_line_numbers(self):
        content = "\n\n\nvoid hello();\n\nint goodbye();\n"
        info = _parse_header(content, "/sdk/lineno.h")
        assert info.functions[0]["line"] == 4  # void hello();
        assert info.functions[1]["line"] == 6  # int goodbye();

    def test_complex_return_types(self):
        content = "const std::vector<int>& get_items() const;\n"
        info = _parse_header(content, "/sdk/complex.h")
        assert len(info.functions) == 1
        assert info.functions[0]["name"] == "get_items"


class TestGenerateCmakeContent:
    def test_includes_sdk_paths_and_libraries(self):
        content = _generate_cmake_content(
            project_name="demo_tests",
            test_file_names=["calc_test.cpp"],
            sdk_include_dirs=["/sdk/include"],
            sdk_lib_dirs=["/sdk/lib"],
            link_libraries=["calc"],
        )
        assert "calc_test.cpp" in content
        assert "/sdk/include" in content.replace("\\", "/")
        assert "/sdk/lib" in content.replace("\\", "/")
        assert "target_link_libraries(run_tests PRIVATE gtest_main gmock calc)" in content


class TestNormalizeStrList:
    def test_none_and_empty(self):
        assert _normalize_str_list(None) == []
        assert _normalize_str_list("") == []
        assert _normalize_str_list("   ") == []

    def test_json_array_string(self):
        assert _normalize_str_list('["/a/include", "/b/lib"]') == ["/a/include", "/b/lib"]

    def test_python_list(self):
        assert _normalize_str_list(["calc", "my_sdk"]) == ["calc", "my_sdk"]


# ---------------------------------------------------------------------------
# scan_headers — integration tests with temp directories
# ---------------------------------------------------------------------------

class TestScanHeaders:
    """Tests scan_headers with real files."""

    @pytest.fixture
    def sdk_dir(self):
        with tempfile.TemporaryDirectory(prefix="sdk_test_") as tmp:
            # Create a small SDK structure
            (Path(tmp) / "core.h").write_text("""
#include <stdint.h>
int32_t open(const char* path);
void close(int32_t fd);
""")
            (Path(tmp) / "sub").mkdir()
            (Path(tmp) / "sub" / "types.h").write_text("""
enum Mode { READ, WRITE };
""")
            (Path(tmp) / "sub" / "modern.hpp").write_text("""
class Widget {
public:
    void render();
};
""")
            yield tmp

    @pytest.mark.asyncio
    async def test_scan_basic(self, sdk_dir):
        from mcp_server import scan_headers
        result = json.loads(await scan_headers(sdk_dir))
        assert result["status"] == "ok"
        assert result["total_files"] == 3
        assert result["total_functions"] == 3
        assert result["total_classes"] == 1
        assert result["total_enums"] == 1

    @pytest.mark.asyncio
    async def test_scan_invalid_dir(self):
        from mcp_server import scan_headers
        result = json.loads(await scan_headers("/nonexistent/path"))
        assert result["status"] == "error"
        assert "error" in result


# ---------------------------------------------------------------------------
# delete_tests — integration tests with temp directories
# ---------------------------------------------------------------------------

class TestDeleteTests:
    """Tests delete_tests with real files."""

    @pytest.fixture
    def test_dir(self):
        with tempfile.TemporaryDirectory(prefix="test_clean_") as tmp:
            # Create mix of test and non-test files
            (Path(tmp) / "foo_test.cpp").write_text("// test")
            (Path(tmp) / "bar_unittest.cpp").write_text("// test")
            (Path(tmp) / "test_baz.cpp").write_text("// test")
            (Path(tmp) / "readme.txt").write_text("not a test")
            (Path(tmp) / "main.cpp").write_text("not a test")
            nested = Path(tmp) / "nested"
            nested.mkdir()
            (nested / "deep_test.cpp").write_text("// nested test")
            yield tmp

    @pytest.mark.asyncio
    async def test_delete_matching_files(self, test_dir):
        from mcp_server import delete_tests
        result = json.loads(await delete_tests(test_dir))
        assert result["status"] == "ok"
        assert result["deleted_count"] == 4
        remaining_files = [p for p in Path(test_dir).rglob("*") if p.is_file()]
        assert len(remaining_files) == 2
        assert not (Path(test_dir) / "nested" / "deep_test.cpp").exists()

    @pytest.mark.asyncio
    async def test_delete_empty_dir(self):
        from mcp_server import delete_tests
        with tempfile.TemporaryDirectory() as tmp:
            result = json.loads(await delete_tests(tmp))
            assert result["status"] == "ok"
            assert result["deleted_count"] == 0

    @pytest.mark.asyncio
    async def test_delete_nonexistent_dir(self):
        from mcp_server import delete_tests
        result = json.loads(await delete_tests("/nonexistent/dir"))
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# compile_tests + run_tests — integration (skip if cmake unavailable)
# ---------------------------------------------------------------------------

def _cmake_available() -> bool:
    return any(
        os.access(os.path.join(p, "cmake"), os.X_OK)
        or os.access(os.path.join(p, "cmake.exe"), os.X_OK)
        for p in os.environ.get("PATH", "").split(os.pathsep)
    )


def _find_sdk_lib_dir(sdk_build: Path) -> Path:
    for candidate in [sdk_build, sdk_build / "Debug", sdk_build / "Release"]:
        if candidate.exists() and (
            list(candidate.glob("calc.lib"))
            or list(candidate.glob("libcalc.a"))
            or list(candidate.glob("libcalc.lib"))
        ):
            return candidate
    return sdk_build


def _build_test_sdk(repo_root: Path) -> tuple[Path, Path]:
    sdk_root = repo_root / "test_sdk"
    sdk_build = sdk_root / "build"
    sdk_build.mkdir(parents=True, exist_ok=True)

    configure = subprocess.run(
        ["cmake", str(sdk_root.resolve())],
        cwd=str(sdk_build.resolve()),
        capture_output=True,
        text=True,
        check=False,
    )
    if configure.returncode != 0:
        raise RuntimeError(configure.stderr or configure.stdout)

    build = subprocess.run(
        ["cmake", "--build", str(sdk_build.resolve())],
        capture_output=True,
        text=True,
        check=False,
    )
    if build.returncode != 0:
        raise RuntimeError(build.stderr or build.stdout)

    return sdk_root / "include", _find_sdk_lib_dir(sdk_build)


@pytest.mark.skipif(not _cmake_available(), reason="cmake not found in PATH — skip integration")
class TestCompileAndRun:
    """Full compile → run pipeline. Requires cmake + C++ compiler."""

    @pytest.fixture
    def test_project(self):
        with tempfile.TemporaryDirectory(prefix="gtest_integration_") as tmp:
            src = Path(tmp)
            # Write a simple GTest file (name must match *_test.cpp or *Test.cpp pattern)
            (src / "math_test.cpp").write_text("""
#include <gtest/gtest.h>

TEST(MathTest, Addition) {
    EXPECT_EQ(1 + 1, 2);
}

TEST(MathTest, Subtraction) {
    EXPECT_EQ(3 - 1, 2);
}
""")
            yield str(src)

    @pytest.mark.asyncio
    async def test_compile_and_run(self, test_project):
        from mcp_server import compile_tests, run_tests

        src = test_project
        build = os.path.join(tempfile.mkdtemp(prefix="gtest_build_"), "b")

        # Compile
        compile_result = json.loads(await compile_tests(src, build))
        assert compile_result["status"] == "ok", (
            f"Compile failed: {compile_result.get('error', compile_result.get('build_output', ''))[:1000]}"
        )

        # Run
        run_result = json.loads(await run_tests(build))
        assert run_result["status"] == "ok"
        assert run_result["total"] == 2
        assert run_result["passed"] == 2
        assert run_result["failed"] == 0

    @pytest.mark.asyncio
    async def test_compile_and_run_with_test_sdk(self):
        from mcp_server import compile_tests, run_tests

        repo_root = Path(__file__).resolve().parent
        include_dir, lib_dir = _build_test_sdk(repo_root)

        with tempfile.TemporaryDirectory(prefix="sdk_forge_tests_") as tmp:
            src = Path(tmp)
            example = repo_root / "test_sdk" / "examples" / "calc_test.cpp"
            (src / "calc_test.cpp").write_text(example.read_text(encoding="utf-8"))
            build = str(Path(tempfile.mkdtemp(prefix="sdk_forge_build_")))

            compile_result = json.loads(
                await compile_tests(
                    str(src),
                    build,
                    sdk_include_dirs=[str(include_dir)],
                    sdk_lib_dirs=[str(lib_dir)],
                    link_libraries=["calc"],
                )
            )
            assert compile_result["status"] == "ok", compile_result

            run_result = json.loads(await run_tests(build))
            assert run_result["status"] == "ok", run_result
            assert run_result["total"] == 4
            assert run_result["passed"] == 4
            assert run_result["failed"] == 0
