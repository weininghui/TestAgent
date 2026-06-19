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

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = REPO_ROOT / "examples"

# Ensure the project root is in sys.path for importing mcp_server
sys.path.insert(0, str(REPO_ROOT))

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

    def test_gtest_cache_block(self, monkeypatch):
        from sdk_forge.gtest import gtest_source_path

        monkeypatch.setattr(
            "sdk_forge.build.gtest_source_path",
            lambda tag: Path("/nonexistent/forge/gtest"),
        )
        content = _generate_cmake_content(
            project_name="demo_tests",
            test_file_names=["demo_test.cpp"],
            gtest_source="cached",
            gtest_version="1.14.0",
        )
        cache = str(_gtest_cache_dir()).replace("\\", "/")
        assert "FETCHCONTENT_BASE_DIR" in content
        assert cache in content
        assert "GIT_TAG v1.14.0" in content
        assert "FETCHCONTENT_UPDATES_DISCONNECTED TRUE" in content

    def test_gtest_local_subdirectory(self, tmp_path, monkeypatch):
        from sdk_forge.gtest import gtest_source_path

        local = tmp_path / "gtest-src"
        local.mkdir()
        (local / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.14)\n", encoding="utf-8")
        monkeypatch.setattr("sdk_forge.build.gtest_source_path", lambda tag: local)
        content = _generate_cmake_content(
            project_name="demo_tests",
            test_file_names=["demo_test.cpp"],
            gtest_source="auto",
            gtest_version="1.14.0",
        )
        assert "add_subdirectory" in content
        assert "FetchContent" not in content

    def test_gtest_fetch_block(self, monkeypatch):
        monkeypatch.setattr(
            "sdk_forge.build.gtest_source_path",
            lambda tag: Path("/nonexistent/forge/gtest"),
        )
        content = _generate_cmake_content(
            project_name="demo_tests",
            test_file_names=["demo_test.cpp"],
            gtest_source="fetch",
            gtest_version="1.13.0",
        )
        assert "FETCHCONTENT_UPDATES_DISCONNECTED FALSE" in content
        assert "GIT_TAG v1.13.0" in content

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

    def test_cli_doctor_init_build_args(self):
        from sdk_forge.cli import build_parser
        parser = build_parser()
        assert parser.parse_args(["doctor"]).command == "doctor"
        init_args = parser.parse_args(["init", "./proj", "--sdk-root", "../sdk", "--name", "calc"])
        assert init_args.command == "init"
        assert init_args.sdk_root == "../sdk"
        build_args = parser.parse_args(["build", "--project-dir", ".", "--no-run", "--retry", "3"])
        assert build_args.no_run is True
        assert build_args.retry == 3
        assert parser.parse_args(["plan", "./sdk"]).command == "plan"
        assert parser.parse_args(["report", "--project-dir", "."]).command == "report"


class TestGtestVersion:
    def test_resolve_pin_version(self):
        from sdk_forge.gtest import resolve_gtest_tag

        assert resolve_gtest_tag("1.13.0") == "v1.13.0"
        assert resolve_gtest_tag("v1.12.0") == "v1.12.0"

    def test_resolve_auto_gcc(self, monkeypatch):
        from sdk_forge import gtest as gtest_mod

        monkeypatch.setattr(gtest_mod, "detect_compiler", lambda: {"kind": "gcc", "major": 11})
        monkeypatch.setattr(gtest_mod, "detect_cmake_major", lambda: 3)
        assert gtest_mod.resolve_gtest_tag("auto") == "v1.13.0"

    def test_resolve_auto_modern_clang(self, monkeypatch):
        from sdk_forge import gtest as gtest_mod

        monkeypatch.setattr(gtest_mod, "detect_compiler", lambda: {"kind": "clang", "major": 16})
        monkeypatch.setattr(gtest_mod, "detect_cmake_major", lambda: 3)
        assert gtest_mod.resolve_gtest_tag("auto") == "v1.14.0"

    def test_doctor_includes_googletest(self):
        from sdk_forge.doctor import doctor_impl

        result = doctor_impl()
        names = {c["name"] for c in result["checks"]}
        assert "googletest" in names


class TestForgeConfig:
    def test_load_forge_json(self, tmp_path):
        from sdk_forge.config import (
            compile_params_from_config,
            find_forge_config,
            load_forge_config,
            merge_compile_params,
            resolve_path,
        )

        config_file = tmp_path / ".forge.json"
        config_file.write_text(
            json.dumps({
                "sdk_root": "../sdk",
                "tests_dir": "tests",
                "build_dir": "build",
                "sdk_include_dirs": ["include"],
                "link_libraries": ["calc"],
            }),
            encoding="utf-8",
        )
        found = find_forge_config(tmp_path / "tests")
        assert found == config_file

        config = load_forge_config(start=tmp_path)
        assert config["_config_path"] == str(config_file.resolve())
        assert resolve_path(config, "tests_dir") == str((tmp_path / "tests").resolve())

        params = compile_params_from_config(config)
        assert params["link_libraries"] == ["calc"]
        merged = merge_compile_params(params, {"link_libraries": "extra"})
        assert "calc" in merged["link_libraries"]
        assert "extra" in merged["link_libraries"]


class TestForgeDoctor:
    def test_doctor_returns_checks(self):
        from sdk_forge.doctor import doctor_impl

        result = doctor_impl()
        assert "checks" in result
        assert "status" in result
        names = {c["name"] for c in result["checks"]}
        assert "cmake" in names
        assert "python" in names
        assert "cxx_compiler" in names


class TestToolchain:
    def test_check_cxx_toolchain_shape(self):
        from sdk_forge.toolchain import check_cxx_toolchain

        tc = check_cxx_toolchain()
        assert "available" in tc
        assert "hints" in tc
        assert "kind" in tc

    def test_compiler_gate_blocks_build(self, tmp_path, monkeypatch):
        def _blocked():
            return {
                "status": "compiler_not_found",
                "error": "No compiler",
                "hints": ["install MSVC"],
                "compile": {"status": "compiler_not_found", "stage": "toolchain", "hints": []},
            }

        monkeypatch.setattr("sdk_forge.retry.compiler_gate_result", _blocked)
        from sdk_forge.retry import build_with_retry_impl

        tests = tmp_path / "tests"
        build = tmp_path / "build"
        tests.mkdir()
        build.mkdir()
        (tests / "t_test.cpp").write_text("#include <gtest/gtest.h>\nTEST(T,T){}\n")
        result = build_with_retry_impl(project_dir=str(tmp_path), run_after_compile=False)
        assert result["status"] == "compiler_not_found"

    def test_report_compiler_not_found_summary(self):
        from sdk_forge.report import build_auto_summary

        text = build_auto_summary({
            "status": "compiler_not_found",
            "toolchain": {"hint": "Install Build Tools"},
        })
        assert "未检测到" in text or "compiler" in text.lower()
        assert "PASS" not in text or "推断" in text

    def test_setup_requires_confirm(self):
        from sdk_forge.toolchain_install import setup_toolchain_impl

        result = setup_toolchain_impl(method="auto", confirm=False)
        assert result["status"] == "confirmation_required"
        assert "available_options" in result

    def test_setup_skips_when_compiler_ready(self, monkeypatch):
        from sdk_forge.toolchain_install import setup_toolchain_impl

        monkeypatch.setattr(
            "sdk_forge.toolchain_install.check_cxx_toolchain",
            lambda: {"available": True, "kind": "msvc"},
        )
        result = setup_toolchain_impl(confirm=True)
        assert result["status"] == "ok"
        assert result.get("skipped") is True

    def test_detect_installers_windows(self, monkeypatch):
        from sdk_forge.toolchain_install import detect_installers

        if sys.platform != "win32":
            pytest.skip("Windows only")
        monkeypatch.setattr("sdk_forge.toolchain_install._which", lambda n: "/usr/bin/winget" if n == "winget" else None)
        detected = detect_installers()
        assert detected.get("auto_method") == "winget-msvc"
        assert len(detected.get("options") or []) >= 1

    def test_ensure_skips_when_ready(self, monkeypatch):
        from sdk_forge.toolchain_install import ensure_toolchain_impl

        monkeypatch.setattr(
            "sdk_forge.toolchain_install.check_cxx_toolchain",
            lambda: {"available": True, "kind": "msvc"},
        )
        result = ensure_toolchain_impl()
        assert result["status"] == "ok"
        assert result["action"] == "none"


