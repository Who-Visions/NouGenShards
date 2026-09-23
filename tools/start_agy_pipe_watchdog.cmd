@echo off
rem Headless bridge for AgyPipeWatchdog
wscript.exe //B //Nologo "%USERPROFILE%\.nougen\bin\run_hidden.vbs" "%USERPROFILE%\Watchtower\NouGen\NouGenShards-push-main\.venv\Scripts\pythonw.exe" "%USERPROFILE%\.nougen\bin\agy_pipe_server.py"
exit /b 0
