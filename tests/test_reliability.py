"""Reliability tests: logging, audit, auto-recovery (v5.12–v5.14)."""

from __future__ import annotations

import json

import pytest


class TestLoggingV512:
    def test_configure_and_run_id(self):
        from sdk_forge.infra.logging_config import configure_forge_logging, get_logger
        from sdk_forge.infra.trace import get_run_id, inject_run_id, new_run_id, set_run_id

        configure_forge_logging(level="DEBUG")
        rid = new_run_id()
        set_run_id(rid)
        assert get_run_id() == rid
        result = {"status": "ok"}
        inject_run_id(result)
        assert result["run_id"] == rid

        logger = get_logger("test")
        assert logger.name == "sdk_forge.test"

    def test_forge_json_injects_run_id(self):
        from sdk_forge.infra.response import forge_json
        from sdk_forge.infra.trace import new_run_id, set_run_id

        set_run_id(new_run_id())
        raw = forge_json({"status": "ok"})
        data = json.loads(raw)
        assert data.get("run_id")
        assert data["status"] == "ok"

    def test_audit_log_write_read(self, tmp_path):
        from sdk_forge.infra.audit import audit_log, read_audit_log
        from sdk_forge.infra.trace import new_run_id, set_run_id

        set_run_id(new_run_id())
        audit_log("stage_start", project_dir=str(tmp_path), stage="scan")
        audit_log("stage_end", project_dir=str(tmp_path), stage="scan")
        out = read_audit_log(str(tmp_path), last_n=10)
        assert out["status"] == "ok"
        assert out["count"] == 2
        assert out["events"][0]["event"] == "stage_start"
        assert out["events"][1]["event"] == "stage_end"

    def test_session_context_includes_recent_audit(self, tmp_path):
        from sdk_forge.infra.audit import audit_log
        from sdk_forge.infra.session import get_session_context_impl

        (tmp_path / ".forge" / "cache").mkdir(parents=True, exist_ok=True)
        audit_log("delegation_register", project_dir=str(tmp_path), agent="forge-enrich")
        ctx = get_session_context_impl(str(tmp_path))
        assert ctx["status"] == "ok"
        assert len(ctx.get("recent_audit") or []) >= 1

    def test_cli_emit_run_id(self, capsys):
        from sdk_forge.cli import _emit
        from sdk_forge.infra.trace import new_run_id, set_run_id

        set_run_id(new_run_id())
        code = _emit({"status": "ok", "total": 1})
        assert code == 0
        out = json.loads(capsys.readouterr().out)
        assert out.get("run_id")

    @pytest.mark.asyncio
    async def test_mcp_get_forge_audit_log(self, tmp_path):
        from mcp_server import get_forge_audit_log
        from sdk_forge.infra.audit import audit_log

        audit_log("health_issue", project_dir=str(tmp_path), agent="forge-build")
        raw = await get_forge_audit_log(str(tmp_path), last_n=5)
        data = json.loads(raw)
        assert data["status"] == "ok"
        assert data["count"] >= 1
        assert data.get("run_id")


