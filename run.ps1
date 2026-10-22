$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskTemp = Join-Path $PSScriptRoot 'work/tmp'
New-Item -ItemType Directory -Force -Path $taskTemp | Out-Null
$env:TEMP = $taskTemp
$env:TMP = $taskTemp
& '.venv/Scripts/python.exe' -m streamlit run app.py --server.address 127.0.0.1 --server.headless true --browser.gatherUsageStats false
exit $LASTEXITCODE
