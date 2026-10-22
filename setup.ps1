param([string]$PythonExecutable = '')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskTemp = Join-Path $PSScriptRoot 'work/tmp'
New-Item -ItemType Directory -Force -Path $taskTemp | Out-Null
$env:TEMP = $taskTemp
$env:TMP = $taskTemp
$env:PIP_CACHE_DIR = Join-Path $PSScriptRoot 'work/pip-cache'
if (-not $PythonExecutable) {
    $bundledPython = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
    if (Test-Path -LiteralPath $bundledPython) {
        $PythonExecutable = $bundledPython
    } else {
        $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($pythonCommand) { $PythonExecutable = $pythonCommand.Source }
    }
}
if (-not $PythonExecutable) { throw 'Install Python 3.12+ or pass -PythonExecutable C:\Path\python.exe.' }
& $PythonExecutable -c 'import sys; assert sys.version_info >= (3,12), "Python 3.12+ is required for the tested dependency lock"'
if ($LASTEXITCODE -ne 0) { throw 'A working Python 3.12+ interpreter is required for the tested dependency lock.' }
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    & $PythonExecutable -m venv --without-pip .venv
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
}
& '.venv/Scripts/python.exe' -m ensurepip --upgrade
if ($LASTEXITCODE -ne 0) { throw 'pip installation failed.' }
& '.venv/Scripts/python.exe' -m pip install -r requirements.lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
if (-not (Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
Write-Host 'AlphaLens is ready. Launch: .\.venv\Scripts\python.exe -m streamlit run app.py'
