@echo off
rem Start the backend dev server (Windows entry point, no WSL).
rem
rem   scripts\dev-backend.cmd
rem   set PORT=8001 && scripts\dev-backend.cmd
rem
rem Typing `bash scripts\dev-backend.sh` in cmd or PowerShell can resolve `bash`
rem to C:\Windows\System32\bash.exe (WSL), which cannot see the Windows .venv.
rem This wrapper finds Git Bash explicitly and runs the .sh script with it.
rem
rem Keep this file ASCII-only: cmd parses batch files with the console code page
rem that was active at launch, so UTF-8 comments can be split mid-character and
rem executed as commands under a GBK (936) console.

setlocal
set "OLDCP="
for /f "tokens=2 delims=:" %%C in ('chcp') do set "OLDCP=%%C"
chcp 65001 >nul

set "BASH="
for /f "delims=" %%G in ('where git 2^>nul') do set "GIT_CMD=%%~dpG"
if defined GIT_CMD if exist "%GIT_CMD%..\bin\bash.exe" set "BASH=%GIT_CMD%..\bin\bash.exe"
if not defined BASH if defined GIT_CMD if exist "%GIT_CMD%..\usr\bin\bash.exe" set "BASH=%GIT_CMD%..\usr\bin\bash.exe"
if not defined BASH if exist "%ProgramFiles%\Git\bin\bash.exe" set "BASH=%ProgramFiles%\Git\bin\bash.exe"
if not defined BASH if exist "%LocalAppData%\Programs\Git\bin\bash.exe" set "BASH=%LocalAppData%\Programs\Git\bin\bash.exe"

if not defined BASH (
  echo [x] Git Bash not found. Install Git for Windows: https://git-scm.com/download/win
  if defined OLDCP chcp %OLDCP% >nul
  exit /b 1
)

"%BASH%" "%~dp0dev-backend.sh" %*
set "RC=%ERRORLEVEL%"
if defined OLDCP chcp %OLDCP% >nul
exit /b %RC%
