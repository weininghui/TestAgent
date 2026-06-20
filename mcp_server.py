#!/usr/bin/env python3
"""MCP server — thin wrapper over sdk_forge core.
MCP 服务入口，封装 sdk_forge 核心能力。
"""

from __future__ import annotations

import json
import logging
from typing import Annotated

from mcp.server.fastmcp import FastMCP

from sdk_forge.build import compile_tests_impl
from sdk_forge.clean import delete_tests_impl
from sdk_forge.coverage import collect_coverage_impl
from sdk_forge.doctor import doctor_impl
from sdk_forge.init import init_project_impl
from sdk_forge.mock import generate_mocks_impl
from sdk_forge.learn import forget_learned_config, load_learned_config
from sdk_forge.pipeline import build_pipeline_impl
from sdk_forge.compdb import export_compile_commands_impl, get_compile_commands_impl
from sdk_forge.plan import suggest_test_plan_impl
from sdk_forge.plan_gap import analyze_plan_gap_impl
from sdk_forge.probe import probe_sdk_impl
from sdk_forge.report import report_impl
from sdk_forge.retry import load_build_state
from sdk_forge.run import run_tests_impl
from sdk_forge.scan import CLANG_AVAILABLE, scan_headers_impl
from sdk_forge.session import get_session_context_impl, save_plan_state
from sdk_forge.enrich import analyze_scaffold_quality_impl, enrich_test_cases_impl, load_scaffold_quality
from sdk_forge.coverage_expand import coverage_expand_impl
from sdk_forge.templates import generate_test_skeleton_impl
from sdk_forge.toolchain_install import setup_toolchain_impl, ensure_toolchain_impl
from sdk_forge.test_fix import analyze_test_failures_impl, apply_proposed_fixes_impl, propose_test_fixes_impl
from sdk_forge.workflow import update_workflow_stage, record_agent_completion

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mcp_server")

mcp = FastMCP(
    "SDK Forge",
    instructions="""SDK Forge — scan, plan, compile, and run GTest suites for C/C++ SDKs.

Tools:
  - forge_doctor        → check cmake, compiler, caches
  - setup_cxx_toolchain → auto-install MSVC/MinGW/g++ (agent_mode default)
  - ensure_forge_environment → doctor + auto-install toolchain if missing
  - init_forge_project  → scaffold tests + .forge.yaml
  - suggest_test_plan   → structured test scenarios from scan
  - generate_test_skeleton → GTest .cpp (smart assertions or skeleton)
  - enrich_test_cases     → Agent briefs for complex case completion
  - analyze_scaffold_quality → placeholder/TODO ratio
  - analyze_assertion_quality → semantic weak/tautology/AGENT gate
  - load_golden_cases / verify_golden_coverage / snapshot_golden_cases / draft_golden_cases → golden oracle
  - run_forge_autopilot   → hands-off init→orchestration next_actions (v5.1)
  - advance_forge_workflow → record sub-agent + return next step (v5.3)
  - register_forge_delegation / poll_forge_delegations / get_delegation_plan → background delegation (v5.5)
  - update_forge_delegation_session / dispatch_forge_delegate → session nav + CLI runtime (v5.6)
  - register_from_omo_task_result → parse OMO task() output + bind sessionId (v5.7)
  - get_task_dispatch_plan / validate_forge_delegation_tool → OMO task() GUI card dispatch (v5.9)
  - record_scan_batch     → store parallel scan batch result (v5.3)
  - coverage_expand       → append TEST_P for low-coverage symbols
  - build_tests         → probe + compile + run with retry/auto-fix
  - analyze_test_failures → parse GTest failure output
  - propose_test_fixes     → suggested assertion edits (confirmation required)
  - apply_test_fixes       → write proposals after confirm=true
  - analyze_plan_gap       → plan vs tests/coverage gap
  - get_compile_commands   → cached compile_commands.json
  - forge_report        → markdown / HTML / JSON report from last build
  - get_build_state     → read last build JSON
  - get_session_context → plan + build + learned config + orchestration
  - get_learned_config  → cached compile params for SDK
  - scan_headers        → parse headers (libclang + regex)
  - probe_sdk           → suggest link settings
  - compile_tests       → CMake build (reads .forge.yaml/.forge.json)
  - run_tests           → execute test binary
  - collect_coverage    → gcov/lcov summary
  - generate_mocks      → GMock templates
  - delete_tests        → remove old test files
  - record_agent_run    → mark sub-agent batch completion for orchestrator
""",
)