class TestForgeInit:
    def test_init_scaffold(self, tmp_path):
        from sdk_forge.init import init_project_impl

        target = tmp_path / "my_forge_proj"
        result = init_project_impl(str(target), sdk_root="../test_sdk", project_name="calc")
        assert result["status"] == "ok"
        assert (target / "tests" / "calc_test.cpp").exists()
        assert (target / ".forge.yaml").exists()
        assert (target / "build").is_dir()


class TestForgePipeline:
    def test_build_no_config_dirs(self, tmp_path):
        from sdk_forge.pipeline import build_pipeline_impl

        tests = tmp_path / "tests"
        build = tmp_path / "build"
        tests.mkdir()
        build.mkdir()
        (tests / "noop_test.cpp").write_text(
            "#include <gtest/gtest.h>\nTEST(Noop, Ok) { EXPECT_TRUE(true); }\n",
            encoding="utf-8",
        )
        result = build_pipeline_impl(
            project_dir=str(tmp_path),
            run_after_compile=False,
        )
        assert result["source_dir"] == str(tests.resolve())
        assert result["build_dir"] == str(build.resolve())
        assert "compile" in result


class TestHintActions:
    def test_undefined_reference_actions(self):
        from sdk_forge.hint_actions import parse_cmake_error_with_actions

        parsed = parse_cmake_error_with_actions(
            "undefined reference to `calc_add'",
            probe={"status": "ok", "link_libraries": ["calc"]},
        )
        assert parsed["hints"]
        types = {a["type"] for a in parsed["actions"]}
        assert "merge_link_libraries" in types
        assert any("calc" in a.get("values", []) for a in parsed["actions"])

    def test_missing_header_actions(self):
        from sdk_forge.hint_actions import parse_cmake_error_with_actions

        parsed = parse_cmake_error_with_actions(
            "fatal error: api.h: No such file or directory",
            probe={"status": "ok", "sdk_include_dirs": ["/sdk/include"]},
        )
        assert any(a["type"] == "merge_sdk_include_dirs" for a in parsed["actions"])

    def test_apply_actions_to_params(self):
        from sdk_forge.config import apply_actions_to_params

        params = {"link_libraries": ["a"], "sdk_include_dirs": []}
        updated = apply_actions_to_params(params, [
            {"type": "merge_link_libraries", "values": ["calc"]},
            {"type": "merge_sdk_include_dirs", "values": ["/inc"]},
        ])
        assert "calc" in updated["link_libraries"]
        assert "/inc" in updated["sdk_include_dirs"]


class TestSuggestPlan:
    def test_plan_from_scan_json(self):
        from sdk_forge.plan import suggest_test_plan_impl

        scan = {
            "status": "ok",
            "sdk_root": "/sdk",
            "files": [{
                "file": "calc.h",
                "functions": [{
                    "name": "calc_add",
                    "return_type": "int",
                    "params": "int a, int b",
                    "kind": "function",
                    "conditional": False,
                }],
                "classes": [],
            }],
        }
        plan = suggest_test_plan_impl(scan_json=scan)
        assert plan["status"] == "ok"
        assert plan["target_count"] == 1
        target = plan["targets"][0]
        assert target["symbol"] == "calc_add"
        assert len(target["scenarios"]) >= 2

    def test_plan_marks_virtual_class(self):
        from sdk_forge.plan import suggest_test_plan_impl

        scan = {
            "status": "ok",
            "files": [{
                "file": "api.hpp",
                "functions": [{
                    "name": "run",
                    "kind": "method",
                    "virtual": True,
                    "return_type": "void",
                    "params": "",
                }],
                "classes": [{"name": "Worker", "kind": "class"}],
            }],
        }
        plan = suggest_test_plan_impl(scan_json=scan)
        worker = next(t for t in plan["targets"] if t["symbol"] == "Worker")
        assert worker["needs_mock"] is True


