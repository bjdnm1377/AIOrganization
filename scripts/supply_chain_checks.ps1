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
    "pyproject.toml",
    "requirements.in",
    "requirements-lock.txt",
    "docker-compose.yml",
    "alembic.ini",
    ".editorconfig",
    ".gitignore"
)

$output = & $Python -m detect_secrets scan -n @paths `
    --exclude-files "(?i)(__pycache__|\.pyc$|\.egg-info|^reports|^\.venv|^\.git)"
$code = $LASTEXITCODE
$output | Set-Content -Encoding utf8 reports\detect-secrets-report.json
exit $code