@mcp.tool(description="Check cmake, compiler, libclang, forge cache; returns forge_version (authoritative).")
async def forge_doctor() -> str:
    return json.dumps(doctor_impl(), indent=2, ensure_ascii=False)


@mcp.tool(description="Auto-install C++ toolchain via winget/apt/brew. Agent mode skips manual confirm.")
async def setup_cxx_toolchain(
    confirm: Annotated[bool | str, "Explicit user confirm (CLI-style)."] = False,
    agent_mode: Annotated[bool | str, "Agent delegated install (default true for forge agent)."] = True,
    method: Annotated[str, "auto, winget-msvc, winget-mingw, apt-build-essential, brew-llvm, ..."] = "auto",
) -> str:
    return json.dumps(
        setup_toolchain_impl(method=method, confirm=confirm, agent_mode=agent_mode),
        indent=2,
        ensure_ascii=False,
    )


@mcp.tool(description="Ensure cmake + C++ compiler; auto-install toolchain when missing (full Agent env setup).")
async def ensure_forge_environment(
    method: Annotated[str, "Toolchain install method when compiler missing."] = "auto",
    auto_install: Annotated[bool | str, "Run package manager install if needed."] = True,
) -> str:
    from sdk_forge.doctor import doctor_impl

    doctor = doctor_impl()
    ensure = ensure_toolchain_impl(method=method, auto_install=auto_install, agent_mode=True)
    doctor_after = doctor_impl()
    return json.dumps(
        {
            "status": "ok" if ensure.get("status") == "ok" or doctor_after.get("ready") else ensure.get("status", "issues_found"),
            "doctor_before": doctor,
            "toolchain": ensure,
            "doctor_after": doctor_after,
            "ready": doctor_after.get("ready", False),
        },
        indent=2,
        ensure_ascii=False,
    )


@mcp.tool(description="Scaffold a forge test project with tests/ and .forge.yaml.")
async def init_forge_project(
    target_dir: Annotated[str, "Directory to create the project in."],
    sdk_root: Annotated[str, "Optional SDK root for .forge.yaml template."] = "",
    project_name: Annotated[str, "Sample test file base name."] = "sdk_tests",
) -> str:
    return json.dumps(init_project_impl(target_dir, sdk_root, project_name), indent=2, ensure_ascii=False)


@mcp.tool(description="Generate structured test plan with scenarios from scan_headers JSON or SDK root.")
async def suggest_test_plan(
    sdk_root: Annotated[str, "SDK root to scan when scan_json is empty."] = "",
    scan_json: Annotated[str, "JSON from scan_headers."] = "",
    project_dir: Annotated[str, "Save plan to .forge/cache when set."] = "",
    max_targets: Annotated[int | str, "Limit targets for large SDKs (0 = all)."] = 0,
) -> str:
    result = suggest_test_plan_impl(
        sdk_root=sdk_root, scan_json=scan_json or None, max_targets=max_targets,
    )
    if project_dir and result.get("status") == "ok":
        save_plan_state(project_dir, result)
        update_workflow_stage(project_dir, "plan")
        result["plan_saved"] = str((project_dir or ".") + "/.forge/cache/last_plan.json")
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool(description="Generate GTest files with smart assertions (fidelity=smart) or TODO skeleton.")
async def generate_test_skeleton(
    output_dir: Annotated[str, "Directory for generated *_test.cpp files."],
    plan_json: Annotated[str, "JSON from suggest_test_plan."] = "",
    sdk_root: Annotated[str, "Scan SDK and plan when plan_json empty."] = "",
    project_name: Annotated[str, "Base name fallback."] = "sdk_tests",
    overwrite: Annotated[bool | str, "Overwrite existing test files."] = False,
    fidelity: Annotated[str, "smart (default) or skeleton."] = "smart",
    group_by_header: Annotated[bool | str, "Group targets per header into one file with TEST_F."] = False,
    skip_existing: Annotated[bool | str, "Only write missing target files (incremental scaffold)."] = False,
) -> str:
    return json.dumps(
        generate_test_skeleton_impl(
            plan_json or None, output_dir, sdk_root, project_name, overwrite,
            fidelity=fidelity, group_by_header=group_by_header, skip_existing=skip_existing,
        ),
        indent=2, ensure_ascii=False,
    )


