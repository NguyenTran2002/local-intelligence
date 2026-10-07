@echo off
setlocal EnableDelayedExpansion
title Local LLM Server - Gemma 4 / Qwen 3.8

set "ROOT=%~dp0"

rem ==========================================================
rem  DEFAULTS = the reference machine: RTX 5090 (32 GB), nothing else on the GPU
rem  (monitor on the integrated GPU). Every context below was measured there as the largest
rem  that survives the worst case - a max-size image, a prompt at ~99%% of context, then two
rem  max-size images at once - at full speed. Past usable VRAM, Gemma SILENTLY spills into
rem  system RAM (prefill ~7x slower, no error) and Qwen CRASHES on the next image.
rem
rem  Any other GPU: onboarding ("Onboard me" in Claude Code) writes config\machine.cmd,
rem  which overrides these values. Its contexts are ESTIMATES until lib\fit-test.py passes.
rem  A context of 0 means "not offered on this GPU".
rem ==========================================================
set "MODELS_DIR=%ROOT%models"
set "LLAMA_DIR=%ROOT%llamacpp\bin"
set "HOST=127.0.0.1"
set "PORT=8080"
set "SLOTS=2"
set "CRAM=24576"
set "TIER="
set "GPU_NAME="
set "G_IMGMAX=1600"
set "Q_IMGMAX=4096"
set "CTX_D_STD=200704"
set "CTX_D_TURBO=153600"
set "CTX_H_STD=188416"
set "CTX_H_TURBO=144384"
set "CTX_M=262144"
set "CTX_Q_STD=262144"
set "CTX_Q_TURBO=245760"
set "CTX_Q3_STD=0"
set "CONFIGURED="
if exist "%ROOT%config\machine.cmd" (
  call "%ROOT%config\machine.cmd"
  set "CONFIGURED=1"
)

set "BIN=%LLAMA_DIR%\llama-server.exe"
set "KEYFILE=%ROOT%api-key.txt"
set "IPPS=%ROOT%lib\get-lan-ip.ps1"
set "ZDRFILTER=%ROOT%lib\zdr-log-filter.py"

rem --- 31B dense. Its vision tower and MTP drafter are shared with the uncensored build. ---
set "D_MODEL=%MODELS_DIR%\gemma-4-31B-it-qat\gemma-4-31B-it-qat-UD-Q4_K_XL.gguf"
set "D_MMPROJ=%MODELS_DIR%\gemma-4-31B-it-qat\mmproj-F16.gguf"
set "D_MTP=%MODELS_DIR%\gemma-4-31B-it-qat\mtp-gemma-4-31B-it.gguf"
rem --- 31B dense, uncensored (Heretic abliteration), built locally by
rem     models\gemma-4-31B-it-qat-heretic\build-heretic-gguf.py ---
set "H_MODEL=%MODELS_DIR%\gemma-4-31B-it-qat-heretic\gemma-4-31B-it-qat-heretic-Q4_0-attnQ8_0.gguf"
rem --- 26B-A4B MoE. Its mmproj is NOT interchangeable with the 31B's, despite the same name. ---
set "M_MODEL=%MODELS_DIR%\unsloth-26B-A4B-qat\gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf"
set "M_MMPROJ=%MODELS_DIR%\unsloth-26B-A4B-qat\mmproj-F16.gguf"
set "M_MTP=%MODELS_DIR%\unsloth-26B-A4B-qat\mtp-gemma-4-26B-A4B-it.gguf"
rem --- Qwen 3.8 27B. 4-bit UD-Q4_K_XL (MTP head built in), or 3-bit UD-IQ3_XXS on 16 GB cards
rem     (UNTESTED). The chat template is a one-line patch: a system message after the first
rem     turn used to be an HTTP 500; it is now rendered in place. ---
set "Q_MODEL=%MODELS_DIR%\qwen3.8-27B\Qwen3.8-27B-UD-Q4_K_XL.gguf"
set "Q3_MODEL=%MODELS_DIR%\qwen3.8-27B\Qwen3.8-27B-UD-IQ3_XXS.gguf"
set "Q_MMPROJ=%MODELS_DIR%\qwen3.8-27B\mmproj-F16.gguf"
set "Q_TMPL=%ROOT%models\qwen3.8-27B\qwen3.8-chat-template-patched.jinja"

if not exist "%BIN%" (
  echo [ERROR] llama.cpp is not installed: %BIN%
  echo         Open Claude Code in this folder and type: Onboard me
  pause
  exit /b 1
)

rem --- API key: generated on first launch, kept in api-key.txt (never committed). ---
if not exist "%KEYFILE%" (
  powershell -NoProfile -Command "$b = New-Object byte[] 24; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); [IO.File]::WriteAllText($env:KEYFILE, 'li-' + [BitConverter]::ToString($b).Replace('-','').ToLower())"
  if not exist "%KEYFILE%" ( echo [ERROR] Could not create %KEYFILE% & pause & exit /b 1 )
  echo Created a new API key in api-key.txt
)
set /p APIKEY=<"%KEYFILE%"

