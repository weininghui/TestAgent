# Release Notes — v5.5.0

**Background delegation** — primary `forge` dispatches sub-agents in the background via oh-my-openagent, then advances the workflow when each task completes.

## Highlights

| Feature | Description |
|---------|-------------|
| **OMO background tasks** | Parallel enrich/scan batches use `task(run_in_background=true)` |
| **Delegation protocol** | `next_actions` include `subagent_type`, `title`, `run_in_background` |
| **State tracking** | `.forge/cache/delegations.json` + MCP `register_forge_delegation` |
| **Dispatch plan** | `get_delegation_plan` splits foreground vs background actions |
| **Inline fallback** | `delegation_mode: inline` restores v5.3 sync `task()` |

## Setup

1. Install **oh-my-openagent** in OpenCode
2. Merge forge agents: `scripts/merge-omo-forge-agents.ps1`
3. Set in `.forge.yaml`: `delegation_mode: omo` (production default)
4. Select **forge** primary agent

See [docs/DELEGATION.md](../DELEGATION.md).

## MCP tools (new)

- `register_forge_delegation`
- `poll_forge_delegations`
- `get_delegation_plan`

## Agents updated

- `forge` — v5.5 background delegation loop
- `forge-env` … `forge-build` — finish with `advance_forge_workflow`

## Tests

`TestDelegationV55` — delegation metadata, inline regression, register/poll/advance flow.