@mcp.tool(description="Build Agent enrichment briefs (header excerpts, AGENT markers, scenarios).")
async def enrich_test_cases(
    project_dir: Annotated[str, "Project root with plan and tests/."] = "",
    symbol: Annotated[str, "Optional single symbol filter."] = "",
    tests_dir: Annotated[str, "Override tests directory."] = "",
    test_files: Annotated[str, "Comma-separated test basenames or paths."] = "",
) -> str:
    return json.dumps(
        enrich_test_cases_impl(project_dir, symbol=symbol, tests_dir=tests_dir, test_files=test_files),
        indent=2, ensure_ascii=False,
    )


@mcp.tool(description="Analyze placeholder/TODO ratio in generated test files.")
async def analyze_scaffold_quality(
    project_dir: Annotated[str, "Project root with tests/."] = "",
    tests_dir: Annotated[str, "Override tests directory."] = "",
    test_files: Annotated[str, "Comma-separated test basenames or paths."] = "",
) -> str:
    return json.dumps(
        analyze_scaffold_quality_impl(project_dir, tests_dir=tests_dir, test_files=test_files),
        indent=2, ensure_ascii=False,
    )


@mcp.tool(description="Analyze semantic assertion quality (weak, tautology, AGENT markers).")
async def analyze_assertion_quality(
    project_dir: Annotated[str, "Project root with tests/."] = "",
    tests_dir: Annotated[str, "Override tests directory."] = "",
    test_files: Annotated[str, "Comma-separated test basenames or paths."] = "",
) -> str:
    from sdk_forge.assertion_quality import analyze_assertion_quality_impl
    return json.dumps(
        analyze_assertion_quality_impl(project_dir, tests_dir=tests_dir, test_files=test_files),
        indent=2, ensure_ascii=False,
    )


@mcp.tool(description="Load golden oracle cases from .forge/golden.yaml.")
async def load_golden_cases(
    project_dir: Annotated[str, "Project root."] = "",
    symbol: Annotated[str, "Optional symbol filter."] = "",
) -> str:
    from sdk_forge.golden import load_golden_cases as load_golden_impl
    return json.dumps(load_golden_impl(project_dir, symbol=symbol), indent=2, ensure_ascii=False)


@mcp.tool(description="Verify golden cases are referenced in generated tests.")
async def verify_golden_coverage(
    project_dir: Annotated[str, "Project root with tests/."] = "",
) -> str:
    from sdk_forge.golden import verify_golden_in_tests
    return json.dumps(verify_golden_in_tests(project_dir), indent=2, ensure_ascii=False)


@mcp.tool(description="Snapshot EXPECT_EQ cases from test sources into .forge/golden.yaml (merge by default).")
async def snapshot_golden_cases(
    project_dir: Annotated[str, "Project root with tests/."] = "",
    merge: Annotated[bool | str, "Merge with existing golden.yaml (default true)."] = True,
    confirm: Annotated[bool | str, "Write golden.yaml (default false = dry-run)."] = False,
) -> str:
    from sdk_forge.golden import snapshot_golden_from_plan_impl
    from sdk_forge.util import parse_bool
    return json.dumps(
        snapshot_golden_from_plan_impl(
            project_dir,
            merge=parse_bool(merge, default=True),
            confirm=parse_bool(confirm, default=False),
        ),
        indent=2,
        ensure_ascii=False,
    )


@mcp.tool(description="Draft golden.yaml cases from plan scenarios (forge-oracle heuristic).")
async def draft_golden_cases(
    project_dir: Annotated[str, "Project root with last_plan.json."] = "",
    merge: Annotated[bool | str, "Merge with existing golden.yaml (default true)."] = True,
    confirm: Annotated[bool | str, "Write golden.yaml (default false = dry-run)."] = False,
) -> str:
    from sdk_forge.oracle import draft_golden_from_plan_impl
    from sdk_forge.util import parse_bool
    return json.dumps(
        draft_golden_from_plan_impl(
            project_dir,
            merge=parse_bool(merge, default=True),
            confirm=parse_bool(confirm, default=False),
        ),
        indent=2,
        ensure_ascii=False,
    )


@mcp.tool(description="Hands-off autopilot: init/env/scan/scaffold then return orchestration next_actions.")
async def run_forge_autopilot(
    sdk_root: Annotated[str, "SDK root to scan and test."] = "",
    project_dir: Annotated[str, "Forge project directory (auto-created if empty)."] = "",
    profile: Annotated[str, "Forge profile: production (default) or default."] = "production",
    max_enrich_rounds: Annotated[int | str, "Max assertion-driven enrich rounds (0 = config default)."] = 0,
) -> str:
    from sdk_forge.autopilot import run_autopilot_impl
    rounds: int | str = ""
    if max_enrich_rounds not in (0, "0", "", None):
        rounds = max_enrich_rounds
    return json.dumps(
        run_autopilot_impl(
            sdk_root=sdk_root,
            project_dir=project_dir,
            profile=profile,
            max_enrich_rounds=rounds,
        ),
        indent=2,
        ensure_ascii=False,
    )


