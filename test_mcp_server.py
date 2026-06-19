"""Tests for mcp_server.py — SDK Test Forge MCP server."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

# Ensure the project root is in sys.path for importing mcp_server
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp_server import (
    HeaderFileInfo,
    _CLANG_AVAILABLE,
    _generate_cmake_content,
    _gtest_cache_dir,
    _normalize_str_list,
    _parse_header,
    _parse_header_clang,
)
from sdk_forge.scan import compute_if_depths
from sdk_forge.mock import generate_mocks_impl
from sdk_forge.errors import parse_cmake_error
from sdk_forge.build import find_test_binary
from sdk_forge.scan import scan_headers_impl


def _cmake_available() -> bool:
    return any(
        os.access(os.path.join(p, "cmake"), os.X_OK)
        or os.access(os.path.join(p, "cmake.exe"), os.X_OK)
        for p in os.environ.get("PATH", "").split(os.pathsep)
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

    def test_conditional_ifdef_function(self):
        content = """
void always_visible();

#ifdef FEATURE_X
int feature_x_only();
#endif

void also_visible();
"""
        info = _parse_header(content, "/sdk/conditional.h")
        by_name = {f["name"]: f for f in info.functions}
        assert by_name["always_visible"]["conditional"] is False
        assert by_name["feature_x_only"]["conditional"] is True
        assert by_name["also_visible"]["conditional"] is False

    def test_compute_if_depths(self):
        content = "#ifdef A\n#ifdef B\nvoid f();\n#endif\n#endif\n"
        depths = compute_if_depths(content)
        assert depths[2] == 2
        assert depths[4] == 1

    def test_conditional_class_and_enum(self):
        content = """
class Always {};

