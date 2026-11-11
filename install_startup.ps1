$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$app = Join-Path $dir "stock_widget.py"
$py = (Get-Command python).Source
$pyw = Join-Path (Split-Path $py) "pythonw.exe"
if (-not (Test-Path $pyw)) { $pyw = $py }
$value = '"' + $pyw + '" "' + $app + '"'
New-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "StockWidget" -Value $value -PropertyType String -Force | Out-Null
Write-Host "Startup kaydi eklendi: $value"