@mcp.tool(description="Append TEST_P boundary cases for low-coverage plan targets.")
async def coverage_expand(
    project_dir: Annotated[str, "Project root with plan, gap, and tests/."] = "",
    tests_dir: Annotated[str, "Override tests directory."] = "",
    threshold_pct: Annotated[float | str, "Expand when line coverage below this (default 80)."] = 80.0,
) -> str:
    try:
        threshold = float(threshold_pct)
    except (TypeError, ValueError):
        threshold = 80.0
    return json.dumps(
        coverage_expand_impl(project_dir, tests_dir=tests_dir, threshold_pct=threshold),
        indent=2, ensure_ascii=False,
    )


@mcp.tool(description="Analyze GTest failures; returns structured review_assertion actions.")
async def analyze_test_failures(
    build_dir: Annotated[str, "Build directory to run tests from."] = "",
    run_json: Annotated[str, "Optional run_tests JSON instead of re-running."] = "",
) -> str:
    return json.dumps(
        analyze_test_failures_impl(build_dir, run_json or None),
        indent=2, ensure_ascii=False,
    )


@mcp.tool(description="Propose test assertion fixes from failures; never writes source (requires user confirmation).")
async def propose_test_fixes(
    build_dir: Annotated[str, "Build directory to analyze."] = "",
    analysis_json: Annotated[str, "Optional analyze_test_failures JSON."] = "",
    project_dir: Annotated[str, "Project root for cache and tests/."] = "",
) -> str:
    return json.dumps(
        propose_test_fixes_impl(build_dir, analysis_json or None, project_dir),
        indent=2, ensure_ascii=False,
    )


@mcp.tool(description="Apply cached test fix proposals after explicit confirm=true.")
async def apply_test_fixes(
    project_dir: Annotated[str, "Project root with .forge/cache/last_proposals.json."] = "",
    confirm: Annotated[bool | str, "Must be true to write files."] = False,
    indices: Annotated[str, "Comma-separated proposal indices to apply (default all)."] = "",
) -> str:
    result = apply_proposed_fixes_impl(project_dir, confirm=confirm, indices=indices or None)
    if result.get("status") == "ok" and project_dir:
        update_workflow_stage(project_dir, "apply", {"applied_count": result.get("applied_count")})
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool(description="Compare test plan targets against tests/ files and optional coverage cache.")
async def analyze_plan_gap(
    project_dir: Annotated[str, "Project root with .forge/cache/."] = "",
    plan_json: Annotated[str, "Optional plan JSON instead of cached plan."] = "",
    tests_dir: Annotated[str, "Override tests directory."] = "",
    sdk_root: Annotated[str, "Scan SDK when no cached plan."] = "",
) -> str:
    return json.dumps(
        analyze_plan_gap_impl(project_dir, plan_json or None, tests_dir, sdk_root),
        indent=2, ensure_ascii=False,
    )


@mcp.tool(description="Read cached compile_commands.json from project .forge/cache/.")
async def get_compile_commands(
    project_dir: Annotated[str, "Project root."] = "",
) -> str:
    return json.dumps(get_compile_commands_impl(project_dir), indent=2, ensure_ascii=False)


@mcp.tool(description="Export compile_commands.json from build dir into project cache.")
async def export_compile_commands(
    build_dir: Annotated[str, "CMake build directory."],
    project_dir: Annotated[str, "Project root for cache."] = "",
) -> str:
    return json.dumps(
        export_compile_commands_impl(build_dir, project_dir),
        indent=2, ensure_ascii=False,
    )


@mcp.tool(description="Combined session: last plan, build state, learned config, report summary.")
async def get_session_context(
    project_dir: Annotated[str, "Project root with .forge/cache/."] = "",
) -> str:
    return json.dumps(get_session_context_impl(project_dir), indent=2, ensure_ascii=False)