class TestBuildRetry:
    def test_retry_applies_actions(self, tmp_path, monkeypatch):
        from sdk_forge import retry as retry_mod

        calls = {"n": 0}

        def fake_compile(source_dir, build_dir, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return {
                    "status": "cmake_error",
                    "stage": "build",
                    "output": "undefined reference to `calc_add'",
                    "hints": ["link"],
                    "actions": [{"type": "merge_link_libraries", "values": ["calc"]}],
                }
            return {"status": "ok", "binary_path": str(tmp_path / "run_tests")}

        monkeypatch.setattr(retry_mod, "compile_tests_impl", fake_compile)
        monkeypatch.setattr(retry_mod, "run_tests_impl", lambda b: {"status": "ok", "total": 1, "passed": 1, "failed": 0})

        tests = tmp_path / "tests"
        build = tmp_path / "build"
        tests.mkdir()
        build.mkdir()
        (tests / "t_test.cpp").write_text("#include <gtest/gtest.h>\nTEST(T,T){}\n")

        result = retry_mod.build_with_retry_impl(
            project_dir=str(tmp_path),
            max_retries=3,
            run_after_compile=True,
        )
        assert result["status"] == "ok"
        assert result["auto_fixed"] is True
        assert len(result["attempts"]) == 2
        assert calls["n"] == 2


class TestReport:
    def test_report_markdown(self):
        from sdk_forge.report import report_impl

        state = {
            "status": "ok",
            "passed": 5,
            "failed": 0,
            "auto_fixed": True,
            "attempts": [{"attempt": 1, "result": "cmake_error", "actions_applied": []}],
            "run": {"total": 5, "passed": 5, "failed": 0},
            "compile": {"gtest_tag": "v1.14.0"},
        }
        result = report_impl(build_state_json=json.dumps(state))
        assert result["status"] == "ok"
        assert "SDK Test Forge Report" in result["markdown"]
        assert "v1.14.0" in result["markdown"]

    def test_report_html(self, tmp_path):
        from sdk_forge.report import report_impl

        cache = tmp_path / ".forge" / "cache"
        cache.mkdir(parents=True)
        state = {
            "status": "test_failures",
            "passed": 4,
            "failed": 1,
            "run": {
                "total": 5,
                "passed": 4,
                "failed": 1,
                "status": "test_failures",
                "output": "[  FAILED  ] CalcAdd.Normal\n",
            },
            "compile": {"gtest_tag": "v1.14.0"},
        }
        (cache / "last_build.json").write_text("{}", encoding="utf-8")
        result = report_impl(
            project_dir=str(tmp_path),
            build_state_json=json.dumps(state),
            output_format="html",
            agent_summary="## Conclusion\nAll good except one test.",
        )
        assert result["status"] == "ok"
        assert result["format"] == "html"
        assert Path(result["html_path"]).is_file()
        html = result["html"]
        assert "SDK Test Forge Report" in html
        assert "测试摘要" in html
        assert "Conclusion" in html
        assert "<script>" not in html
        assert "&lt;script&gt;" not in html or "Conclusion" in html


class TestHtmlReport:
    def test_xss_escaped(self):
        from sdk_forge.report_html import format_report_html

        html_out = format_report_html(
            {"status": "ok", "run": {"total": 1, "passed": 1, "failed": 0}},
            agent_summary="<script>alert(1)</script>",
        )
        assert "<script>alert" not in html_out
        assert "&lt;script&gt;" in html_out

    def test_agent_summary_hidden_when_empty(self):
        from sdk_forge.report_html import format_report_html

        html_out = format_report_html({"status": "ok"}, agent_summary="")
        assert "测试摘要" not in html_out


class TestAutoReport:
    def test_build_auto_summary_failures(self):
        from sdk_forge.report import build_auto_summary

        state = {
            "status": "test_failures",
            "passed": 2,
            "failed": 1,
            "run": {
                "status": "test_failures",
                "total": 3,
                "passed": 2,
                "failed": 1,
                "output": (
                    "[ RUN      ] Calc.Add\n"
                    "calc_test.cpp:10: Failure\n"
                    "Expected: 1\n"
                    "Actual: 2\n"
                    "[  FAILED  ] Calc.Add\n"
                ),
            },
        }
        text = build_auto_summary(state)
        assert "失败" in text
        assert "Calc.Add" in text

    def test_auto_generate_report_writes_html(self, tmp_path):
        from sdk_forge.report import auto_generate_report

        state = {"status": "ok", "run": {"total": 1, "passed": 1, "failed": 0, "status": "ok"}}
        result = auto_generate_report(str(tmp_path), state)
        assert result["status"] == "ok"
        assert Path(result["html_path"]).is_file()
        assert "测试摘要" in result["html"]

    def test_pipeline_attaches_html_path(self, tmp_path, monkeypatch):
        from sdk_forge import pipeline

        tests = tmp_path / "tests"
        tests.mkdir()

        def fake_build(**_kwargs):
            return {
                "status": "ok",
                "source_dir": str(tests.resolve()),
                "build_dir": str((tmp_path / "build").resolve()),
                "run": {"total": 1, "passed": 1, "failed": 0, "status": "ok"},
            }

        monkeypatch.setattr(pipeline, "build_with_retry_impl", fake_build)
        result = pipeline.build_pipeline_impl(project_dir=str(tmp_path))
        assert result.get("html_path")
        assert result["report"]["format"] == "html"


class TestCodegen:
    def test_parse_params(self):
        from sdk_forge.codegen import parse_params

        params = parse_params("int a, const char* name")
        assert len(params) == 2
        assert params[0].type_name == "int"
        assert params[1].is_pointer

    def test_render_add_normal(self):
        from sdk_forge.codegen import render_assertion

        target = {
            "symbol": "calc_add",
            "return_type": "int",
            "params": "int a, int b",
        }
        body = render_assertion("calc_add", {"name": "normal"}, target, fidelity="smart")
        assert "EXPECT_EQ" in body
        assert "calc_add(2, 3)" in body

    def test_render_unknown_type_agent_marker(self):
        from sdk_forge.codegen import render_assertion

        target = {"symbol": "foo", "return_type": "MyType", "params": "MyType x"}
        body = render_assertion("foo", {"name": "normal"}, target, fidelity="smart")
        assert "AGENT:" in body

    def test_skeleton_fidelity(self):
        from sdk_forge.codegen import render_assertion

        target = {"symbol": "calc_add", "return_type": "int", "params": "int a, int b"}
        body = render_assertion("calc_add", {"name": "normal"}, target, fidelity="skeleton")
        assert "TODO" in body

    def test_smart_scaffold_expect_eq(self, tmp_path):
        from sdk_forge.templates import generate_test_skeleton_impl

        plan = {
            "status": "ok",
            "targets": [{
                "symbol": "calc_add",
                "kind": "function",
                "file": "calc.h",
                "return_type": "int",
                "params": "int a, int b",
                "scenarios": [{"name": "normal"}, {"name": "boundary"}],
            }],
        }
        out = tmp_path / "tests"
        result = generate_test_skeleton_impl(plan_json=plan, output_dir=str(out), fidelity="smart")
        content = (out / "calc_add_test.cpp").read_text(encoding="utf-8")
        assert result["fidelity"] == "smart"
        assert "EXPECT_EQ" in content

    def test_count_placeholders(self):
        from sdk_forge.codegen import count_placeholders

        text = "// TODO: x\nEXPECT_TRUE(true);\n// AGENT: fill"
        counts = count_placeholders(text)
        assert counts["total"] >= 2


class TestEnrich:
    def test_analyze_scaffold_quality(self, tmp_path):
        from sdk_forge.enrich import analyze_scaffold_quality_impl

        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "foo_test.cpp").write_text(
            "TEST(Foo, A) { EXPECT_TRUE(true); // TODO: fix }\n",
            encoding="utf-8",
        )
        result = analyze_scaffold_quality_impl(project_dir=str(tmp_path))
        assert result["status"] == "ok"
        assert result["placeholder_total"] >= 1
        assert Path(result["saved_to"]).is_file()

    def test_enrich_briefs(self, tmp_path):
        from sdk_forge.enrich import enrich_test_cases_impl

        cache = tmp_path / ".forge" / "cache"
        cache.mkdir(parents=True)
        plan = {"status": "ok", "sdk_root": "", "targets": [{
            "symbol": "calc_add", "file": "calc.h", "scenarios": [{"name": "normal"}],
        }]}
        (cache / "last_plan.json").write_text(json.dumps(plan), encoding="utf-8")
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "calc_add_test.cpp").write_text(
            "TEST(Calc_add, Normal) { // AGENT: fill }\n",
            encoding="utf-8",
        )
        result = enrich_test_cases_impl(project_dir=str(tmp_path))
        assert result["status"] == "ok"
        assert result["brief_count"] >= 1
        assert result["briefs"][0]["markers"]


class TestEnrichBatch:
    def test_enrich_test_files_filter(self, tmp_path):
        from sdk_forge.enrich import enrich_test_cases_impl

        cache = tmp_path / ".forge" / "cache"
        cache.mkdir(parents=True)
        plan = {"status": "ok", "sdk_root": "", "targets": [
            {"symbol": "calc_add", "file": "calc.h", "scenarios": [{"name": "normal"}]},
            {"symbol": "calc_mul", "file": "calc.h", "scenarios": [{"name": "normal"}]},
        ]}
        (cache / "last_plan.json").write_text(json.dumps(plan), encoding="utf-8")
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "calc_add_test.cpp").write_text(
            "TEST(Calc_add, Normal) { // AGENT: fill }\n", encoding="utf-8",
        )
        (tests / "calc_mul_test.cpp").write_text(
            "TEST(Calc_mul, Normal) { // AGENT: fill }\n", encoding="utf-8",
        )
        result = enrich_test_cases_impl(
            project_dir=str(tmp_path),
            test_files="calc_add_test.cpp",
        )
        assert result["status"] == "ok"
        assert result["brief_count"] == 1
        assert "calc_add" in result["briefs"][0]["test_file"].lower()

    def test_quality_test_files_filter(self, tmp_path):
        from sdk_forge.enrich import analyze_scaffold_quality_impl

        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "a_test.cpp").write_text("TEST(A, X) { // TODO: x }\n", encoding="utf-8")
        (tests / "b_test.cpp").write_text("TEST(B, X) { EXPECT_TRUE(true); }\n", encoding="utf-8")
        result = analyze_scaffold_quality_impl(
            project_dir=str(tmp_path),
            test_files="a_test.cpp",
        )
        assert result["status"] == "ok"
        assert result["file_count"] == 1
        assert result["files"][0]["file"] == "a_test.cpp"


class TestOrchestration:
    def test_split_enrich_batches(self):
        from sdk_forge.orchestration import split_enrich_batches

        batches = split_enrich_batches(["a.cpp", "b.cpp", "c.cpp", "d.cpp", "e.cpp"], batch_size=2)
        assert len(batches) == 3
        assert batches[0]["files"] == ["a.cpp", "b.cpp"]
        assert batches[2]["files"] == ["e.cpp"]

    def test_single_file_one_batch(self):
        from sdk_forge.orchestration import split_enrich_batches

        batches = split_enrich_batches(["only_test.cpp"], batch_size=4)
        assert len(batches) == 1
        assert batches[0]["batch_id"] == 0

    def test_next_actions_env_first(self, tmp_path):
        from sdk_forge.orchestration import get_orchestration_context

        ctx = get_orchestration_context(str(tmp_path))
        assert ctx["status"] == "ok"
        assert ctx["next_actions"][0]["agent"] == "forge-env"

    def test_next_actions_enrich_parallel(self, tmp_path):
        from sdk_forge.orchestration import get_orchestration_context
        from sdk_forge.session import save_plan_state
        from sdk_forge.workflow import record_agent_completion

        save_plan_state(str(tmp_path), {
            "status": "ok", "sdk_root": "/sdk", "targets": [{"symbol": "a"}, {"symbol": "b"}],
        })
        tests = tmp_path / "tests"
        tests.mkdir()
        for name in ("a_test.cpp", "b_test.cpp", "c_test.cpp", "d_test.cpp", "e_test.cpp"):
            (tests / name).write_text(f"TEST(X, Y) {{ // AGENT: fill }}\n", encoding="utf-8")
        (tmp_path / ".forge.yaml").write_text("multi_agent_batch_size: 2\n", encoding="utf-8")
        for agent in ("forge-env", "forge-scan", "forge-scaffold"):
            record_agent_completion(str(tmp_path), agent, status="ok")

        ctx = get_orchestration_context(str(tmp_path))
        enrich_actions = [a for a in ctx["next_actions"] if a["agent"] == "forge-enrich"]
        assert len(enrich_actions) >= 2
        assert all(a["parallel"] for a in enrich_actions)

    def test_serial_enrich_one_batch_at_a_time(self, tmp_path):
        from sdk_forge.orchestration import get_orchestration_context
        from sdk_forge.session import save_plan_state
        from sdk_forge.workflow import record_agent_completion

        save_plan_state(str(tmp_path), {
            "status": "ok", "sdk_root": "/sdk", "targets": [{"symbol": "a"}, {"symbol": "b"}],
        })
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "a_test.cpp").write_text("// AGENT: x\n", encoding="utf-8")
        (tests / "b_test.cpp").write_text("// AGENT: y\n", encoding="utf-8")
        (tmp_path / ".forge.yaml").write_text("multi_agent_batch_size: 1\n", encoding="utf-8")
        for agent in ("forge-env", "forge-scan", "forge-scaffold"):
            record_agent_completion(str(tmp_path), agent, status="ok")

        ctx = get_orchestration_context(str(tmp_path))
        enrich_actions = [a for a in ctx["next_actions"] if a["agent"] == "forge-enrich"]
        assert len(enrich_actions) == 1
        assert enrich_actions[0]["parallel"] is False

    def test_record_agent_completion(self, tmp_path):
        from sdk_forge.workflow import load_workflow_state, record_agent_completion

        record_agent_completion(str(tmp_path), "forge-enrich", batch_id=0, status="ok")
        state = load_workflow_state(str(tmp_path))
        assert len(state["agent_runs"]) == 1
        assert state["agent_runs"][0]["agent"] == "forge-enrich"


