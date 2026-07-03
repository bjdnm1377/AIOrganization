# Codex CLI Diagnostics

## Current Status

Local real Codex CLI diagnostics are blocked on this host. The diagnostic
stage must not be reported as passing.

Observed facts from the latest diagnostic run:

- `codex --version` completed.
- `codex doctor --json` completed.
- Read-only exec completed near the timeout and reported transport-stall
  signals.
- Single-file create timed out after the bounded timeout.
- JSONL events observed: `9`.
- File-change events observed: `0`.
- Last event: `item.started`.
- Approval requested: false.
- Process and process tree were killed.
- Main worktree fingerprint before and after was identical.
- No MergeCandidate was generated.
- No merge was performed.
- No push was performed.

## Purpose

The diagnostic path exists to isolate CLI/app-server/auth/transport behavior
before another real Coding Worker task is attempted. It is not a Coding Worker
success path and it cannot authorize merge approval or merge execution.

## Execution Boundary

The manual diagnostic test is disabled by default and requires:

```powershell
$env:AI_ORG_ENABLE_REAL_CODEX_DIAGNOSTICS = "true"
.\.venv\Scripts\python -m pytest tests\manual\test_real_codex_cli_diagnostics.py -q
```

The test creates an independent temporary Git repository. The project main
worktree is only fingerprinted before and after the diagnostic. The diagnostic
does not run in the AIleader source tree, does not create a MergeCandidate,
does not commit, does not merge, and does not push.

## CI Boundary

GitHub Actions sets `AI_ORG_ENABLE_REAL_CODEX_DIAGNOSTICS=false` and does not
require Codex CLI, Codex auth, an OpenAI API key, or a GitHub token. CI runs
only unit tests for diagnostic command construction, event classification,
sanitization, timeout reporting, and Review Worker rejection.

## Next Revalidation Options

The same bounded diagnostic can be repeated after changing the runtime
environment, for example:

- WSL or Linux;
- a different Codex CLI version;
- a repaired or restarted Codex App server;
- a Codex App worktree;
- a remote controlled development host.

The diagnostic remains blocked until the single-file create scenario completes
without timeout and without main-worktree fingerprint drift.
