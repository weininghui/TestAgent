"""One-shot probe + compile + run pipeline."""

from __future__ import annotations

from pathlib import Path

from sdk_forge.retry import build_with_retry_impl, save_build_state


def build_pipeline_impl(
    project_dir: str = "",
    source_dir: str = "",
    build_dir: str = "",
    sdk_root: str = "",
    run_after_compile: bool | str = True,
    max_retries: int | str = 1,
    auto_fix_config: bool | str = False,
) -> dict:
    result = build_with_retry_impl(
        project_dir=project_dir,
        source_dir=source_dir,
        build_dir=build_dir,
        sdk_root=sdk_root,
        run_after_compile=run_after_compile,
        max_retries=max_retries,
        auto_fix_config=auto_fix_config,
    )
    if project_dir or result.get("source_dir"):
        try:
            cache_root = project_dir or str(Path(result.get("source_dir", ".")).parent)
            save_build_state(cache_root, result)
        except OSError:
            pass
    return result
