# State Machine

## Project States

- `CREATED`: project exists and has generated tasks.
- `RUNNING`: workflow is selecting or executing work.
- `WAITING_APPROVAL`: at least one high-risk task is waiting for human approval.
- `REVIEWING`: worker output is being reviewed.
- `COMPLETED`: all project tasks are accepted.
- `BLOCKED`: workflow stopped due to approval rejection or retry exhaustion.
- `FAILED`: unrecoverable error state reserved for future runtime failures.

Allowed transitions are enforced in `src/ai_org/domain/state_machine.py`.

## Task States

- `PENDING`: task exists but dependency readiness was not evaluated.
- `READY`: dependencies are accepted and the task can run.
- `RUNNING`: worker execution is in progress.
- `WAITING_APPROVAL`: high-risk task is paused at approval.
- `REVIEWING`: worker output is ready for independent review.
- `ACCEPTED`: review accepted the result.
- `REWORK_REQUIRED`: review requested another attempt.
- `BLOCKED`: approval rejection or retry exhaustion stopped the task.
- `FAILED`: reserved for unrecoverable worker or validation failures.

## Approval Outcomes

- `PENDING`: approval request has been created and the graph is interrupted.
- `APPROVED`: resume may continue to worker dispatch.
- `REJECTED`: worker dispatch is prohibited and the task/project become blocked.

## Review Outcomes

- `ACCEPTED`: task becomes `ACCEPTED`.
- `REWORK_REQUIRED`: task loops to `RUNNING` if attempts remain.
- `REJECTED`: task and project are blocked.

## Loop Boundaries

`attempt_count` is incremented before worker dispatch. If review asks for rework
and `attempt_count >= max_attempts`, the task transitions to `BLOCKED`; this
prevents infinite loops.

## Idempotency Rules

- Completed tasks are never re-dispatched.
- WorkerRun idempotency key is `worker-run:{task_id}:{worker_type}:{attempt}`.
- Approval idempotency key is `approval:{project_id}:{task_id}:execute_high_risk_task`.
- Repository implementations enforce optimistic version checks.
