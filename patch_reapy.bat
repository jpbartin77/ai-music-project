@echo off
echo Applying reapy-next Python 3.13 compatibility patches...

REM ── Patch system Python ──
echo Patching system Python...
copy /Y "%~dp0envelope.py" "C:\Users\jpbar\AppData\Local\Programs\Python\Python313\Lib\site-packages\reapy\core\envelope.py"
copy /Y "%~dp0config.py" "C:\Users\jpbar\AppData\Local\Programs\Python\Python313\Lib\site-packages\reapy\config\config.py"

REM ── Patch venv ──
echo Patching venv...
copy /Y "%~dp0envelope.py" "C:\Users\jpbar\My Drive\Technical Projects\ai-music-project\.venv\Lib\site-packages\reapy\core\envelope.py"
copy /Y "%~dp0config.py" "C:\Users\jpbar\My Drive\Technical Projects\ai-music-project\.venv\Lib\site-packages\reapy\config\config.py"

echo Done! Both locations patched.
echo Remember to restart Reaper and run enable_reapy.py after patching.
pause