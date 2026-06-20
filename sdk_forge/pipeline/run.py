"""Test execution."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from sdk_forge.pipeline.build import find_test_binary
from sdk_forge.domain.util import run_subprocess


def run_tests_impl(build_dir: str, test_filter: str = "") -> dict:
    build_path = Path(build_dir)
    binary = find_test_binary(build_path)

    if binary is None or not binary.exists():
        return {"error": f"Test binary not found in {build_dir}. Run compile_tests first.", "status": "error"}

    cmd = [str(binary)]
    if test_filter:
        cmd.extend(["--gtest_filter", test_filter])

    try:
        result = run_subprocess(cmd)
    except subprocess.TimeoutExpired:
        return {"error": "Test execution timed out (600s).", "status": "error"}

    full_output = (result.stdout or "") + "\n" + (result.stderr or "")
    passed = failed = skipped = total = 0
    failed_tests: list[str] = []
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("[  PASSED  ]"):
            m = re.search(r"(\d+)\s+test", line)
            if m:
                passed = int(m.group(1))
        elif line.startswith("[  FAILED  ]"):
            m = re.search(r"(\d+)\s+test", line)
            if m:
                failed = int(m.group(1))
            elif " test," in line or line.endswith(" test."):
                failed_tests.append(line)
        elif line.startswith("[  SKIPPED ]"):
            m = re.search(r"(\d+)\s+test", line)
            if m:
                skipped = int(m.group(1))
    m_total = re.search(r"\[==========\] Running (\d+) tests", result.stdout or "")
    total = int(m_total.group(1)) if m_total else passed + failed + skipped

    return {
        "status": "ok" if result.returncode == 0 else "test_failures",
        "return_code": result.returncode,
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "failed_tests": failed_tests,
        "output": full_output,
    }
