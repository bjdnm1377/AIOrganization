from __future__ import annotations

from pathlib import Path

from ai_org.ports.sandbox import SandboxCommandSpec, SandboxMount, SandboxPolicy

CREDENTIAL_PATH_MARKERS = (
    ".env",
    ".ssh",
    ".git-credentials",
    ".gitconfig",
    ".aws",
    ".azure",
    ".config/gcloud",
    "AppData/Roaming/gh",
    "AppData/Local/GitCredentialManager",
)


class SandboxPolicyError(ValueError):
    """Raised when a sandbox command violates the configured policy."""


def validate_sandbox_spec(spec: SandboxCommandSpec) -> None:
    policy = spec.policy
    _validate_policy_baseline(policy)
    worktree = _resolved(spec.worktree_path)
    if not worktree.exists() or not worktree.is_dir():
        raise SandboxPolicyError("Sandbox worktree must exist and be a directory.")
    if _is_forbidden_primary_mount(worktree):
        raise SandboxPolicyError("Sandbox worktree may not be a home or credential path.")
    if not spec.command or any(not part for part in spec.command):
        raise SandboxPolicyError("Sandbox command must contain non-empty argv parts.")
    if _contains_secret_env(spec.env):
        raise SandboxPolicyError("Sandbox environment may not include secret-like keys.")
    for mount in policy.mounts.extra_mounts:
        _validate_extra_mount(mount, worktree)


def _validate_policy_baseline(policy: SandboxPolicy) -> None:
    if policy.privileged:
        raise SandboxPolicyError("Privileged containers are not allowed.")
    if "ALL" not in policy.cap_drop:
        raise SandboxPolicyError("Sandbox policy must drop all Linux capabilities.")
    if "no-new-privileges" not in policy.security_options:
        raise SandboxPolicyError("Sandbox policy must enable no-new-privileges.")
    if not policy.read_only_rootfs:
        raise SandboxPolicyError("Sandbox policy must use a read-only root filesystem.")
    if policy.network.enabled:
        raise SandboxPolicyError("Sandbox network access requires a later approval flow.")
    if not policy.user or policy.user == "0" or policy.user.startswith("0:"):
        raise SandboxPolicyError("Sandbox policy must not run as root.")
    if not policy.mounts.container_workdir.startswith("/"):
        raise SandboxPolicyError("Sandbox container workdir must be absolute.")
    limits = policy.resources
    if limits.timeout_seconds <= 0:
        raise SandboxPolicyError("Sandbox timeout must be positive.")
    if limits.pids_limit <= 0:
        raise SandboxPolicyError("Sandbox pids limit must be positive.")
    if limits.stdout_limit_bytes <= 0 or limits.stderr_limit_bytes <= 0:
        raise SandboxPolicyError("Sandbox output limits must be positive.")


def _validate_extra_mount(mount: SandboxMount, worktree: Path) -> None:
    host_path = _resolved(mount.host_path)
    if host_path == worktree or _is_relative_to(host_path, worktree):
        return
    if _is_credential_path(host_path):
        raise SandboxPolicyError("Credential and dotenv paths may not be mounted.")
    raise SandboxPolicyError("Only task worktree paths may be mounted into the sandbox.")


def _contains_secret_env(env: dict[str, str]) -> bool:
    sensitive = ("SECRET", "TOKEN", "PASSWORD", "API_KEY", "AUTH", "CREDENTIAL")
    return any(any(marker in key.upper() for marker in sensitive) for key in env)


def _is_credential_path(path: Path) -> bool:
    normalized = path.as_posix()
    return any(marker in normalized for marker in CREDENTIAL_PATH_MARKERS)


def _is_forbidden_primary_mount(path: Path) -> bool:
    try:
        home = Path.home().resolve()
    except OSError:
        home = None
    if home is not None and path == home:
        return True
    return _is_credential_path(path)


def _resolved(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError as exc:
        raise SandboxPolicyError(f"Could not resolve sandbox path: {path}") from exc


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