class TestAutopilotLoop:
    def test_enrich_round_and_clear_agent_runs(self, tmp_path):
        from sdk_forge.workflow import (
            clear_agent_runs,
            get_enrich_round,
            increment_enrich_round,
            record_agent_completion,
        )

        assert get_enrich_round(str(tmp_path)) == 0
        assert increment_enrich_round(str(tmp_path)) == 1
        assert get_enrich_round(str(tmp_path)) == 1
        record_agent_completion(str(tmp_path), "forge-enrich", batch_id=0, status="ok")
        cleared = clear_agent_runs(str(tmp_path), agent="forge-enrich")
        assert cleared["status"] == "ok"
        assert cleared["remaining_runs"] == 0

    def test_redispatch_after_assertion_fail(self, tmp_path):
        from sdk_forge.orchestration import get_orchestration_context
        from sdk_forge.session import save_plan_state
        from sdk_forge.workflow import get_enrich_round, record_agent_completion

        save_plan_state(str(tmp_path), {
            "status": "ok", "sdk_root": "/sdk", "targets": [{"symbol": "good"}, {"symbol": "weak"}],
        })
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "good_test.cpp").write_text(
            "TEST(Good, Ok) { EXPECT_EQ(2 + 3, 5); }\n",
            encoding="utf-8",
        )
        (tests / "weak_test.cpp").write_text(
            "TEST(Weak, Bad) { SUCCEED(); }\n",
            encoding="utf-8",
        )
        (tmp_path / ".forge.yaml").write_text(
            "multi_agent_batch_size: 1\nmax_enrich_rounds: 3\nforge_profile: production\n",
            encoding="utf-8",
        )
        for agent in ("forge-env", "forge-scan", "forge-scaffold"):
            record_agent_completion(str(tmp_path), agent, status="ok")
        record_agent_completion(str(tmp_path), "forge-enrich", batch_id=0, status="ok")
        record_agent_completion(str(tmp_path), "forge-enrich", batch_id=1, status="ok")

        ctx = get_orchestration_context(str(tmp_path))
        enrich_actions = [a for a in ctx["next_actions"] if a["agent"] == "forge-enrich"]
        assert enrich_actions, ctx
        assert enrich_actions[0]["files"] == ["weak_test.cpp"]
        assert get_enrich_round(str(tmp_path)) == 1
        assert ctx["enrich_round"] == 1
        assert ctx["assertion_gate_preview"].get("passed") is False

    def test_files_needing_assertion_fix(self, tmp_path):
        from sdk_forge.orchestration import files_needing_assertion_fix

        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "weak_test.cpp").write_text("TEST(W, A) { SUCCEED(); }\n", encoding="utf-8")
        files = files_needing_assertion_fix(str(tmp_path))
        assert "weak_test.cpp" in files


class TestOrchestrationV52:
    def _base_project(self, tmp_path):
        from sdk_forge.session import save_plan_state
        from sdk_forge.workflow import record_agent_completion

        save_plan_state(str(tmp_path), {
            "status": "ok", "sdk_root": "/sdk", "targets": [{"symbol": "x"}],
        })
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "x_test.cpp").write_text("TEST(X, Ok) { EXPECT_EQ(1, 1); }\n", encoding="utf-8")
        (tmp_path / ".forge.yaml").write_text(
            "max_agent_retries: 2\nmax_enrich_rounds: 3\n",
            encoding="utf-8",
        )
        for agent in ("forge-env", "forge-scan", "forge-scaffold"):
            record_agent_completion(str(tmp_path), agent, status="ok")
        return tmp_path

    def test_agent_error_retry(self, tmp_path):
        from sdk_forge.orchestration import get_orchestration_context
        from sdk_forge.workflow import record_agent_completion

        self._base_project(tmp_path)
        record_agent_completion(str(tmp_path), "forge-enrich", batch_id=0, status="error")

        ctx = get_orchestration_context(str(tmp_path))
        enrich = [a for a in ctx["next_actions"] if a["agent"] == "forge-enrich"]
        assert enrich
        assert enrich[0].get("retry") is True

    def test_agent_error_blocked_after_max_retries(self, tmp_path):
        from sdk_forge.orchestration import get_orchestration_context
        from sdk_forge.workflow import record_agent_completion

        self._base_project(tmp_path)
        for _ in range(3):
            record_agent_completion(str(tmp_path), "forge-enrich", batch_id=0, status="error")

        ctx = get_orchestration_context(str(tmp_path))
        blocked = [a for a in ctx["next_actions"] if a.get("blocked")]
        assert blocked

    def test_review_verdict_blocks_build(self, tmp_path):
        from sdk_forge.orchestration import get_orchestration_context
        from sdk_forge.workflow import record_agent_completion, set_review_verdict

        self._base_project(tmp_path)
        record_agent_completion(str(tmp_path), "forge-enrich", batch_id=0, status="ok")
        record_agent_completion(str(tmp_path), "forge-review", status="ok")
        set_review_verdict(str(tmp_path), "block")

        ctx = get_orchestration_context(str(tmp_path))
        assert not any(a["agent"] == "forge-build" for a in ctx["next_actions"])
        assert ctx["review_verdict"] == "block"

    def test_review_pass_allows_build(self, tmp_path):
        from sdk_forge.orchestration import get_orchestration_context
        from sdk_forge.workflow import record_agent_completion

        self._base_project(tmp_path)
        record_agent_completion(str(tmp_path), "forge-enrich", batch_id=0, status="ok")
        record_agent_completion(
            str(tmp_path), "forge-review", status="ok",
            detail={"review_verdict": "pass"},
        )

        ctx = get_orchestration_context(str(tmp_path))
        build = [a for a in ctx["next_actions"] if a["agent"] == "forge-build"]
        assert build

    def test_build_blocked_redispatch_enrich(self, tmp_path):
        from sdk_forge.orchestration import get_orchestration_context
        from sdk_forge.retry import save_build_state
        from sdk_forge.workflow import record_agent_completion

        self._base_project(tmp_path)
        (tmp_path / "tests" / "x_test.cpp").write_text(
            "TEST(X, Bad) { SUCCEED(); }\n", encoding="utf-8",
        )
        record_agent_completion(str(tmp_path), "forge-enrich", batch_id=0, status="ok")
        record_agent_completion(
            str(tmp_path), "forge-review", status="ok",
            detail={"review_verdict": "pass"},
        )
        record_agent_completion(str(tmp_path), "forge-build", status="error")
        save_build_state(str(tmp_path), {"status": "assertion_quality_blocked"})

        ctx = get_orchestration_context(str(tmp_path))
        enrich = [a for a in ctx["next_actions"] if a["agent"] == "forge-enrich"]
        assert enrich
        assert ctx["enrich_round"] >= 1

    def test_merge_ready_when_complete(self, tmp_path):
        from sdk_forge.orchestration import get_orchestration_context
        from sdk_forge.retry import save_build_state
        from sdk_forge.workflow import record_agent_completion

        self._base_project(tmp_path)
        record_agent_completion(str(tmp_path), "forge-enrich", batch_id=0, status="ok")
        record_agent_completion(
            str(tmp_path), "forge-review", status="ok",
            detail={"review_verdict": "pass"},
        )
        record_agent_completion(str(tmp_path), "forge-build", status="ok")
        save_build_state(str(tmp_path), {"status": "ok", "run": {"passed": 1}})

        ctx = get_orchestration_context(str(tmp_path))
        assert ctx["merge_ready"] is True
        assert ctx["next_actions"] == []


