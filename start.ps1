Set-Location $PSScriptRoot
if (-not (Test-Path "data\zhixue.db")) {
  Write-Host "[习得] 首次运行，生成演示数据..."
  python seed.py --reset
}
Write-Host "[习得] http://127.0.0.1:5820"
python app.py
