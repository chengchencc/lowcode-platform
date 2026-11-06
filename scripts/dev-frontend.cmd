@echo off
rem Start the frontend dev server (Windows entry point, no WSL).
rem
rem   scripts\dev-frontend.cmd
rem
rem Same as dev-backend.cmd: use Git Bash explicitly instead of letting `bash`
rem resolve to WSL. Keep this file ASCII-only (see dev-backend.cmd).

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

"%BASH%" "%~dp0dev-frontend.sh" %*
set "RC=%ERRORLEVEL%"
if defined OLDCP chcp %OLDCP% >nul
exit /b %RC%
