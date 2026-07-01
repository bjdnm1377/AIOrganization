# API

The FastAPI adapter is implemented in `src/ai_org/adapters/api/main.py`.

By default, the API uses in-memory storage so tests and local smoke runs need no
database. Set `AI_ORG_DATABASE_URL` to use the PostgreSQL repository and
PostgreSQL checkpoint saver. Set `AI_ORG_CHECKPOINT_SETUP=true` only for
initialization/test environments that are allowed to create checkpoint tables.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Health and checkpoint strict-mode status |
| `POST` | `/projects` | Create a project and default task |
| `GET` | `/projects/{project_id}` | Fetch project details |
| `GET` | `/projects/{project_id}/tasks` | List project tasks |
| `POST` | `/projects/{project_id}/run` | Run or continue workflow until completion or interrupt |
| `GET` | `/projects/{project_id}/status` | Fetch workflow status |
| `GET` | `/projects/{project_id}/approvals` | List project approvals |
| `POST` | `/approvals/{approval_id}/decision` | Record approval and resume workflow |
| `GET` | `/projects/{project_id}/audit-events` | List audit events |

## Errors

- Missing resources return `404`.
- Illegal state transitions and conflicts return `409`.
- Validation errors return `422`.
- Unhandled internal errors return a generic `500` body.

API responses do not include database passwords, environment variables,
checkpoint binary payloads, or exception stack traces.

## Example Low-Risk Request

```json
{
  "title": "Demo",
  "goal": "Create a deterministic mock result",
  "success_criteria": ["workflow completes"],
  "tasks": [
    {
      "title": "Research",
      "objective": "Produce deterministic evidence",
      "worker_type": "research",
      "risk_level": "LOW",
      "acceptance_criteria": ["workflow completes"]
    }
  ]
}
```

## Example Approval Decision

```json
{
  "decision": "APPROVED",
  "decision_reason": "Risk accepted for deterministic test"
}
```
