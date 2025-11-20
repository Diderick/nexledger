@echo off
taskkill /f /im python.exe /im pythonw.exe
timeout /t 1 >nul
del "Z:\SourceCode\NexLedger\pro\companies\*.db"
echo All company databases deleted. You can now run NexLedger fresh.
pause