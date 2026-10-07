@echo off
rem ==========================================================
rem  Claude Code CLI against OpenRouter, running Qwen 3.8 27B in the cloud - for machines
rem  without a GPU strong enough to host the model locally.
rem  Usage: claude-openrouter [any claude arguments]
rem
rem  Needs openrouter-key.txt in this folder: create a key at https://openrouter.ai/keys
rem  and paste it into that file yourself (it is git-ignored). You pay OpenRouter per token.
rem  Everything is set for THIS process only; the profile lives in
rem  %USERPROFILE%\.claude-openrouter. Your normal `claude` and ~/.claude are untouched.
rem
rem  UNTESTED by this project: OpenRouter only guarantees Claude Code with Anthropic models.
rem ==========================================================
setlocal
set "ROOT=%~dp0"
set "PROFILE_DIR=%USERPROFILE%\.claude-openrouter"
set "OR_MODEL=qwen/qwen3.8-27b"
set "OR_CTX=262144"

if not exist "%PROFILE_DIR%\settings.json" (
  echo [claude-openrouter] No profile yet. Open Claude Code in this folder and type: Onboard me
  exit /b 1
)
if not exist "%ROOT%openrouter-key.txt" (
  echo [claude-openrouter] Missing openrouter-key.txt - create a key at https://openrouter.ai/keys
  echo                     and paste it into %ROOT%openrouter-key.txt
  exit /b 1
)
set /p KEY=<"%ROOT%openrouter-key.txt"

set "TESTED="
for /f "usebackq delims=" %%v in (`powershell -NoProfile -Command "(Get-Content -Raw (Join-Path $env:ROOT 'release.json') | ConvertFrom-Json).tested.claude_code"`) do set "TESTED=%%v"
set "CCV="
for /f "tokens=1" %%v in ('claude --version 2^>nul') do set "CCV=%%v"
if not defined CCV (
  echo [claude-openrouter] The claude command was not found. Install Claude Code first.
  exit /b 1
)
if not "%CCV%"=="%TESTED%" (
  echo [claude-openrouter] NOTE: Claude Code %CCV% is installed; this project was tested with %TESTED%. 1>&2
  echo [claude-openrouter]       It will most likely work, but this version is NOT tested. 1>&2
)

set "CLAUDE_CONFIG_DIR=%PROFILE_DIR%"
set "ANTHROPIC_BASE_URL=https://openrouter.ai/api"
set "ANTHROPIC_AUTH_TOKEN=%KEY%"
rem OpenRouter's guide: no Anthropic API key may be in play. cmd cannot hold an empty variable,
rem so this clears any key inherited from your environment, for this process only.
set "ANTHROPIC_API_KEY="
set "ANTHROPIC_MODEL=%OR_MODEL%"
set "ANTHROPIC_DEFAULT_FABLE_MODEL=%OR_MODEL%"
set "ANTHROPIC_DEFAULT_OPUS_MODEL=%OR_MODEL%"
set "ANTHROPIC_DEFAULT_SONNET_MODEL=%OR_MODEL%"
set "ANTHROPIC_DEFAULT_HAIKU_MODEL=%OR_MODEL%"
set "CLAUDE_CODE_SUBAGENT_MODEL=%OR_MODEL%"
set "CLAUDE_CODE_MAX_CONTEXT_TOKENS=%OR_CTX%"
set "CLAUDE_CODE_ATTRIBUTION_HEADER=0"
set "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1"

echo [claude-openrouter] %OR_MODEL% via OpenRouter, %OR_CTX% tokens of context (billed per token) 1>&2
claude %*