@mcp.tool(description="Record sub-agent completion for multi-agent orchestration (workflow.json agent_runs).")
async def record_agent_run(
    agent: Annotated[str, "Sub-agent name e.g. forge-enrich."],
    project_dir: Annotated[str, "Project root."] = "",
    status: Annotated[str, "ok or error."] = "ok",
    batch_id: Annotated[int | str, "Enrich batch id when applicable."] = "",
    detail_json: Annotated[str, "Optional JSON detail object."] = "",
    review_verdict: Annotated[str, "forge-review only: pass or block."] = "",
) -> str:
    bid: int | None = None
    if batch_id not in ("", None):
        try:
            bid = int(batch_id)
        except (TypeError, ValueError):
            bid = None
    detail = None
    if detail_json:
        try:
            detail = json.loads(detail_json)
        except json.JSONDecodeError:
            detail = {"raw": detail_json}
    if review_verdict:
        detail = dict(detail or {})
        detail["review_verdict"] = review_verdict.strip().lower()
    result = record_agent_completion(project_dir, agent, status=status, batch_id=bid, detail=detail)
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool(description="Advance workflow after sub-agent completes; records run and returns next step.")
async def advance_forge_workflow(
    project_dir: Annotated[str, "Project root."] = "",
    last_agent: Annotated[str, "Completed sub-agent name (empty to only read next step)."] = "",
    last_status: Annotated[str, "ok or error for last_agent."] = "ok",
    batch_id: Annotated[int | str, "Batch id when applicable."] = "",
    review_verdict: Annotated[str, "forge-review only: pass or block."] = "",
    detail_json: Annotated[str, "Optional JSON detail for last run."] = "",
) -> str:
    from sdk_forge.workflow_advance import advance_forge_workflow_impl

    bid: int | None = None
    if batch_id not in ("", None):
        try:
            bid = int(batch_id)
        except (TypeError, ValueError):
            bid = None
    detail = None
    if detail_json:
        try:
            detail = json.loads(detail_json)
        except json.JSONDecodeError:
            detail = {"raw": detail_json}
    return json.dumps(
        advance_forge_workflow_impl(
            project_dir=project_dir,
            last_agent=last_agent,
            last_status=last_status,
            batch_id=bid,
            review_verdict=review_verdict,
            detail=detail,
        ),
        indent=2,
        ensure_ascii=False,
    )


@mcp.tool(description="Register OMO background task_id after primary dispatches a sub-agent (v5.5+).")
async def register_forge_delegation(
    task_id: Annotated[str, "OMO task() return value."],
    agent: Annotated[str, "Sub-agent name e.g. forge-enrich."],
    project_dir: Annotated[str, "Project root."] = "",
    batch_id: Annotated[int | str, "Batch id when applicable."] = "",
    title: Annotated[str, "Human-readable task title."] = "",
    session_id: Annotated[str, "OpenCode session id when known (enables TUI navigation)."] = "",
) -> str:
    from sdk_forge.delegation import register_delegation_impl

    bid: int | None = None
    if batch_id not in ("", None):
        try:
            bid = int(batch_id)
        except (TypeError, ValueError):
            bid = None
    return json.dumps(
        register_delegation_impl(
            project_dir, task_id, agent,
            batch_id=bid, title=title, session_id=session_id,
        ),
        indent=2,
        ensure_ascii=False,
    )


@mcp.tool(description="Attach OpenCode session_id to a delegation for sub-agent navigation (v5.6).")
async def update_forge_delegation_session(
    task_id: Annotated[str, "Delegation task_id from register_forge_delegation or dispatch_forge_delegate."],
    session_id: Annotated[str, "OpenCode session id e.g. ses_xxx."],
    project_dir: Annotated[str, "Project root."] = "",
) -> str:
    from sdk_forge.delegation import update_delegation_session_impl

    return json.dumps(
        update_delegation_session_impl(project_dir, task_id, session_id),
        indent=2,
        ensure_ascii=False,
    )


@mcp.tool(description="Dispatch sub-agent via CLI `opencode run` when delegation_mode=cli (v5.6).")
async def dispatch_forge_delegate(
    agent: Annotated[str, "Sub-agent name e.g. forge-enrich."],
    prompt: Annotated[str, "Prompt for the sub-agent."],
    project_dir: Annotated[str, "Project root."] = "",
    batch_id: Annotated[int | str, "Batch id when applicable."] = "",
    title: Annotated[str, "Human-readable task title."] = "",
) -> str:
    from sdk_forge.delegate_runner import dispatch_cli_delegate_impl

    bid: int | None = None
    if batch_id not in ("", None):
        try:
            bid = int(batch_id)
        except (TypeError, ValueError):
            bid = None
    return json.dumps(
        dispatch_cli_delegate_impl(project_dir, agent, prompt, batch_id=bid, title=title),
        indent=2,
        ensure_ascii=False,
    )