rem --- ZDR: the log must hold metadata only, but llama-server echoes model output into some
rem     warnings (unparsable tool calls, malformed output). So the server's output is piped
rem     through lib\zdr-log-filter.py, which writes the log with that text redacted; --log-file
rem     is not used. The console still shows everything (it is not stored).
rem     No Python = no filter = refuse to start, rather than log unfiltered. ---
if not exist "%ZDRFILTER%" ( echo [ERROR] Missing: %ZDRFILTER% & pause & exit /b 1 )
set "PYEXE="
for /f "usebackq delims=" %%p in (`py -3 -c "import sys;print(sys.executable)" 2^>nul`) do set "PYEXE=%%p"
if not defined PYEXE ( echo [ERROR] Python 3 not found ^(py -3^) - the ZDR log filter needs it. Not starting. & pause & exit /b 1 )

if not exist "%ROOT%logs" mkdir "%ROOT%logs"
set "STAMP="
for /f "usebackq delims=" %%t in (`powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"`) do set "STAMP=%%t"
if "%STAMP%"=="" set "STAMP=nostamp"

set "LANIP="
if "%HOST%"=="0.0.0.0" if exist "%IPPS%" (
  for /f "usebackq delims=" %%i in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%IPPS%"`) do set "LANIP=%%i"
)
if "%LANIP%"=="" set "LANIP=[not detected - run ipconfig]"

rem --- what is installed and offered on this machine ---
set "AV_D=" & set "AV_H=" & set "AV_M=" & set "AV_Q="
set /a "SUM_D=CTX_D_STD+CTX_D_TURBO, SUM_H=CTX_H_STD+CTX_H_TURBO, SUM_Q=CTX_Q_STD+CTX_Q_TURBO"
if exist "%D_MODEL%" if !SUM_D! GTR 0 set "AV_D=1"
if exist "%H_MODEL%" if !SUM_H! GTR 0 set "AV_H=1"
if exist "%M_MODEL%" if %CTX_M% GTR 0 set "AV_M=1"
if exist "%Q_MODEL%" if !SUM_Q! GTR 0 set "AV_Q=1"
if exist "%Q3_MODEL%" if %CTX_Q3_STD% GTR 0 set "AV_Q=1"
for %%v in (D H M Q) do (
  if defined AV_%%v ( set "TAGL_%%v=" ) else ( set "TAGL_%%v=   -- not installed / not offered on this GPU" )
)

rem --- per-model settings; the Gemma values are the defaults, Qwen overrides them ---
set "BRAND=GEMMA 4"
set "LOGPFX=gemma"
set "IMGMAX=%G_IMGMAX%"
set "SAMPLER=--temp 1.0 --top-p 0.95 --top-k 64 --min-p 0.0"
set "EXTRA="

rem ==========================================================
rem  STEP 1 - pick a model
rem ==========================================================
:PICK_MODEL
cls
echo ==========================================================
echo    LOCAL LLM SERVER  -  step 1 of 2:  pick a model
echo ==========================================================
if defined CONFIGURED (
  echo    This machine: %GPU_NAME%  ^(tier %TIER%^)
) else (
  echo    No config\machine.cmd - using the RTX 5090 reference values.
  echo    On any other GPU, run onboarding first: "Onboard me" in Claude Code.
)
echo    Speeds below were measured on an RTX 5090; yours will differ.
echo.
echo     [1] GEMMA 4 31B DENSE      highest-quality Gemma!TAGL_D!
echo           decode 66-70 tok/s shallow  /  24 tok/s at 196K
echo           reads fine print in images best
echo.
echo     [2] GEMMA 4 26B-A4B MoE    ~4x faster!TAGL_M!
echo           decode 258-329 tok/s shallow with MTP  /  99 tok/s at 256K
echo           BUT weak at depth: stops calling tools and loses detail
echo           in long contexts. Best for bulk work and search under ~32K.
echo.
echo     [3] GEMMA 4 31B UNCENSORED the 31B with refusals removed!TAGL_H!
echo           matched [1] on our tests; 1-3%% slower, a bit less context
echo.
echo     [4] QWEN 3.8 27B           best on our agentic coding tests!TAGL_Q!
echo           decode 74 tok/s, 110-145 with MTP. Model id: qwen3.8-27b
echo           Recommended for Claude Code (claude-local).
echo.
choice /C 1234 /N /M "  Select a model [1/2/3/4]: "
if errorlevel 4 goto MODEL_QWEN
if errorlevel 3 goto MODEL_UNCENSORED
if errorlevel 2 goto MODEL_MOE
goto MODEL_DENSE