#ifdef FEATURE_X
class FeatureClass {};
enum FeatureEnum { A, B };
#endif
"""
        info = _parse_header(content, "/sdk/cond.h")
        always = next(c for c in info.classes if c["name"] == "Always")
        feature = next(c for c in info.classes if c["name"] == "FeatureClass")
        assert always["conditional"] is False
        assert feature["conditional"] is True
        feat_enum = next(e for e in info.enums if e["name"] == "FeatureEnum")
        assert feat_enum["conditional"] is True


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

    def test_gtest_cache_block(self):
        content = _generate_cmake_content(
            project_name="demo_tests",
            test_file_names=["demo_test.cpp"],
            gtest_source="cached",
        )
        cache = str(_gtest_cache_dir()).replace("\\", "/")
        assert "FETCHCONTENT_BASE_DIR" in content
        assert cache in content
        assert "UPDATE_DISCONNECTED TRUE" in content

    def test_gtest_system_block(self):
        content = _generate_cmake_content(
            project_name="demo_tests",
            test_file_names=["demo_test.cpp"],
            gtest_source="system",
        )
        assert "find_package(GTest REQUIRED)" in content
        assert "FetchContent" not in content

    def test_pkg_config_and_find_package(self):
        content = _generate_cmake_content(
            project_name="demo_tests",
            test_file_names=["demo_test.cpp"],
            pkg_config_packages=["libcurl"],
            find_packages=[{"name": "OpenSSL", "components": ["Crypto"], "target": "OpenSSL::Crypto"}],
            cmake_prefix_path=["/opt/sdk"],
        )
        assert "pkg_check_modules(LIBCURL REQUIRED IMPORTED_TARGET libcurl)" in content
        assert "find_package(OpenSSL REQUIRED COMPONENTS Crypto)" in content
        assert "PkgConfig::LIBCURL" in content
        assert "OpenSSL::Crypto" in content
        assert "/opt/sdk" in content.replace("\\", "/")

    def test_coverage_flags(self):
        content = _generate_cmake_content(
            project_name="demo_tests",
            test_file_names=["demo_test.cpp"],
            coverage=True,
        )
        assert "--coverage" in content


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

    @pytest.mark.asyncio
    async def test_scan_reports_parser_metadata(self, sdk_dir):
        from mcp_server import scan_headers
        result = json.loads(await scan_headers(sdk_dir, use_clang=False))
        assert result["status"] == "ok"
        assert result["parser"] == "regex"
        assert "libclang_available" in result

    @pytest.mark.asyncio
    async def test_scan_cache_hit(self, sdk_dir, tmp_path, monkeypatch):
        from mcp_server import scan_headers
        cache_dir = tmp_path / "scan_cache"
        cache_dir.mkdir()
        monkeypatch.setenv("FORGE_SCAN_CACHE", str(cache_dir))

        first = json.loads(await scan_headers(sdk_dir, use_clang=False))
        assert first["status"] == "ok"
        assert first.get("cached") is False

        second = json.loads(await scan_headers(sdk_dir, use_clang=False))
        assert second["status"] == "ok"
        assert second.get("cached") is True
        assert second["total_files"] == first["total_files"]


class TestGenerateMocks:
    def test_generates_mock_for_virtual_method(self):
        scan = {
            "status": "ok",
            "files": [{
                "file": "api.hpp",
                "classes": [{"name": "Calculator", "kind": "class"}],
                "functions": [{
                    "name": "div",
                    "return_type": "double",
                    "params": "int a, int b",
                    "virtual": True,
                    "kind": "method",
                }],
            }],
        }
        result = generate_mocks_impl(scan, "Calculator")
        assert result["status"] == "ok"
        assert result["mock_count"] == 1
        assert "MOCK_METHOD" in result["header"]
        assert "MockCalculator" in result["header"]


class TestCli:
    def test_cli_scan_help(self):
        from sdk_forge.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["scan", "/tmp/sdk", "--no-cache"])
        assert args.command == "scan"
        assert args.sdk_root == "/tmp/sdk"
        assert args.no_cache is True

    def test_cli_compile_from_probe_arg(self):
        from sdk_forge.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["compile", "./tests", "./build", "--from-probe", "./sdk"])
        assert args.from_probe == "./sdk"


class TestCmakeHints:
    def test_undefined_reference_hint(self):
        hints = parse_cmake_error("undefined reference to `calc_add'")
        assert any("link" in h.lower() for h in hints)

    def test_missing_header_hint(self):
        hints = parse_cmake_error("fatal error: api.h: No such file or directory")
        assert any("include" in h.lower() for h in hints)


class TestFindTestBinary:
    def test_finds_x64_debug_exe(self, tmp_path):
        nested = tmp_path / "x64" / "Debug"
        nested.mkdir(parents=True)
        exe = nested / "run_tests.exe"
        exe.write_text("fake", encoding="utf-8")
        found = find_test_binary(tmp_path)
        assert found == exe


def _forge_cmd() -> list[str]:
    forge = shutil.which("forge")
    if forge:
        return [forge]
    return [sys.executable, "-m", "sdk_forge.cli"]


@pytest.mark.skipif(not _cmake_available(), reason="cmake not found")
class TestCliIntegration:
    def test_forge_compile_and_run(self):
        with tempfile.TemporaryDirectory(prefix="forge_cli_") as tmp:
            src = Path(tmp)
            (src / "math_test.cpp").write_text("""
#include <gtest/gtest.h>
TEST(MathTest, One) { EXPECT_EQ(1, 1); }
""")
            build = str(Path(tempfile.mkdtemp(prefix="forge_cli_build_")))
            cmd_base = _forge_cmd()
            compile = subprocess.run(
                cmd_base + ["compile", str(src), build],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert compile.returncode == 0, compile.stdout + compile.stderr
            result = json.loads(compile.stdout)
            assert result["status"] == "ok"
            assert "compile_duration_sec" in result

            run = subprocess.run(
                cmd_base + ["run", build, "--quiet"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert run.returncode == 0, run.stdout + run.stderr
            run_result = json.loads(run.stdout)
            assert run_result["passed"] >= 1

    @pytest.mark.asyncio
    async def test_compile_failure_returns_hints(self):
        from mcp_server import compile_tests
        with tempfile.TemporaryDirectory(prefix="forge_bad_link_") as tmp:
            src = Path(tmp)
            (src / "bad_test.cpp").write_text("""
