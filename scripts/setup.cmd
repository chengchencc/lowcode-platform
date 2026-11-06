@echo off
rem First-time setup (Windows entry point, no WSL).
rem
rem   scripts\setup.cmd
rem
rem Idempotent. Runs setup.sh through Git Bash.
rem Keep this file ASCII-only (see dev-backend.cmd).

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

"%BASH%" "%~dp0setup.sh" %*
set "RC=%ERRORLEVEL%"
if defined OLDCP chcp %OLDCP% >nul
exit /b %RC%