:NOT_AVAILABLE
echo.
echo   That model is not installed, or not offered on this GPU.
echo   To add it, ask Claude Code in this folder (e.g. "download the 31B").
echo.
pause
goto PICK_MODEL

:PROFILE_NA
echo.
echo   That profile is not offered on this GPU. Pick the other one.
pause
goto PICK_MODEL

rem ==========================================================
rem  STEP 2 - both 31B builds offer STANDARD and TURBO
rem ==========================================================
:MODEL_DENSE
if not defined AV_D goto NOT_AVAILABLE
set "MODEL=%D_MODEL%"
set "ALIAS=gemma-4-31b"
set "TAG=31B"
set "NAME=31B DENSE"
set "STD_CTX=%CTX_D_STD%"
set "TURBO_CTX=%CTX_D_TURBO%"
goto DENSE_PROFILE

:MODEL_UNCENSORED
if not defined AV_H goto NOT_AVAILABLE
set "MODEL=%H_MODEL%"
set "ALIAS=gemma-4-31b-uncensored"
set "TAG=31B-UNCENSORED"
set "NAME=31B UNCENSORED"
set "STD_CTX=%CTX_H_STD%"
set "TURBO_CTX=%CTX_H_TURBO%"
goto DENSE_PROFILE

:DENSE_PROFILE
set "MMPROJ=%D_MMPROJ%"
cls
echo ==========================================================
echo    GEMMA 4 %NAME%  -  step 2 of 2:  pick a profile
echo ==========================================================
echo.
echo     [1] STANDARD     %STD_CTX% tokens  -  slower
echo           RTX 5090: decode 66-70 tok/s shallow / 24 at full context
echo.
echo     [2] TURBO        %TURBO_CTX% tokens  -  faster, MTP enabled
echo           RTX 5090: decode 80-150 tok/s shallow / 55-58 at full context
echo.
echo     A context of 0 = not offered on this GPU.
echo     Contexts are sized to a small VRAM margin: nothing else may
echo     use this GPU while the server runs.
echo.
choice /C 12 /N /M "  Select a profile [1/2]: "
if errorlevel 2 goto D_TURBO
if %STD_CTX% LEQ 0 goto PROFILE_NA
set "CTX=%STD_CTX%"
set "PROFILE=%NAME% STANDARD"
set "SPEC="
goto LAUNCH
:D_TURBO
if %TURBO_CTX% LEQ 0 goto PROFILE_NA
if not exist "%D_MTP%" ( echo [ERROR] Missing MTP drafter: %D_MTP% & pause & exit /b 1 )
set "CTX=%TURBO_CTX%"
set "PROFILE=%NAME% TURBO (MTP)"
set SPEC=--spec-type draft-mtp -md "%D_MTP%" -ngld all
goto LAUNCH

rem ==========================================================
rem  The MoE has ONE config, deliberately: its KV is 4x smaller, so full context WITH
rem  vision AND MTP fits at once on the reference GPU. A reduced MoE profile would be
rem  worse in every dimension there.
rem ==========================================================
:MODEL_MOE
if not defined AV_M goto NOT_AVAILABLE
if not exist "%M_MTP%" ( echo [ERROR] Missing MTP drafter: %M_MTP% & pause & exit /b 1 )
set "MODEL=%M_MODEL%"
set "MMPROJ=%M_MMPROJ%"
set "ALIAS=gemma-4-26b"
set "TAG=26B"
set "CTX=%CTX_M%"
set "PROFILE=26B-A4B MoE (MTP)"
set SPEC=--spec-type draft-mtp -md "%M_MTP%" -ngld all
cls
echo ==========================================================
echo    GEMMA 4 26B-A4B MoE  -  single configuration
echo ==========================================================
echo.
echo     %CTX_M% tokens  +  vision  +  MTP
echo           RTX 5090: decode 258-329 tok/s shallow / 99 tok/s at 256K
echo.
echo     NOTE: model id is gemma-4-26b, NOT gemma-4-31b.
echo.
pause
goto LAUNCH