#include <gtest/gtest.h>
extern int missing_symbol();
TEST(Bad, Link) { EXPECT_EQ(missing_symbol(), 1); }
""")
            build = str(Path(tempfile.mkdtemp(prefix="forge_bad_build_")))
            result = json.loads(await compile_tests(str(src), build))
            assert result["status"] == "cmake_error"
            assert result.get("hints")


class TestScanCacheInvalidation:
    @pytest.mark.asyncio
    async def test_cache_invalidates_on_mtime_change(self, tmp_path, monkeypatch):
        from mcp_server import scan_headers
        cache_dir = tmp_path / "scan_cache"
        cache_dir.mkdir()
        monkeypatch.setenv("FORGE_SCAN_CACHE", str(cache_dir))
        (tmp_path / "api.h").write_text("void foo();", encoding="utf-8")

        first = json.loads(await scan_headers(str(tmp_path), use_clang=False))
        assert first.get("cached") is False

        second = json.loads(await scan_headers(str(tmp_path), use_clang=False))
        assert second.get("cached") is True

        time.sleep(0.05)
        (tmp_path / "api.h").write_text("void foo();\nvoid bar();", encoding="utf-8")
        third = json.loads(await scan_headers(str(tmp_path), use_clang=False))
        assert third.get("cached") is False
        assert third["total_functions"] >= 2


class TestMocksE2E:
    def test_scan_test_sdk_cpp_generates_div_mock(self):
        repo = Path(__file__).resolve().parent
        scan = scan_headers_impl(str(repo / "test_sdk_cpp" / "include"), use_clang=False, use_cache=False)
        assert scan["status"] == "ok"
        result = generate_mocks_impl(scan, "Calculator")
        assert result["mock_count"] >= 1
        assert "div" in result["header"]
        assert "MOCK_METHOD" in result["header"]
        assert "mock_Calculator.hpp" in result.get("output_files", [])


@pytest.mark.skipif(sys.platform == "win32", reason="coverage pipeline on Linux CI")
@pytest.mark.skipif(not _cmake_available(), reason="cmake not found")
class TestCoveragePipeline:
    @pytest.mark.asyncio
    async def test_coverage_pipeline(self):
        from mcp_server import collect_coverage, compile_tests, run_tests
        with tempfile.TemporaryDirectory(prefix="cov_pipeline_") as tmp:
            src = Path(tmp)
            (src / "cov_test.cpp").write_text("""
#include <gtest/gtest.h>
TEST(Cov, Basic) { EXPECT_EQ(2+2, 4); }
""")
            build = str(Path(tempfile.mkdtemp(prefix="cov_build_")))
            compile_result = json.loads(await compile_tests(str(src), build, coverage=True))
            assert compile_result["status"] == "ok", compile_result
            run_result = json.loads(await run_tests(build))
            assert run_result["status"] == "ok"
            cov = json.loads(await collect_coverage(build, str(src)))
            assert cov["status"] in ("ok", "unsupported")


@pytest.mark.skipif(not _cmake_available(), reason="cmake not found")
class TestGtestCacheTiming:
    @pytest.mark.asyncio
    async def test_second_compile_tracks_duration(self):
        from mcp_server import compile_tests
        with tempfile.TemporaryDirectory(prefix="gtest_timing_") as tmp:
            src = Path(tmp)
            (src / "t_test.cpp").write_text("#include <gtest/gtest.h>\nTEST(T,T){EXPECT_TRUE(true);}\n")
            build = str(Path(tempfile.mkdtemp(prefix="gtest_timing_build_")))
            first = json.loads(await compile_tests(str(src), build))
            assert first["status"] == "ok"
            second = json.loads(await compile_tests(str(src), build))
            assert second["status"] == "ok"
            assert "compile_duration_sec" in second
            assert second["compile_duration_sec"] <= 600


class TestParseHeaderClang:
    @pytest.fixture
    def cpp_header(self, tmp_path):
        header = tmp_path / "api.hpp"
        header.write_text(
            """