class TestForgeOracle:
    def test_draft_golden_from_plan(self, tmp_path):
        from sdk_forge.oracle import draft_golden_from_plan_impl
        from sdk_forge.session import save_plan_state

        save_plan_state(str(tmp_path), {
            "status": "ok",
            "targets": [{
                "symbol": "add",
                "scenarios": [{"name": "Normal", "args": [1, 2]}],
            }],
        })
        dry = draft_golden_from_plan_impl(str(tmp_path), confirm=False)
        assert dry["status"] == "ok"
        assert dry["added_count"] >= 1

        written = draft_golden_from_plan_impl(str(tmp_path), confirm=True)
        assert (tmp_path / ".forge" / "golden.yaml").is_file()
        assert written["added_count"] >= 0


class TestGoldenSnapshot:
    def test_extract_expect_eq_to_golden(self, tmp_path):
        from sdk_forge.golden import load_golden_cases, snapshot_golden_from_plan_impl
        from sdk_forge.session import save_plan_state

        save_plan_state(str(tmp_path), {
            "status": "ok", "targets": [{"symbol": "calc_add"}],
        })
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "calc_add_test.cpp").write_text(
            "TEST(CalcAdd, Normal) { EXPECT_EQ(calc_add(2, 3), 5); }\n",
            encoding="utf-8",
        )
        dry = snapshot_golden_from_plan_impl(str(tmp_path), merge=True, confirm=False)
        assert dry["added_count"] == 1
        assert dry.get("dry_run") is True

        written = snapshot_golden_from_plan_impl(str(tmp_path), merge=True, confirm=True)
        assert written["status"] == "ok"
        assert written["added_count"] == 1
        loaded = load_golden_cases(str(tmp_path), symbol="calc_add")
        cases = loaded.get("cases") or []
        assert any(c.get("expect") == 5 for c in cases)

    def test_snapshot_merge_skips_existing(self, tmp_path):
        from sdk_forge.golden import init_golden_template, snapshot_golden_from_plan_impl

        init_golden_template(str(tmp_path))
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "calc_add_test.cpp").write_text(
            "TEST(CalcAdd, Normal) { EXPECT_EQ(calc_add(2, 3), 5); }\n",
            encoding="utf-8",
        )
        first = snapshot_golden_from_plan_impl(str(tmp_path), merge=True, confirm=True)
        second = snapshot_golden_from_plan_impl(str(tmp_path), merge=True, confirm=True)
        assert first["added_count"] >= 1
        assert second["added_count"] == 0
        assert second["skipped_count"] >= 1


class TestAutopilotEntry:
    def test_autopilot_init_returns_needs_agent(self, tmp_path, monkeypatch):
        from sdk_forge.autopilot import run_autopilot_impl

        sdk = tmp_path / "sdk"
        inc = sdk / "include"
        inc.mkdir(parents=True)
        (inc / "demo.h").write_text(
            "int add(int a, int b);\n",
            encoding="utf-8",
        )
        project = tmp_path / "forge_project"

        monkeypatch.setattr(
            "sdk_forge.autopilot.ensure_toolchain_impl",
            lambda **kw: {"status": "ok", "skipped": True},
        )

        result = run_autopilot_impl(
            sdk_root=str(sdk),
            project_dir=str(project),
            profile="production",
            max_enrich_rounds=3,
        )
        assert result["status"] in ("needs_agent", "ready_for_build")
        assert result["project_dir"] == str(project.resolve())
        assert "next_actions" in result
        assert result["orchestration"]["max_enrich_rounds"] == 3
        assert (project / ".forge.yaml").is_file()

    @pytest.mark.asyncio
    async def test_mcp_run_forge_autopilot(self, tmp_path, monkeypatch):
        from mcp_server import run_forge_autopilot

        sdk = tmp_path / "sdk"
        (sdk / "include").mkdir(parents=True)
        (sdk / "include" / "x.h").write_text("void x();\n", encoding="utf-8")
        project = tmp_path / "proj"

        monkeypatch.setattr(
            "sdk_forge.autopilot.ensure_toolchain_impl",
            lambda **kw: {"status": "ok"},
        )
        result = json.loads(await run_forge_autopilot(str(sdk), str(project), "production", 2))
        assert result["status"] in ("needs_agent", "ready_for_build", "ok", "blocked")
        assert result["enrich_round"] >= 0


class TestAssertionQuality:
    def test_detects_weak_succeed(self, tmp_path):
        from sdk_forge.assertion_quality import analyze_assertion_quality_impl

        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "foo_test.cpp").write_text(
            'TEST(Foo, Weak) { SUCCEED(); }\n',
            encoding="utf-8",
        )
        result = analyze_assertion_quality_impl(project_dir=str(tmp_path))
        assert result["status"] == "ok"
        assert result["weak_test_count"] >= 1
        assert result["score"] < 100

    def test_detects_tautology(self, tmp_path):
        from sdk_forge.assertion_quality import analyze_assertion_quality_impl

        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "bar_test.cpp").write_text(
            "TEST(Bar, Taut) { EXPECT_EQ(1, 1); }\n",
            encoding="utf-8",
        )
        result = analyze_assertion_quality_impl(project_dir=str(tmp_path))
        assert any("tautology" in (t.get("issues") or []) for t in result["weak_tests"])

    def test_real_assertion_scores_high(self, tmp_path):
        from sdk_forge.assertion_quality import analyze_assertion_quality_impl

        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "ok_test.cpp").write_text(
            "TEST(Ok, Good) { EXPECT_EQ(2 + 3, 5); }\n",
            encoding="utf-8",
        )
        result = analyze_assertion_quality_impl(project_dir=str(tmp_path))
        assert result["score"] >= 80


class TestProductionProfile:
    def test_production_profile_presets(self):
        from sdk_forge.profile import resolve_forge_config

        cfg = resolve_forge_config({}, "production")
        assert cfg["forge_profile"] == "production"
        assert cfg["min_assertion_score"] == 80

    def test_assertion_gate_blocks_agent(self, tmp_path):
        from sdk_forge.quality_gate import run_assertion_quality_gate

        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "bad_test.cpp").write_text(
            "TEST(Bad, A) { // AGENT: fill\n SUCCEED(); }\n",
            encoding="utf-8",
        )
        gate = run_assertion_quality_gate(str(tmp_path), {"forge_profile": "production"})
        assert gate["passed"] is False
        assert gate["block_reasons"]

    def test_pipeline_blocks_weak_production(self, tmp_path):
        from sdk_forge.pipeline import build_pipeline_impl

        tests = tmp_path / "tests"
        build = tmp_path / "build"
        tests.mkdir()
        build.mkdir()
        (tests / "weak_test.cpp").write_text(
            "#include <gtest/gtest.h>\nTEST(W, A) { SUCCEED(); }\n",
            encoding="utf-8",
        )
        (tmp_path / ".forge.yaml").write_text("forge_profile: production\n", encoding="utf-8")
        result = build_pipeline_impl(project_dir=str(tmp_path), run_after_compile=False, profile="production")
        assert result["status"] == "assertion_quality_blocked"


