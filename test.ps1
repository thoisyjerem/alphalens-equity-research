$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskTemp = Join-Path $PSScriptRoot 'work/tmp'
New-Item -ItemType Directory -Force -Path $taskTemp | Out-Null
$env:TEMP = $taskTemp
$env:TMP = $taskTemp
$testRunDirectory = 'work/pytest-run-' + [guid]::NewGuid().ToString('N')
& '.venv/Scripts/python.exe' -m pytest -q --tb=short --junitxml=outputs/test_results.xml --basetemp=$testRunDirectory
exit $LASTEXITCODE
