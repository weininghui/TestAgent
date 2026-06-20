## Summary

<!-- What changed and why (1–3 sentences) -->

## Test plan

- [ ] `python -m pytest tests/ -v -k "not TestCompileAndRun and not TestCoveragePipeline and not TestCliIntegration"`
- [ ] (if MCP/tools) added/updated tests in `tests/test_mcp_server.py`
- [ ] (if release) version files + RELEASE_NOTES updated per [docs/RELEASE_PROCESS.md](docs/RELEASE_PROCESS.md)