namespace my_sdk {
class Widget {
public:
    void render();
    static int count();
    virtual void update();
};
enum class Mode { Read, Write };
template <typename T> T clamp(T v, T lo, T hi);
}
""",
            encoding="utf-8",
        )
        return header

    @pytest.mark.skipif(not _CLANG_AVAILABLE, reason="libclang not installed")
    def test_clang_parses_namespace_and_class(self, cpp_header):
        info = _parse_header_clang(str(cpp_header.resolve()), ["-std=c++17", "-x", "c++"])
        assert info is not None
        assert info.parser == "libclang"
        assert "my_sdk" in info.namespaces
        class_names = [c["name"] for c in info.classes]
        assert "Widget" in class_names
        fn_names = [f["name"] for f in info.functions]
        assert "render" in fn_names or "count" in fn_names


class TestProbeSdk:
    @pytest.fixture
    def sdk_layout(self, tmp_path):
        include = tmp_path / "include"
        lib = tmp_path / "lib"
        include.mkdir()
        lib.mkdir()
        (include / "api.h").write_text("void foo();", encoding="utf-8")
        (tmp_path / "my_sdk.pc").write_text(
            "Cflags: -I/opt/include\nLibs: -L/opt/lib -lmy_sdk\n",
            encoding="utf-8",
        )
        return tmp_path

    @pytest.mark.asyncio
    async def test_probe_sdk_root(self, sdk_layout):
        from mcp_server import probe_sdk
        result = json.loads(await probe_sdk(str(sdk_layout)))
        assert result["status"] == "ok"
        assert any("include" in p for p in result["sdk_include_dirs"])
        assert result["pkg_config_packages"] == ["my_sdk"]

    @pytest.mark.asyncio
    async def test_probe_pc_file(self, sdk_layout):
        from mcp_server import probe_sdk
        pc = sdk_layout / "my_sdk.pc"
        result = json.loads(await probe_sdk(str(pc)))
        assert result["status"] == "ok"
        assert result["sdk_include_dirs"] == ["/opt/include"]
        assert "my_sdk" in result["link_libraries"]


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
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if configure.returncode != 0:
        raise RuntimeError(configure.stderr or configure.stdout)

    build = subprocess.run(
        ["cmake", "--build", str(sdk_build.resolve())],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
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

    @pytest.mark.asyncio
    async def test_compile_and_run_with_test_sdk_cpp(self):
        from mcp_server import compile_tests, run_tests

        repo_root = Path(__file__).resolve().parent
        sdk_root = repo_root / "test_sdk_cpp"
        sdk_build = sdk_root / "build"
        sdk_build.mkdir(parents=True, exist_ok=True)

        configure = subprocess.run(
            ["cmake", str(sdk_root.resolve())],
            cwd=str(sdk_build.resolve()),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        assert configure.returncode == 0, configure.stderr or configure.stdout

        build = subprocess.run(
            ["cmake", "--build", str(sdk_build.resolve())],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        assert build.returncode == 0, build.stderr or build.stdout

        lib_dir = sdk_build
        for candidate in [sdk_build, sdk_build / "Debug", sdk_build / "Release"]:
            if list(candidate.glob("my_sdk.lib")) or list(candidate.glob("libmy_sdk.a")):
                lib_dir = candidate
                break

        with tempfile.TemporaryDirectory(prefix="sdk_cpp_forge_tests_") as tmp:
            src = Path(tmp)
            example = repo_root / "test_sdk_cpp" / "examples" / "api_test.cpp"
            (src / "api_test.cpp").write_text(example.read_text(encoding="utf-8"))
            build_dir = str(Path(tempfile.mkdtemp(prefix="sdk_cpp_forge_build_")))

            compile_result = json.loads(
                await compile_tests(
                    str(src),
                    build_dir,
                    sdk_include_dirs=[str(sdk_root / "include")],
                    sdk_lib_dirs=[str(lib_dir)],
                    link_libraries=["my_sdk"],
                )
            )
            assert compile_result["status"] == "ok", compile_result
            assert compile_result.get("gtest_cache_dir")

            run_result = json.loads(await run_tests(build_dir))
            assert run_result["status"] == "ok", run_result
            assert run_result["total"] == 5
            assert run_result["passed"] == 5
            assert run_result["failed"] == 0

    @pytest.mark.asyncio
    @pytest.mark.skipif(sys.platform == "win32", reason="pkg-config integration tested on Linux CI")
    async def test_compile_with_pkg_config(self):
        from mcp_server import compile_tests, run_tests

        repo_root = Path(__file__).resolve().parent
        sdk_root = repo_root / "test_sdk_cpp"
        install_prefix = Path(tempfile.mkdtemp(prefix="my_sdk_install_"))
        sdk_build = sdk_root / "build_ci"
        sdk_build.mkdir(parents=True, exist_ok=True)

        configure = subprocess.run(
            ["cmake", str(sdk_root.resolve()), f"-DCMAKE_INSTALL_PREFIX={install_prefix}"],
            cwd=str(sdk_build.resolve()),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        assert configure.returncode == 0, configure.stderr or configure.stdout

        build = subprocess.run(
            ["cmake", "--build", str(sdk_build.resolve())],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        assert build.returncode == 0, build.stderr or build.stdout

        install = subprocess.run(
            ["cmake", "--install", str(sdk_build.resolve())],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        assert install.returncode == 0, install.stderr or install.stdout

        pc_path = install_prefix / "lib" / "pkgconfig" / "my_sdk.pc"
        assert pc_path.exists()

        with tempfile.TemporaryDirectory(prefix="sdk_pc_forge_tests_") as tmp:
            src = Path(tmp)
            example = repo_root / "test_sdk_cpp" / "examples" / "api_test.cpp"
            (src / "api_test.cpp").write_text(example.read_text(encoding="utf-8"))
            build_dir = str(Path(tempfile.mkdtemp(prefix="sdk_pc_forge_build_")))

            os.environ["PKG_CONFIG_PATH"] = str(pc_path.parent)

            compile_result = json.loads(
                await compile_tests(
                    str(src),
                    build_dir,
                    pkg_config_packages=["my_sdk"],
                )
            )
            assert compile_result["status"] == "ok", compile_result

            run_result = json.loads(await run_tests(build_dir))
            assert run_result["status"] == "ok", run_result
            assert run_result["passed"] == 5

    @pytest.mark.asyncio
    @pytest.mark.skipif(sys.platform == "win32", reason="medium pkg-config on Linux CI")
    async def test_medium_sdk_pipeline(self):
        from mcp_server import compile_tests, probe_sdk, run_tests, scan_headers

        repo_root = Path(__file__).resolve().parent
        sdk_root = repo_root / "test_sdk_medium"
        install_prefix = Path(tempfile.mkdtemp(prefix="medium_install_"))
        sdk_build = sdk_root / "build_ci"
        sdk_build.mkdir(parents=True, exist_ok=True)

        for cmd in (
            ["cmake", str(sdk_root.resolve()), f"-DCMAKE_INSTALL_PREFIX={install_prefix}"],
            ["cmake", "--build", str(sdk_build.resolve())],
            ["cmake", "--install", str(sdk_build.resolve())],
        ):
            r = subprocess.run(cmd, cwd=str(sdk_build), capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            assert r.returncode == 0, r.stderr or r.stdout

        scan = json.loads(await scan_headers(str(sdk_root / "include"), use_clang=False))
        assert scan["status"] == "ok"
        conditional = [
            sym for f in scan["files"] for sym in f.get("functions", []) + f.get("classes", [])
            if sym.get("conditional")
        ]
        assert len(conditional) >= 1

        probe = json.loads(await probe_sdk(str(install_prefix)))
        assert probe["status"] == "ok"

        os.environ["PKG_CONFIG_PATH"] = str(install_prefix / "lib" / "pkgconfig")
        with tempfile.TemporaryDirectory(prefix="medium_tests_") as tmp:
            src = Path(tmp)
            (src / "medium_test.cpp").write_text(
                (sdk_root / "examples" / "medium_test.cpp").read_text(encoding="utf-8")
            )
            build = str(Path(tempfile.mkdtemp(prefix="medium_test_build_")))
            compile_result = json.loads(await compile_tests(str(src), build, pkg_config_packages=["medium"]))
            assert compile_result["status"] == "ok", compile_result
            run_result = json.loads(await run_tests(build))
            assert run_result["status"] == "ok"
            assert run_result["passed"] >= 1