class TestGolden:
    def test_load_golden_cases(self, tmp_path):
        from sdk_forge.golden import init_golden_template, load_golden_cases

        init_golden_template(str(tmp_path))
        loaded = load_golden_cases(str(tmp_path), symbol="calc_add")
        assert loaded["status"] == "ok"
        assert len(loaded.get("cases") or []) >= 1

    def test_golden_codegen_body(self):
        from sdk_forge.codegen import _smart_function_body

        target = {
            "return_type": "int",
            "params": "int a, int b",
            "golden_cases": [{"name": "normal", "args": [2, 3], "expect": 5}],
        }
        body = _smart_function_body("add", {"name": "normal"}, target)
        assert "EXPECT_EQ" in body
        assert "5" in body

    def test_golden_enrich_hints(self, tmp_path):
        from sdk_forge.enrich import enrich_test_cases_impl
        from sdk_forge.golden import init_golden_template
        from sdk_forge.session import save_plan_state

        init_golden_template(str(tmp_path))
        cache = tmp_path / ".forge" / "cache"
        cache.mkdir(parents=True, exist_ok=True)
        plan = {"status": "ok", "sdk_root": "", "targets": [{
            "symbol": "calc_add", "file": "calc.h", "scenarios": [{"name": "normal"}],
        }]}
        (cache / "last_plan.json").write_text(json.dumps(plan), encoding="utf-8")
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "calc_add_test.cpp").write_text(
            "TEST(Calc_add, Normal) { // AGENT: fill }\n", encoding="utf-8",
        )
        result = enrich_test_cases_impl(project_dir=str(tmp_path))
        assert result["briefs"][0].get("oracle_hints")


class TestQualityGate:
    def test_gate_settings_defaults(self):
        from sdk_forge.quality_gate import quality_gate_settings

        s = quality_gate_settings({})
        assert s["enabled"] is True
        assert s["mode"] == "warn"
        assert s["max_placeholder_ratio"] == 0.5

    def test_gate_blocks_when_ratio_high(self, tmp_path):
        from sdk_forge.pipeline import build_pipeline_impl

        tests = tmp_path / "tests"
        build = tmp_path / "build"
        tests.mkdir()
        build.mkdir()
        (tests / "bad_test.cpp").write_text(
            "TEST(Bad, A) { EXPECT_TRUE(true); // TODO: x // TODO: y // AGENT: z }\n" * 5,
            encoding="utf-8",
        )
        (tmp_path / ".forge.yaml").write_text(
            "scaffold_quality_gate: true\nmax_placeholder_ratio: 0.01\nquality_gate_mode: block\n",
            encoding="utf-8",
        )
        result = build_pipeline_impl(project_dir=str(tmp_path), run_after_compile=False)
        assert result["status"] == "scaffold_quality_blocked"
        assert result["quality_gate"]["passed"] is False

    def test_skip_quality_gate(self, tmp_path):
        from sdk_forge.pipeline import build_pipeline_impl

        tests = tmp_path / "tests"
        build = tmp_path / "build"
        tests.mkdir()
        build.mkdir()
        (tests / "noop_test.cpp").write_text(
            "#include <gtest/gtest.h>\nTEST(Noop, Ok) { EXPECT_TRUE(true); }\n",
            encoding="utf-8",
        )
        (tmp_path / ".forge.yaml").write_text(
            "scaffold_quality_gate: true\nmax_placeholder_ratio: 0.01\nquality_gate_mode: block\n",
            encoding="utf-8",
        )
        result = build_pipeline_impl(
            project_dir=str(tmp_path),
            run_after_compile=False,
            skip_quality_gate=True,
        )
        assert result["status"] != "scaffold_quality_blocked"
        assert result["quality_gate"]["skipped"] is True


class TestCoverageExpand:
    def test_appends_test_p_block(self, tmp_path):
        from sdk_forge.coverage_expand import coverage_expand_impl

        cache = tmp_path / ".forge" / "cache"
        cache.mkdir(parents=True)
        plan = {
            "status": "ok",
            "sdk_root": "",
            "targets": [{
                "symbol": "calc_add",
                "kind": "function",
                "params": "int a, int b",
                "return_type": "int",
                "scenarios": [{"name": "normal"}],
            }],
        }
        (cache / "last_plan.json").write_text(json.dumps(plan), encoding="utf-8")
        (cache / "plan_gap.json").write_text(json.dumps({
            "status": "ok",
            "missing_targets": [],
            "partial_targets": [{"symbol": "calc_add"}],
            "coverage": {"uncovered_symbols": ["calc_add"], "line_coverage_pct": 10},
        }), encoding="utf-8")
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "calc_add_test.cpp").write_text(
            "TEST(Calc_add, Normal) { EXPECT_EQ(1, 1); }\n",
            encoding="utf-8",
        )
        result = coverage_expand_impl(project_dir=str(tmp_path))
        assert result["status"] == "ok"
        assert result["appended_count"] >= 1
        content = (tests / "calc_add_test.cpp").read_text(encoding="utf-8")
        assert "ForgeExpand" in content or "INSTANTIATE_TEST_SUITE_P" in content


class TestPlanEnum:
    def test_status_enum_members_from_scan(self):
        from sdk_forge.plan import suggest_test_plan_impl
        from sdk_forge.scan import scan_headers_impl

        sdk = EXAMPLES / "test_sdk_cpp"
        scan = scan_headers_impl(str(sdk / "include"), use_clang=False, use_cache=False)
        assert scan["status"] == "ok"
        clamp_fn = next(
            (f for f in scan["files"][0]["functions"] if f.get("name") == "clamp"),
            None,
        )
        assert clamp_fn is not None
        assert clamp_fn.get("is_template") is True
        enum_info = next(e for e in scan["files"][0]["enums"] if e.get("name") == "Status")
        assert len(enum_info.get("members") or []) >= 3
        plan = suggest_test_plan_impl(scan_json=scan)
        status = next(t for t in plan["targets"] if t["symbol"] == "Status")
        assert status["kind"] == "enum"
        assert len(status.get("enum_members") or []) >= 3
        assert status.get("namespace") == "my_sdk" or status.get("parser_function")


class TestScaffoldGroup:
    def test_group_by_header(self, tmp_path):
        from sdk_forge.templates import generate_test_skeleton_impl

        plan = {
            "status": "ok",
            "targets": [
                {
                    "symbol": "calc_add",
                    "kind": "function",
                    "file": "calc.h",
                    "return_type": "int",
                    "params": "int a, int b",
                    "scenarios": [{"name": "normal"}],
                },
                {
                    "symbol": "calc_sub",
                    "kind": "function",
                    "file": "calc.h",
                    "return_type": "int",
                    "params": "int a, int b",
                    "scenarios": [{"name": "normal"}],
                },
            ],
        }
        out = tmp_path / "tests"
        result = generate_test_skeleton_impl(
            plan_json=plan,
            output_dir=str(out),
            overwrite=True,
            group_by_header=True,
        )
        assert result["status"] == "ok"
        assert len(result["files_written"]) == 1
        content = (out / "calc_test.cpp").read_text(encoding="utf-8")
        assert "calc.h" in content
        assert "TEST_F" in content or "TEST(" in content


class TestTemplates:
    def test_scaffold_from_plan(self, tmp_path):
        from sdk_forge.templates import generate_test_skeleton_impl

        plan = {
            "status": "ok",
            "targets": [{
                "symbol": "calc_add",
                "kind": "function",
                "file": "calc.h",
                "return_type": "int",
                "params": "int a, int b",
                "scenarios": [
                    {"name": "normal", "description": "positive integers"},
                    {"name": "boundary", "description": "edge values"},
                ],
                "conditional": False,
                "needs_mock": False,
            }],
        }
        out = tmp_path / "tests"
        result = generate_test_skeleton_impl(plan_json=plan, output_dir=str(out))
        assert result["status"] == "ok"
        assert len(result["files_written"]) == 1
        content = (out / "calc_add_test.cpp").read_text(encoding="utf-8")
        assert "TEST(Calc_add, Normal)" in content or "TEST(CalcAdd, Normal)" in content
        assert "calc.h" in content


