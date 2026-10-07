@echo off
rem ==========================================================
rem  Claude Code CLI against the local server (whichever model it has loaded).
rem  Usage: claude-local [any claude arguments]     e.g.  claude-local -p "hi"
rem
rem  Everything is set for THIS process only. The normal `claude` command, its
rem  claude.ai login and ~/.claude are untouched: this profile keeps its own
rem  config, history and settings in %USERPROFILE%\.claude-local (created by onboarding,
rem  or: py -3 lib\make-profile.py local --mode bypass).
rem  The model id and context size are read from the running server's /props,
rem  so start the server (Start-Local-LLM-Server.bat) first.
rem ==========================================================
setlocal
set "ROOT=%~dp0"
set "PROFILE_DIR=%USERPROFILE%\.claude-local"
if not defined LOCAL_LLM_URL set "LOCAL_LLM_URL=http://127.0.0.1:8080"

if not exist "%PROFILE_DIR%\settings.json" (
  echo [claude-local] No profile yet. Open Claude Code in this folder and type: Onboard me
  exit /b 1
)
if not exist "%ROOT%api-key.txt" (
  echo [claude-local] No api-key.txt - start Start-Local-LLM-Server.bat once; it creates the key.
  exit /b 1
)
set /p KEY=<"%ROOT%api-key.txt"

rem --- the Claude Code version this project was tested with (release.json) ---
set "TESTED="
for /f "usebackq delims=" %%v in (`powershell -NoProfile -Command "(Get-Content -Raw (Join-Path $env:ROOT 'release.json') | ConvertFrom-Json).tested.claude_code"`) do set "TESTED=%%v"
set "CCV="
for /f "tokens=1" %%v in ('claude --version 2^>nul') do set "CCV=%%v"
if not defined CCV (
  echo [claude-local] The claude command was not found. Install Claude Code first.
  exit /b 1
)
if not "%CCV%"=="%TESTED%" (
  echo [claude-local] NOTE: Claude Code %CCV% is installed; this project was tested with %TESTED%. 1>&2
  echo [claude-local]       It will most likely work, but this version is NOT tested. 1>&2
)

set "MODEL="
set "CTX="
for /f "usebackq tokens=1,2" %%a in (`powershell -NoProfile -Command "try { $p = Invoke-RestMethod -TimeoutSec 5 -Uri '%LOCAL_LLM_URL%/props' -Headers @{Authorization = 'Bearer %KEY%'}; '{0} {1}' -f $p.model_alias, $p.default_generation_settings.n_ctx } catch { }"`) do (
  set "MODEL=%%a"
  set "CTX=%%b"
)
if not defined MODEL (
  echo [claude-local] No server answering at %LOCAL_LLM_URL% - start Start-Local-LLM-Server.bat first.
  exit /b 1
)

set "CLAUDE_CONFIG_DIR=%PROFILE_DIR%"
set "ANTHROPIC_BASE_URL=%LOCAL_LLM_URL%"
set "ANTHROPIC_AUTH_TOKEN=%KEY%"
rem Every model slot Claude Code knows about -> the one model the server has loaded.
set "ANTHROPIC_MODEL=%MODEL%"
set "ANTHROPIC_DEFAULT_FABLE_MODEL=%MODEL%"
set "ANTHROPIC_DEFAULT_OPUS_MODEL=%MODEL%"
set "ANTHROPIC_DEFAULT_SONNET_MODEL=%MODEL%"
set "ANTHROPIC_DEFAULT_HAIKU_MODEL=%MODEL%"
set "CLAUDE_CODE_SUBAGENT_MODEL=%MODEL%"
rem The server's real window; auto-compact then works inside it instead of 400-ing.
set "CLAUDE_CODE_MAX_CONTEXT_TOKENS=%CTX%"
rem A per-turn system block that would otherwise change every request (and break the cache).
set "CLAUDE_CODE_ATTRIBUTION_HEADER=0"
rem No telemetry, error reports or update checks to Anthropic from this profile.
set "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1"

rem to stderr, so `claude-local -p ... --output-format json` stays parseable
echo [claude-local] %MODEL% at %LOCAL_LLM_URL%, %CTX% tokens of context 1>&2
if %CTX% LSS 65536 echo [claude-local] Context is under 64K: Claude Code compacts at context minus 33K, so sessions will be cramped. 1>&2
claude %*
