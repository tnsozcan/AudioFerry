$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $Python)) {
    throw "Project Python environment not found: $Python"
}
Set-Location $Root

& $Python -m compileall -q audioferry_app.py tests
if ($LASTEXITCODE -ne 0) { throw "Python compilation failed" }
& $Python -m ruff check .
if ($LASTEXITCODE -ne 0) { throw "Ruff checks failed" }
& $Python -m mypy audioferry_app.py
if ($LASTEXITCODE -ne 0) { throw "Mypy checks failed" }
& $Python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "Tests failed" }
& $Python audioferry_app.py --version
if ($LASTEXITCODE -ne 0) { throw "Version startup check failed" }