class TestLearn:
    def test_learn_and_load(self, tmp_path):
        from sdk_forge.learn import learn_from_build, load_learned_config, merge_learned_into_params

        state = {
            "status": "ok",
            "sdk_root": str(tmp_path / "sdk"),
            "compile": {"status": "ok"},
            "run": {"status": "ok"},
            "link_libraries": ["calc"],
            "sdk_include_dirs": ["/inc"],
            "attempts": [{"attempt": 1, "actions_applied": [{"type": "merge_link_libraries", "values": ["calc"]}]}],
        }
        saved = learn_from_build(state, str(tmp_path))
        assert saved["status"] == "ok"
        loaded = load_learned_config(str(tmp_path / "sdk"), str(tmp_path))
        assert loaded["found"] is True
        merged = merge_learned_into_params({}, str(tmp_path / "sdk"), str(tmp_path))
        assert "calc" in merged.get("link_libraries", [])


class TestTestFix:
    def test_parse_gtest_failure(self):
        from sdk_forge.test_fix import parse_test_failures

        run_result = {
            "status": "test_failures",
            "output": """
[ RUN      ] CalcAdd.Normal
/path/calc_add_test.cpp:8: Failure
Expected: 3
Actual: 0
[  FAILED  ] CalcAdd.Normal
""",
        }
        parsed = parse_test_failures(run_result)
        assert parsed["failure_count"] >= 1
        assert parsed["actions"][0]["type"] == "review_assertion"


class TestSessionContext:
    def test_session_context(self, tmp_path):
        from sdk_forge.session import get_session_context_impl, save_plan_state
        from sdk_forge.retry import save_build_state

        save_plan_state(str(tmp_path), {"status": "ok", "sdk_root": "/sdk", "targets": []})
        save_build_state(str(tmp_path), {"status": "ok", "sdk_root": "/sdk", "passed": 1})
        ctx = get_session_context_impl(str(tmp_path))
        assert ctx["status"] == "ok"
        assert ctx["plan"] is not None
        assert ctx["build_state"] is not None
        assert ctx["orchestration"] is not None
        assert "enrich_batches" in ctx["orchestration"]
        assert "next_actions" in ctx["orchestration"]


class TestPlanGap:
    def test_analyze_gap_missing_target(self, tmp_path):
        from sdk_forge.plan_gap import analyze_plan_gap_impl
        from sdk_forge.session import save_plan_state

        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "calc_add_test.cpp").write_text(
            '#include <gtest/gtest.h>\nTEST(Calc_add, Normal) {}\n',
            encoding="utf-8",
        )
        plan = {
            "status": "ok",
            "targets": [
                {"symbol": "calc_add", "kind": "function", "file": "calc.h", "scenarios": [
                    {"name": "normal"}, {"name": "error"},
                ]},
                {"symbol": "calc_mul", "kind": "function", "file": "calc.h", "scenarios": [
                    {"name": "normal"},
                ]},
            ],
        }
        save_plan_state(str(tmp_path), plan)
        result = analyze_plan_gap_impl(str(tmp_path))
        assert result["status"] == "ok"
        assert any(t["symbol"] == "calc_mul" for t in result["missing_targets"])
        assert any(t["symbol"] == "calc_add" for t in result["partial_targets"])


class TestProposeFix:
    def test_propose_assertion_fix(self, tmp_path):
        from sdk_forge.test_fix import propose_test_fixes_impl

        tests = tmp_path / "tests"
        tests.mkdir()
        test_file = tests / "calc_add_test.cpp"
        test_file.write_text(
            "#include <gtest/gtest.h>\n"
            "TEST(CalcAdd, Normal) {\n"
            "    EXPECT_EQ(calc_add(1, 2), 0);\n"
            "}\n",
            encoding="utf-8",
        )
        analysis = {
            "status": "ok",
            "failures": [{
                "test": "CalcAdd.Normal",
                "file": str(test_file),
                "line": 3,
                "expected": "3",
                "actual": "0",
            }],
        }
        result = propose_test_fixes_impl(
            analysis_json=analysis,
            project_dir=str(tmp_path),
            tests_dir=str(tests),
        )
        assert result["status"] == "ok"
        assert result["proposal_count"] >= 1
        prop = result["proposals"][0]
        assert prop["requires_confirmation"] is True
        assert "3" in prop["suggested"]


class TestCompdb:
    def test_export_and_get(self, tmp_path):
        from sdk_forge.compdb import export_compile_commands_impl, get_compile_commands_impl

        build = tmp_path / "build"
        build.mkdir()
        (build / "compile_commands.json").write_text("[{}]", encoding="utf-8")
        exported = export_compile_commands_impl(str(build), str(tmp_path))
        assert exported["status"] == "ok"
        loaded = get_compile_commands_impl(str(tmp_path))
        assert loaded["status"] == "ok"
        assert loaded["entry_count"] == 1


class TestProbeCmake:
    def test_yaml_cpp_library_name(self):
        from sdk_forge.probe import parse_cmake_link_libraries
        from pathlib import Path

        cmake = Path(r"C:\Users\14513\Downloads\test\CMakeLists.txt")
        if not cmake.is_file():
            pytest.skip("yaml-cpp clone not present")
        libs = parse_cmake_link_libraries(cmake)
        assert "yaml-cpp" in libs

    def test_probe_not_folder_name(self):
        from sdk_forge.probe import probe_sdk_impl
        from pathlib import Path

        root = Path(r"C:\Users\14513\Downloads\test")
        if not root.is_dir():
            pytest.skip("yaml-cpp clone not present")
        result = probe_sdk_impl(str(root))
        assert result["status"] == "ok"
        assert "test" not in result.get("link_libraries", []) or "yaml-cpp" in result["link_libraries"]


class TestPlanFilter:
    def test_filters_macro_symbols(self):
        from sdk_forge.plan import _is_noise_symbol

        assert _is_noise_symbol("YAML_CPP_API", "class") is True
        assert _is_noise_symbol("calc_add", "function") is False

    def test_max_targets_limits(self):
        from sdk_forge.plan import suggest_test_plan_impl

        scan = {
            "status": "ok",
            "files": [{
                "file": "api.h",
                "functions": [
                    {"name": f"fn_{i}", "kind": "function", "params": "int x"}
                    for i in range(10)
                ],
                "classes": [],
            }],
        }
        plan = suggest_test_plan_impl(scan_json=scan, max_targets=3)
        assert plan["target_count"] == 3
        assert plan["total_candidates"] == 10


class TestApplyFix:
    def test_requires_confirm(self, tmp_path):
        from sdk_forge.test_fix import apply_proposed_fixes_impl

        result = apply_proposed_fixes_impl(str(tmp_path), confirm=False)
        assert result["status"] == "error"
        assert "confirm" in result["error"].lower()

    def test_apply_line(self, tmp_path):
        from sdk_forge.test_fix import apply_proposed_fixes_impl, propose_test_fixes_impl

        tests = tmp_path / "tests"
        tests.mkdir()
        test_file = tests / "calc_test.cpp"
        test_file.write_text("TEST(T, C) {\n    EXPECT_EQ(1, 0);\n}\n", encoding="utf-8")

        analysis = {
            "status": "ok",
            "failures": [{"test": "T.C", "file": str(test_file), "line": 2, "expected": "1", "actual": "0"}],
        }
        propose_test_fixes_impl(analysis_json=analysis, project_dir=str(tmp_path), tests_dir=str(tests))
        result = apply_proposed_fixes_impl(str(tmp_path), confirm=True)
        assert result["status"] == "ok"
        assert "EXPECT_EQ(1, 1)" in test_file.read_text(encoding="utf-8")


class TestSanitizerCmake:
    def test_asan_block_linux(self, monkeypatch):
        from sdk_forge.build import sanitizer_cmake_block

        monkeypatch.setattr("sdk_forge.build.sys.platform", "linux")
        block, hints = sanitizer_cmake_block("asan")
        assert "-fsanitize=address" in block
        assert not hints

    def test_msvc_unsupported(self, monkeypatch):
        from sdk_forge.build import sanitizer_cmake_block

        monkeypatch.setattr("sdk_forge.build.sys.platform", "win32")
        block, hints = sanitizer_cmake_block("asan")
        assert block == ""
        assert hints


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
        scan = scan_headers_impl(str(EXAMPLES / "test_sdk_cpp" / "include"), use_clang=False, use_cache=False)
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
    sdk_root = repo_root / "examples" / "test_sdk"
    sdk_build = sdk_root / "build"
    if sdk_build.exists():
        import shutil
        shutil.rmtree(sdk_build, ignore_errors=True)
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


