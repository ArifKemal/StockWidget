Remove-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "StockWidget" -ErrorAction SilentlyContinue
Write-Host "Startup kaydi kaldirildi."
