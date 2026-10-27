@echo off
cd /d "%~dp0"

rem ブラウザを開く係として呼ばれたとき
if "%~1"=="openbrowser" goto :openbrowser

if not exist ".venv\Scripts\python.exe" (
    echo [エラー] 実行環境 .venv が見つかりません。
    echo 先に「初回セットアップ.bat」をダブルクリックしてください。
    pause
    exit /b 1
)
echo 設備点検システムを起動します。この黒い窓は閉じないでください。
echo 終了するときは、この窓で Ctrl + C を押してください。
echo.
start /min "" "%~f0" openbrowser
".venv\Scripts\python.exe" app.py
pause
exit /b 0

:openbrowser
rem サーバーの起動を待つ
timeout /t 3 /nobreak >nul
rem 音付き動画を自動再生できるよう、専用の設定でEdgeを開く。
rem --user-data-dir を付けないと、既に開いているEdgeに合流して指定が無視される。
set "EDGE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" set "EDGE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" goto :fallback
start "" "%EDGE%" --user-data-dir="%~dp0.browser" --autoplay-policy=no-user-gesture-required --no-first-run --no-default-browser-check http://localhost:5000
exit /b 0

:fallback
rem Edgeが見つからないときは既定のブラウザで開く（音が出ないことがある）
start "" http://localhost:5000
exit /b 0