rem ==========================================================
rem  Qwen 3.8 27B: STANDARD or TURBO (MTP head built into the 4-bit file, so no -md).
rem  Its own sampler (top-k 20), image cap and chat template.
rem ==========================================================
:MODEL_QWEN
if not defined AV_Q goto NOT_AVAILABLE
if not exist "%Q_MMPROJ%" ( echo [ERROR] Missing: %Q_MMPROJ% & pause & exit /b 1 )
if not exist "%Q_TMPL%"   ( echo [ERROR] Missing: %Q_TMPL%   & pause & exit /b 1 )
set "MMPROJ=%Q_MMPROJ%"
set "ALIAS=qwen3.8-27b"
set "TAG=QWEN38-27B"
set "BRAND=QWEN 3.8 27B"
set "LOGPFX=qwen"
set "IMGMAX=%Q_IMGMAX%"
set "SAMPLER=--temp 1.0 --top-p 0.95 --top-k 20 --min-p 0.0"
set EXTRA=--image-min-tokens 1024 --chat-template-file "%Q_TMPL%"
rem 16 GB cards: the 3-bit file, STANDARD only.
set "Q_STD_FILE=%Q_MODEL%"
set "Q_STD_CTX=%CTX_Q_STD%"
set "Q_STD_NOTE=4-bit"
if %CTX_Q_STD% LEQ 0 if %CTX_Q3_STD% GTR 0 (
  set "Q_STD_FILE=%Q3_MODEL%"
  set "Q_STD_CTX=%CTX_Q3_STD%"
  set "Q_STD_NOTE=3-bit - UNTESTED quant, restrictive context"
)
set "Q_TURBO_CTX=%CTX_Q_TURBO%"
if not exist "%Q_MODEL%" set "Q_TURBO_CTX=0"
cls
echo ==========================================================
echo    QWEN 3.8 27B  -  step 2 of 2:  pick a profile
echo ==========================================================
echo.
echo     [1] STANDARD     !Q_STD_CTX! tokens  -  !Q_STD_NOTE!
echo           RTX 5090: decode 74 tok/s shallow / 37 at full context
echo.
echo     [2] TURBO        !Q_TURBO_CTX! tokens  -  faster, MTP enabled
echo           RTX 5090: decode 110-145 tok/s shallow / 60 at full context
echo.
echo     A context of 0 = not offered on this GPU.
echo     Running out of VRAM CRASHES Qwen instead of slowing it:
echo     nothing else may use this GPU while the server runs.
echo.
choice /C 12 /N /M "  Select a profile [1/2]: "
if errorlevel 2 goto Q_TURBO
if !Q_STD_CTX! LEQ 0 goto PROFILE_NA
if not exist "!Q_STD_FILE!" goto NOT_AVAILABLE
set "MODEL=!Q_STD_FILE!"
set "CTX=!Q_STD_CTX!"
set "PROFILE=QWEN 3.8 27B STANDARD (!Q_STD_NOTE!)"
set "SPEC="
goto LAUNCH
:Q_TURBO
if !Q_TURBO_CTX! LEQ 0 goto PROFILE_NA
set "MODEL=%Q_MODEL%"
set "CTX=!Q_TURBO_CTX!"
set "PROFILE=QWEN 3.8 27B TURBO (MTP)"
set "SPEC=--spec-type draft-mtp --spec-draft-n-max 3"
goto LAUNCH

rem ==========================================================
:LAUNCH
set "LOGFILE=%ROOT%logs\%LOGPFX%-%TAG%-%STAMP%.log"

cls
echo ==========================================================
echo    %BRAND%  -  local inference server
echo ==========================================================
echo.
echo   ON THIS MACHINE:
echo.
echo      Base URL    : http://127.0.0.1:%PORT%/v1
echo      Chat UI     : http://127.0.0.1:%PORT%
echo      Model ID    : %ALIAS%
echo      API key     : in api-key.txt
echo      Claude Code : open a NEW terminal in this folder and run  claude-local
echo.
if "%HOST%"=="0.0.0.0" (
  echo   OTHER DEVICES ON YOUR NETWORK - see CONNECT-mine.md:
  echo.
  echo      Base URL : http://!LANIP!:%PORT%/v1
  echo      API key  : !APIKEY!
  echo.
)
echo   PROFILE: %PROFILE%
echo   CONFIG: %CTX% ctx ^| %SLOTS% slots ^(unified KV^) ^| q8_0 KV ^| %CRAM% MiB RAM cache
echo.
echo   Model load takes ~10-60s. Wait for "listening on".
echo   Press Ctrl+C here to stop  ^(answer Y to "Terminate batch job"^).
echo ==========================================================
echo.

"%BIN%" -m "%MODEL%" ^
  -ngl 99 -fa on -mm "%MMPROJ%" ^
  -np %SLOTS% -kvu -c %CTX% -b 2048 -ub 2048 ^
  -ctk q8_0 -ctv q8_0 ^
  -cram %CRAM% ^
  --image-max-tokens %IMGMAX% %EXTRA% ^
  --jinja --metrics --no-slots -a %ALIAS% %SPEC% ^
  --log-prefix --log-timestamps --log-colors off ^
  %SAMPLER% ^
  --host %HOST% --port %PORT% ^
  --api-key-file "%KEYFILE%" 2>&1 | "%PYEXE%" "%ZDRFILTER%" "%LOGFILE%"

echo.
echo Server stopped.  ^(profile: %PROFILE%^)
pause
