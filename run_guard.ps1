$py = Join-Path (Get-Location) ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw ".venv python not found" }
$ver = & $py -c "import sys; print(sys.version.split()[0])"
if (-not $ver.StartsWith("3.11")) { throw "Wrong Python: $ver (need 3.11.x)" }
Write-Host "Python OK:" $ver