@mcp.tool(description="Parse OMO task()/call_omo_agent text and register delegation (v5.7).")
async def register_from_omo_task_result(
    omo_result_text: Annotated[str, "Raw text returned by OMO task() or call_omo_agent."],
    agent: Annotated[str, "Sub-agent name e.g. forge-enrich."],
    project_dir: Annotated[str, "Project root."] = "",
    batch_id: Annotated[int | str, "Batch id when applicable."] = "",
    title: Annotated[str, "Human-readable task title."] = "",
) -> str:
    from sdk_forge.delegation import register_from_omo_result_impl

    bid: int | None = None
    if batch_id not in ("", None):
        try:
            bid = int(batch_id)
        except (TypeError, ValueError):
            bid = None
    return json.dumps(
        register_from_omo_result_impl(project_dir, omo_result_text, agent, batch_id=bid, title=title),
        indent=2,
        ensure_ascii=False,
    )


@mcp.tool(description="Poll pending/completed background delegations and stage_timeline (v5.5).")
async def poll_forge_delegations(
    project_dir: Annotated[str, "Project root."] = "",
) -> str:
    from sdk_forge.delegation import poll_forge_delegations_impl

    return json.dumps(poll_forge_delegations_impl(project_dir), indent=2, ensure_ascii=False)


@mcp.tool(description="Auto-bind delegations to OpenCode sessions by title pattern (v5.8).")
async def sync_delegation_sessions(
    project_dir: Annotated[str, "Project root."] = "",
    parent_session_id: Annotated[str, "Optional forge primary session id to filter child sessions."] = "",
) -> str:
    from sdk_forge.session_nav import sync_delegation_sessions_impl

    return json.dumps(
        sync_delegation_sessions_impl(project_dir, parent_session_id=parent_session_id),
        indent=2,
        ensure_ascii=False,
    )


@mcp.tool(description="Live dashboard: sub-agent session ids, previews, and jump hints (v5.8).")
async def get_subagent_dashboard(
    project_dir: Annotated[str, "Project root."] = "",
    parent_session_id: Annotated[str, "Optional forge primary session id."] = "",
    include_preview: Annotated[bool, "Include live_preview from session export."] = True,
) -> str:
    from sdk_forge.session_nav import get_subagent_dashboard_impl

    return json.dumps(
        get_subagent_dashboard_impl(
            project_dir,
            parent_session_id=parent_session_id,
            include_preview=include_preview,
        ),
        indent=2,
        ensure_ascii=False,
    )


@mcp.tool(description="Peek what a sub-agent session is doing right now (v5.8).")
async def peek_subagent_session(
    session_id: Annotated[str, "OpenCode session id e.g. ses_xxx."],
    max_chars: Annotated[int, "Max preview characters."] = 500,
) -> str:
    from sdk_forge.session_nav import export_session_preview_impl

    return json.dumps(
        export_session_preview_impl(session_id, max_chars=max_chars),
        indent=2,
        ensure_ascii=False,
    )


@mcp.tool(description="Build dispatch plan from orchestration next_actions with run_in_background hints (v5.5).")
async def get_delegation_plan(
    project_dir: Annotated[str, "Project root."] = "",
) -> str:
    from sdk_forge.delegation import get_delegation_plan_impl

    return json.dumps(get_delegation_plan_impl(project_dir), indent=2, ensure_ascii=False)


@mcp.tool(description="OMO task() dispatch plan for OpenCode GUI Task cards (v5.9).")
async def get_task_dispatch_plan(
    project_dir: Annotated[str, "Project root."] = "",
) -> str:
    from sdk_forge.task_dispatch import get_task_dispatch_plan_impl

    return json.dumps(get_task_dispatch_plan_impl(project_dir), indent=2, ensure_ascii=False)


@mcp.tool(description="Validate agent tool text — reject call_omo_agent / task(agent=) (v5.9).")
async def validate_forge_delegation_tool(
    text: Annotated[str, "Agent tool call text or transcript snippet to validate."],
) -> str:
    from sdk_forge.task_dispatch import validate_delegation_tool_text_impl

    return json.dumps(validate_delegation_tool_text_impl(text), indent=2, ensure_ascii=False)