@pytest.mark.skipif(not _cmake_available(), reason="cmake not found")
class TestE2EPipeline:
    def test_scaffold_build_analyze_propose(self):
        from sdk_forge.build import compile_tests_impl
        from sdk_forge.plan import suggest_test_plan_impl
        from sdk_forge.plan_gap import analyze_plan_gap_impl
        from sdk_forge.run import run_tests_impl
        from sdk_forge.session import save_plan_state
        from sdk_forge.templates import generate_test_skeleton_impl
        from sdk_forge.test_fix import analyze_test_failures_impl, propose_test_fixes_impl

        repo_root = Path(__file__).resolve().parent.parent
        include_dir, lib_dir = _build_test_sdk(repo_root)

        with tempfile.TemporaryDirectory(prefix="forge_e2e_") as tmp:
            project = Path(tmp)
            tests = project / "tests"
            build = project / "build"
            tests.mkdir()
            build.mkdir()

            from sdk_forge.scan import scan_headers_impl

            sdk_path = str(repo_root / "examples" / "test_sdk")
            scan = scan_headers_impl(sdk_path, use_clang=False, use_cache=False)
            plan = suggest_test_plan_impl(scan_json=scan)
            assert plan["status"] == "ok"
            assert plan["target_count"] >= 1
            save_plan_state(str(project), plan)

            scaffold = generate_test_skeleton_impl(
                plan_json=plan, output_dir=str(tests), overwrite=True, fidelity="smart",
            )
            assert scaffold["status"] == "ok"

            test_file = tests / "calc_add_test.cpp"
            assert test_file.exists()
            content = test_file.read_text(encoding="utf-8")
            assert "EXPECT_EQ" in content
            content = content.replace("EXPECT_EQ(calc_add(2, 3), 5)", "EXPECT_EQ(calc_add(1, 2), 0)", 1)
            test_file.write_text(content, encoding="utf-8")

            compile_result = compile_tests_impl(
                str(tests),
                str(build),
                sdk_include_dirs=[str(include_dir)],
                sdk_lib_dirs=[str(lib_dir)],
                link_libraries=["calc"],
                use_config=False,
                extra_cmake_snippet="add_definitions(-DFEATURE_ENABLED)",
            )
            assert compile_result["status"] == "ok"

            run_result = run_tests_impl(str(build))
            assert run_result["status"] == "test_failures"

            analysis = analyze_test_failures_impl(run_json=run_result)
            assert analysis["failure_count"] >= 1
            assert analysis["actions"][0]["type"] == "review_assertion"

            proposals = propose_test_fixes_impl(
                analysis_json=analysis,
                project_dir=str(project),
                tests_dir=str(tests),
            )
            assert proposals["proposal_count"] >= 1
            assert proposals["proposals"][0]["requires_confirmation"] is True

            gap = analyze_plan_gap_impl(str(project))
            assert gap["status"] == "ok"

    def test_smart_scaffold_build_passes_without_manual_edit(self):
        from sdk_forge.build import compile_tests_impl
        from sdk_forge.plan import suggest_test_plan_impl
        from sdk_forge.run import run_tests_impl
        from sdk_forge.templates import generate_test_skeleton_impl

        from sdk_forge.scan import scan_headers_impl

        repo_root = Path(__file__).resolve().parent.parent
        sdk_root = repo_root / "examples" / "test_sdk"
        include_dir, lib_dir = _build_test_sdk(repo_root)

        with tempfile.TemporaryDirectory(prefix="forge_e2e_smart_") as tmp:
            project = Path(tmp)
            tests = project / "tests"
            build = project / "build"
            tests.mkdir()
            if build.exists():
                import shutil
                shutil.rmtree(build)
            build.mkdir()

            scan = scan_headers_impl(str(sdk_root), use_clang=False, use_cache=False)
            plan = suggest_test_plan_impl(scan_json=scan)
            assert plan["target_count"] >= 1
            scaffold = generate_test_skeleton_impl(
                plan_json=plan, output_dir=str(tests), overwrite=True, fidelity="smart",
            )
            assert scaffold["status"] == "ok"
            calc_test = tests / "calc_add_test.cpp"
            assert calc_test.exists()
            assert "EXPECT_EQ" in calc_test.read_text(encoding="utf-8")

            compile_result = compile_tests_impl(
                str(tests),
                str(build),
                sdk_include_dirs=[str(include_dir)],
                sdk_lib_dirs=[str(lib_dir)],
                link_libraries=["calc"],
                use_config=False,
                extra_cmake_snippet="add_definitions(-DFEATURE_ENABLED)",
            )
            assert compile_result["status"] == "ok"

            run_result = run_tests_impl(str(build))
            assert run_result["status"] == "ok"
            assert run_result["failed"] == 0

    def test_quality_gate_blocks_when_ratio_high(self, tmp_path):
        from sdk_forge.pipeline import build_pipeline_impl
        from sdk_forge.templates import generate_test_skeleton_impl

        plan = {
            "status": "ok",
            "targets": [{
                "symbol": "x",
                "kind": "function",
                "file": "x.h",
                "return_type": "void",
                "params": "",
                "scenarios": [{"name": "normal"}],
            }],
        }
        tests = tmp_path / "tests"
        tests.mkdir()
        generate_test_skeleton_impl(
            plan_json=plan, output_dir=str(tests), overwrite=True, fidelity="skeleton",
        )
        (tmp_path / ".forge.yaml").write_text(
            "scaffold_quality_gate: true\nmax_placeholder_ratio: 0.01\nquality_gate_mode: block\n",
            encoding="utf-8",
        )
        result = build_pipeline_impl(project_dir=str(tmp_path), run_after_compile=False)
        assert result["status"] == "scaffold_quality_blocked"


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

        include_dir, lib_dir = _build_test_sdk(REPO_ROOT)

        with tempfile.TemporaryDirectory(prefix="sdk_forge_tests_") as tmp:
            src = Path(tmp)
            example = EXAMPLES / "test_sdk" / "examples" / "calc_test.cpp"
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

        sdk_root = EXAMPLES / "test_sdk_cpp"
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
            example = EXAMPLES / "test_sdk_cpp" / "examples" / "api_test.cpp"
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

        sdk_root = EXAMPLES / "test_sdk_cpp"
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
            example = EXAMPLES / "test_sdk_cpp" / "examples" / "api_test.cpp"
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

        sdk_root = EXAMPLES / "test_sdk_medium"
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

    @pytest.mark.asyncio
    @pytest.mark.skipif(sys.platform == "win32", reason="medium scaffold E2E on Linux CI")
    async def test_medium_sdk_scaffold_and_expand(self):
        from mcp_server import coverage_expand, generate_test_skeleton, suggest_test_plan

        sdk_root = EXAMPLES / "test_sdk_medium"
        install_prefix = Path(tempfile.mkdtemp(prefix="medium_scaffold_"))
        sdk_build = sdk_root / "build_scaffold"
        sdk_build.mkdir(parents=True, exist_ok=True)

        for cmd in (
            ["cmake", str(sdk_root.resolve()), f"-DCMAKE_INSTALL_PREFIX={install_prefix}"],
            ["cmake", "--build", str(sdk_build.resolve())],
            ["cmake", "--install", str(sdk_build.resolve())],
        ):
            r = subprocess.run(cmd, cwd=str(sdk_build), capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            assert r.returncode == 0, r.stderr or r.stdout

        with tempfile.TemporaryDirectory(prefix="medium_forge_") as tmp:
            project = Path(tmp)
            (project / "tests").mkdir()
            (project / "build").mkdir()
            plan = json.loads(await suggest_test_plan(str(sdk_root / "include"), max_targets=10))
            assert plan["status"] == "ok"
            cache = project / ".forge" / "cache"
            cache.mkdir(parents=True)
            (cache / "last_plan.json").write_text(json.dumps(plan), encoding="utf-8")

            scaffold = json.loads(await generate_test_skeleton(
                str(project / "tests"),
                plan_json=json.dumps(plan),
                overwrite=True,
                fidelity="smart",
            ))
            assert scaffold["status"] == "ok"
            assert scaffold.get("files_written")

            expand = json.loads(await coverage_expand(str(project)))
            assert expand["status"] == "ok"
