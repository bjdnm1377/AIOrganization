# API

The FastAPI adapter is implemented in `src/ai_org/adapters/api/main.py`.

By default, the API uses in-memory storage. Set `AI_ORG_DATABASE_URL` to use the
PostgreSQL repository and PostgreSQL checkpoint saver. Set
`AI_ORG_CHECKPOINT_SETUP=true` only in initialization or test environments that
are allowed to create checkpoint tables.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Health and checkpoint strict-mode status |
| `POST` | `/projects` | Create a project and task specs |
| `GET` | `/projects/{project_id}` | Fetch project details |
| `GET` | `/projects/{project_id}/tasks` | List project tasks |
| `GET` | `/projects/{project_id}/worker-runs` | List all WorkerRuns for a project |
| `GET` | `/tasks/{task_id}/worker-runs` | List WorkerRuns for one task |
| `GET` | `/worker-runs/{run_id}` | Fetch one WorkerRun |
| `GET` | `/worker-runs/{run_id}/artifacts` | List structured artifact metadata |
| `POST` | `/projects/{project_id}/run` | Run or continue workflow until completion or interrupt |
| `GET` | `/projects/{project_id}/status` | Fetch workflow status |
| `GET` | `/projects/{project_id}/approvals` | List project approvals |
| `POST` | `/approvals/{approval_id}/decision` | Record approval and resume workflow |
| `GET` | `/projects/{project_id}/audit-events` | List audit events |
| `GET` | `/merge-candidates/{candidate_id}` | Fetch a bounded MergeCandidate summary |
| `GET` | `/projects/{project_id}/merge-candidates` | List MergeCandidates for a project |
| `POST` | `/merge-candidates/{candidate_id}/approval` | Approve or reject a waiting MergeCandidate |
| `POST` | `/merge-candidates/{candidate_id}/merge` | Enter the controlled merge/apply path for an approved candidate |

Artifact endpoints return `Artifact` metadata from structured `AgentResult`
output. They do not inline full diff, prompt, command-log content, database
passwords, environment variables, checkpoint binary payloads, or stack traces.
Codex Worker metadata uses logical worktree values such as
`worktree://codex/{task_id}/attempt-{n}`. MergeCandidate output is exposed as
artifact metadata through `GET /worker-runs/{run_id}/artifacts` and as a
`merge_candidate.created` audit event through
`GET /projects/{project_id}/audit-events`; neither endpoint performs a merge.
`worktree://codex/{task_id}/attempt-1`; artifact URIs use
`artifact://codex/...`.

MergeCandidate endpoints expose candidate identifiers, source type, base
commit, repository-relative changed files, bounded summaries, status, approval
metadata, and logical artifact/worktree URIs. They do not expose raw patches,
large diffs, local absolute paths, secrets, or tracebacks. Approval endpoints
require an explicit `APPROVED` or `REJECTED` decision. The merge endpoint does
not push or deploy; it can proceed only for an approved candidate and otherwise
returns `409`.

Candidate creation validates logical patch/worktree URI fields, and response
mappers defensively redact local paths or secret-like strings if malformed
internal data is ever present.

## Errors

- Missing resources return `404`.
- Illegal state transitions and conflicts return `409`.
- Validation errors return `422`.
- Unhandled internal errors return a generic `500` body.

## Example Codex Mock Task

```json
{
  "title": "Codex mock",
  "goal": "Create a deterministic coding artifact",
  "tasks": [
    {
      "title": "Code",
      "objective": "Create an isolated deterministic artifact",
      "worker_type": "codex",
      "metadata": {
        "codex_mode": "mock",
        "mock_output_file": "src/generated.txt",
        "allowed_files": ["src/generated.txt"]
      }
    }
  ]
}
```

## Example Manual Codex CLI Smoke Task

This task only runs real Codex if the server process was started with
`AI_ORG_ENABLE_REAL_CODEX_SMOKE=true` and the local Codex CLI is installed and
authenticated. CI does not enable this path.

```json
{
  "title": "Codex smoke",
  "goal": "Verify controlled real Codex CLI smoke path",
  "tasks": [
    {
      "title": "Create smoke file",
      "objective": "Create only smoke/codex_worker_smoke.txt with fixed smoke text.",
      "worker_type": "codex",
      "metadata": {
        "codex_mode": "local_cli",
        "allowed_files": ["smoke/**"],
        "codex_sandbox": "workspace-write",
        "codex_approval_policy": "on-request"
      }
    }
  ]
}
```
