param(
    [string]$Python = ".\.venv\Scripts\python"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path "reports" | Out-Null

& $Python -m pip_audit --format json --output reports\pip-audit-report.json
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& .\.venv\Scripts\pip-licenses --format=json --output-file=reports\license-report.json
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python -m cyclonedx_py environment .\.venv --output-format JSON --output-file reports\sbom.json
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$paths = @(
    "src",
    "tests",
    "docs",
    "alembic",
    "README.md",
    "AGENTS.md",
    "ACCEPTANCE_REPORT.md",
    "FINAL_VERIFICATION_REPORT.md",
    "FINAL_CI_VERIFICATION_REPORT.md",
    "CODEX_WORKER_ACCEPTANCE_REPORT.md",
    "CODEX_REAL_SMOKE_TEST_REPORT.md",
    "CODEX_REAL_CODE_TASK_REPORT.md",
    "DOCKER_SANDBOX_ACCEPTANCE_REPORT.md",
    "CI_PENDING_REPORT.md",
    "CI_BLOCKED_REPORT.md",
    "CI_FAILED_REPORT.md",
    "pyproject.toml",
    "requirements.in",
    "requirements-lock.txt",
    "docker-compose.yml",
    "alembic.ini",
    ".editorconfig",
    ".gitignore",
    ".github"
)

$output = & $Python -m detect_secrets scan -n @paths `
    --exclude-files "(?i)(__pycache__|\.pyc$|\.egg-info|^reports|^\.venv|^\.git)"
$code = $LASTEXITCODE
$output | Set-Content -Encoding utf8 reports\detect-secrets-report.json
if ($code -ne 0) { exit $code }

$scan = Get-Content -Raw reports\detect-secrets-report.json | ConvertFrom-Json
$findings = 0
if ($null -ne $scan.results) {
    foreach ($property in $scan.results.PSObject.Properties) {
        $findings += @($property.Value).Count
    }
}
Write-Host "detect-secrets findings: $findings"
if ($findings -ne 0) { exit 1 }
