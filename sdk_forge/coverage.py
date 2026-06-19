"""Coverage collection via gcov/lcov."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

from sdk_forge.util import run_subprocess


def collect_coverage_impl(build_dir: str, source_dir: str = "", coverage_tool: str = "gcov") -> dict:
    build_path = Path(build_dir)
    if not build_path.is_dir():
        return {"error": f"Build directory not found: {build_dir}", "status": "error"}

    if sys.platform == "win32":
        return {
            "status": "unsupported",
            "error": "Coverage collection is not supported on MSVC/Windows in v3.0. Use Linux CI or GCC/Clang.",
        }

    tool = (coverage_tool or "gcov").lower()
    src_path = Path(source_dir) if source_dir else None

    gcov_files: list[str] = []
    for gcno in build_path.rglob("*.gcno"):
        cmd = ["gcov", "-o", str(gcno.parent), str(gcno.with_suffix(".cpp"))]
        if src_path and (src_path / gcno.stem).with_suffix(".cpp").exists():
            cmd = ["gcov", "-o", str(gcno.parent), str((src_path / gcno.stem).with_suffix(".cpp"))]
        try:
            run_subprocess(cmd, cwd=str(build_path))
            for gcda in gcno.parent.glob(f"{gcno.stem}.gcov"):
                gcov_files.append(str(gcda))
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    line_pct = 0.0
    files_summary: list[dict] = []
    html_dir = build_path / "coverage_html"

    if shutil.which("lcov"):
        info_file = build_path / "coverage.info"
        try:
            run_subprocess(
                ["lcov", "--capture", "--directory", str(build_path), "--output-file", str(info_file)],
                cwd=str(build_path),
            )
            summary = run_subprocess(["lcov", "--summary", str(info_file)], cwd=str(build_path))
            output = (summary.stdout or "") + (summary.stderr or "")
            m = re.search(r"lines\.*:\s*([\d.]+)%", output)
            if m:
                line_pct = float(m.group(1))
            if shutil.which("genhtml"):
                html_dir.mkdir(parents=True, exist_ok=True)
                run_subprocess(
                    ["genhtml", str(info_file), "--output-directory", str(html_dir)],
                    cwd=str(build_path),
                )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return {"status": "error", "error": str(exc)}

    for gcov in gcov_files[:20]:
        try:
            text = Path(gcov).read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()
            covered = sum(1 for ln in lines if ln.strip().startswith("1:"))
            total = sum(1 for ln in lines if ln.strip() and ln.strip()[0].isdigit())
            if total:
                files_summary.append({
                    "file": Path(gcov).name,
                    "line_coverage_pct": round(100.0 * covered / total, 1),
                })
        except OSError:
            continue

    return {
        "status": "ok",
        "coverage_tool": tool,
        "line_coverage_pct": line_pct,
        "files": files_summary,
        "gcov_files": gcov_files,
        "html_report_dir": str(html_dir) if html_dir.exists() else None,
    }