@mcp.tool(description="Store parallel scan batch JSON in workflow (forge-scan sub-agent).")
async def record_scan_batch(
    project_dir: Annotated[str, "Project root."] = "",
    batch_id: Annotated[int | str, "Scan batch id."] = 0,
    scan_json: Annotated[str, "scan_headers JSON for this batch."] = "",
) -> str:
    from sdk_forge.workflow import save_scan_batch_result

    try:
        bid = int(batch_id)
    except (TypeError, ValueError):
        return json.dumps({"status": "error", "error": "batch_id required"}, indent=2)
    if not scan_json:
        return json.dumps({"status": "error", "error": "scan_json required"}, indent=2)
    try:
        payload = json.loads(scan_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"status": "error", "error": str(exc)}, indent=2)
    result = save_scan_batch_result(project_dir, bid, payload)
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool(description="Load learned compile params for an SDK from prior successful builds.")
async def get_learned_config(
    sdk_root: Annotated[str, "SDK root path."],
    project_dir: Annotated[str, "Project cache directory."] = "",
) -> str:
    return json.dumps(load_learned_config(sdk_root, project_dir), indent=2, ensure_ascii=False)


@mcp.tool(description="Remove cached learned compile params for an SDK.")
async def forget_learned_config(
    sdk_root: Annotated[str, "SDK root path."],
    project_dir: Annotated[str, "Project cache directory."] = "",
) -> str:
    return json.dumps(forget_learned_config(sdk_root, project_dir), indent=2, ensure_ascii=False)


@mcp.tool(description="Probe + compile + run with retry; auto-generates HTML report at .forge/cache/report.html.")
async def build_tests(
    project_dir: Annotated[str, "Project root containing .forge.yaml or .forge.json."] = "",
    source_dir: Annotated[str, "Override tests directory."] = "",
    build_dir: Annotated[str, "Override build directory."] = "",
    sdk_root: Annotated[str, "Override SDK root for probe."] = "",
    run_after_compile: Annotated[bool | str, "Run tests after compile (default true)."] = True,
    max_retries: Annotated[int | str, "Max compile attempts with hint-based auto-fix (default 3)."] = 3,
    auto_fix_config: Annotated[bool | str, "Write applied fixes back to .forge config."] = False,
    skip_quality_gate: Annotated[bool | str, "Skip scaffold quality gate (default false)."] = False,
    auto_setup_toolchain: Annotated[bool | str, "Auto-install compiler if missing (default true)."] = True,
    profile: Annotated[str, "Forge profile: default or production."] = "",
) -> str:
    return json.dumps(
        build_pipeline_impl(
            project_dir, source_dir, build_dir, sdk_root,
            run_after_compile, max_retries, auto_fix_config, skip_quality_gate,
            auto_setup_toolchain, profile=profile,
        ),
        indent=2, ensure_ascii=False,
    )


@mcp.tool(description="Generate markdown, HTML, or JSON report from last build state.")
async def forge_report(
    project_dir: Annotated[str, "Project directory with .forge/cache/last_build.json."] = "",
    output_format: Annotated[str, "markdown (default), html, or json."] = "markdown",
    agent_summary: Annotated[str, "Optional Agent analysis text for HTML report section."] = "",
    output_path: Annotated[str, "Optional HTML output path (default .forge/cache/report.html)."] = "",
) -> str:
    result = report_impl(
        project_dir,
        output_format=output_format,
        agent_summary=agent_summary,
        output_path=output_path,
    )
    if result.get("status") == "ok" and output_format == "html" and project_dir:
        update_workflow_stage(project_dir, "report")
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool(description="Read last build state JSON from project cache.")
async def get_build_state(
    project_dir: Annotated[str, "Project directory."] = "",
) -> str:
    return json.dumps(load_build_state(project_dir), indent=2, ensure_ascii=False)


@mcp.tool(description="Scan .h/.hpp headers using libclang when available, with regex fallback.")
async def scan_headers(
    sdk_root: Annotated[str, "Absolute path to the SDK root directory."],
    include_dirs: Annotated[list[str] | str, "Optional include dirs for libclang (-I)."] = "",
    compile_args: Annotated[list[str] | str, "Optional extra compile args for libclang."] = "",
    use_clang: Annotated[bool | str, "Use libclang when available (default true)."] = True,
    use_cache: Annotated[bool | str, "Use scan result cache (default true)."] = True,
) -> str:
    result = scan_headers_impl(sdk_root, include_dirs, compile_args, use_clang, use_cache)
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool(description="Probe an SDK root or .pc file and suggest compile_tests parameters.")
async def probe_sdk(
    sdk_root: Annotated[str, "SDK root directory or path to a .pc file."],
) -> str:
    return json.dumps(probe_sdk_impl(sdk_root), indent=2, ensure_ascii=False)


@mcp.tool(description="Delete existing GTest files recursively.")
async def delete_tests(test_dir: Annotated[str, "Directory to scan for existing test files."]) -> str:
    return json.dumps(delete_tests_impl(test_dir), indent=2, ensure_ascii=False)