class TestAutoRecoveryV513:
    def test_should_auto_recover_respects_max(self, tmp_path):
        from sdk_forge.delegation.recovery import (
            record_recovery_attempt,
            retry_count_for_batch,
            should_auto_recover,
        )

        cfg_path = tmp_path / ".forge.json"
        cfg_path.write_text(
            json.dumps(
                {
                    "delegation_auto_recovery": True,
                    "delegation_auto_recovery_max": 2,
                    "delegation_retry_backoff_sec": 0,
                }
            ),
            encoding="utf-8",
        )
        entry = {"health": "timeout", "agent": "forge-enrich", "batch_id": 0, "task_id": "t1"}
        ok, reason = should_auto_recover(entry, str(tmp_path), force=True)
        assert ok and reason == "eligible"

        record_recovery_attempt(str(tmp_path), "forge-enrich", 0)
        record_recovery_attempt(str(tmp_path), "forge-enrich", 0)
        assert retry_count_for_batch(str(tmp_path), "forge-enrich", 0) == 2

        ok2, reason2 = should_auto_recover(entry, str(tmp_path), force=True)
        assert not ok2 and reason2 == "circuit_open"

    def test_backoff_blocks_rapid_retry(self, tmp_path):
        from sdk_forge.delegation.recovery import record_recovery_attempt, should_auto_recover

        (tmp_path / ".forge.json").write_text(
            json.dumps(
                {
                    "delegation_auto_recovery": True,
                    "delegation_auto_recovery_max": 5,
                    "delegation_retry_backoff_sec": 3600,
                }
            ),
            encoding="utf-8",
        )
        entry = {"health": "stale", "agent": "forge-scan", "batch_id": 1, "task_id": "t2"}
        record_recovery_attempt(str(tmp_path), "forge-scan", 1)
        ok, reason = should_auto_recover(entry, str(tmp_path), force=False)
        assert not ok and reason == "backoff"

    def test_poll_auto_recovery(self, tmp_path, monkeypatch):
        from sdk_forge.delegation.core import poll_forge_delegations_impl, register_delegation_impl

        (tmp_path / ".forge.json").write_text(
            json.dumps({"delegation_auto_recovery": True, "delegation_auto_recovery_max": 2}),
            encoding="utf-8",
        )
        register_delegation_impl(str(tmp_path), "task_ar1", "forge-enrich", batch_id=0)

        stale_entry = {
            "task_id": "task_ar1",
            "agent": "forge-enrich",
            "batch_id": 0,
            "health": "stale",
            "issues": [{"kind": "stale"}],
        }

        def fake_health(project_dir, include_preview=True):
            return {
                "status": "ok",
                "needs_recovery": [stale_entry],
                "unhealthy_count": 1,
                "pending_count": 1,
                "subagents": [stale_entry],
            }

        recover_calls = []

        def fake_recover(project_dir, task_id="", action="retry", failure_reason=""):
            recover_calls.append(task_id)
            return {"status": "ok", "action": action, "workflow": {"status": "needs_agent"}}

        monkeypatch.setattr("sdk_forge.delegation.health.check_subagent_health_impl", fake_health)
        monkeypatch.setattr(
            "sdk_forge.delegation.health.recover_stalled_subagent_impl", fake_recover
        )

        polled = poll_forge_delegations_impl(str(tmp_path))
        assert polled.get("auto_recovered")
        assert recover_calls == ["task_ar1"]

    def test_production_profile_enables_auto_recovery(self):
        from sdk_forge.infra.profile import resolve_forge_config

        cfg = resolve_forge_config({"forge_profile": "production"})
        assert cfg.get("delegation_auto_recovery") is True


class TestForgeErrorV514:
    def test_forge_error_to_dict(self):
        from sdk_forge.domain.errors import ForgeError, forge_error_to_dict

        exc = ForgeError(
            "scan failed",
            code="SCAN_CLANG_FAILED",
            stage="scan",
            hints=["use --no-clang"],
            recoverable=True,
        )
        d = forge_error_to_dict(exc, run_id="forge_abc12345")
        assert d["error_code"] == "SCAN_CLANG_FAILED"
        assert d["stage"] == "scan"
        assert d["recoverable"] is True
        assert d["run_id"] == "forge_abc12345"

    def test_build_cmake_error_has_error_code(self, tmp_path, monkeypatch):
        from sdk_forge.pipeline import build as build_mod
        from sdk_forge.pipeline.build import compile_tests_impl

        src = tmp_path / "tests"
        src.mkdir()
        (src / "empty_test.cpp").write_text("// empty\n", encoding="utf-8")
        build = tmp_path / "build"

        class FakeResult:
            returncode = 1
            stdout = ""
            stderr = "undefined reference to `missing_symbol'"

        monkeypatch.setattr(build_mod, "run_subprocess", lambda *a, **k: FakeResult())

        result = compile_tests_impl(str(src), str(build), use_config=False)
        assert result.get("status") == "cmake_error"
        assert result.get("error_code") == "BUILD_LINK_ERROR"