@mcp.tool(description="Compile GTest sources; auto-loads .forge.yaml/.forge.json from project.")
async def compile_tests(
    source_dir: Annotated[str, "Directory containing test .cpp files."],
    build_dir: Annotated[str, "Build directory for artifacts."],
    sdk_include_dirs: Annotated[list[str] | str, "SDK include directories."] = "",
    sdk_lib_dirs: Annotated[list[str] | str, "SDK library directories."] = "",
    link_libraries: Annotated[list[str] | str, "Libraries to link besides gtest."] = "",
    cmake_prefix_path: Annotated[list[str] | str, "CMAKE_PREFIX_PATH entries."] = "",
    find_packages: Annotated[list[dict] | str, "find_package specs as JSON list."] = "",
    pkg_config_packages: Annotated[list[str] | str, "pkg-config package names."] = "",
    extra_cmake_snippet: Annotated[str, "Extra CMake snippet appended before link lines."] = "",
    gtest_source: Annotated[str, "GTest: auto (default), cached, fetch, or system."] = "auto",
    gtest_version: Annotated[str, "Pin googletest tag, e.g. 1.14.0; auto picks by toolchain."] = "auto",
    coverage: Annotated[bool | str, "Enable gcov coverage flags."] = False,
    coverage_tool: Annotated[str, "Coverage tool: gcov or llvm-cov."] = "gcov",
    sanitizer: Annotated[str, "Sanitizer: none, asan, ubsan, asan+ubsan."] = "none",
    use_config: Annotated[bool | str, "Load .forge.yaml/.forge.json (default true)."] = True,
) -> str:
    return json.dumps(
        compile_tests_impl(
            source_dir, build_dir, sdk_include_dirs, sdk_lib_dirs, link_libraries,
            cmake_prefix_path, find_packages, pkg_config_packages, extra_cmake_snippet,
            gtest_source, gtest_version, coverage, coverage_tool, sanitizer, use_config,
        ),
        indent=2, ensure_ascii=False,
    )


@mcp.tool(description="Run a compiled GTest binary and return structured results.")
async def run_tests(
    build_dir: Annotated[str, "Build directory containing run_tests binary."],
    test_filter: Annotated[str, "Optional GTest filter pattern."] = "",
) -> str:
    return json.dumps(run_tests_impl(build_dir, test_filter), indent=2, ensure_ascii=False)


@mcp.tool(description="Collect gcov/lcov coverage from a build directory.")
async def collect_coverage(
    build_dir: Annotated[str, "Build directory with coverage artifacts."],
    source_dir: Annotated[str, "Optional source directory for gcov."] = "",
    coverage_tool: Annotated[str, "gcov (default) or llvm-cov."] = "gcov",
) -> str:
    return json.dumps(collect_coverage_impl(build_dir, source_dir, coverage_tool), indent=2, ensure_ascii=False)


@mcp.tool(description="Generate GMock templates from scan_headers JSON or SDK root.")
async def generate_mocks(
    scan_json: Annotated[str, "JSON from scan_headers, or sdk_root if scan_json is a directory path."] = "",
    sdk_root: Annotated[str, "SDK root to scan when scan_json is empty."] = "",
    class_name: Annotated[str, "Optional class name filter."] = "",
) -> str:
    if scan_json.strip():
        data = scan_json
    elif sdk_root.strip():
        data = scan_headers_impl(sdk_root)
    else:
        return json.dumps({"status": "error", "error": "Provide scan_json or sdk_root."}, indent=2)
    if isinstance(data, dict) and data.get("status") == "error":
        return json.dumps(data, indent=2, ensure_ascii=False)
    payload = data if isinstance(data, str) else json.dumps(data)
    return json.dumps(generate_mocks_impl(payload, class_name), indent=2, ensure_ascii=False)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="MCP server for SDK Forge")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    if args.transport == "sse":
        mcp.run(transport="sse", port=args.port)
    else:
        mcp.run(transport="stdio")


from sdk_forge.build import generate_cmake_content as _generate_cmake_content
from sdk_forge.cache import gtest_cache_dir as _gtest_cache_dir
from sdk_forge.scan import (
    HeaderFileInfo,
    parse_header as _parse_header,
    parse_header_clang as _parse_header_clang,
)
from sdk_forge.util import normalize_str_list as _normalize_str_list

_CLANG_AVAILABLE = CLANG_AVAILABLE

if __name__ == "__main__":
    main()
