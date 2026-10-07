---
name: onboard
description: Set up Local Intelligence on this computer from scratch - check the hardware, recommend local hosting or OpenRouter, download and configure the model server, and create the claude-local / claude-openrouter Claude Code profile. Use when the user says "Onboard me", "set this up", "get started", or anything similar, or when config\machine.cmd does not exist yet and the user wants to use the project.
---

# Onboarding

You are onboarding someone who may never have used a terminal, a GPU server or a local model.
Your job: get them from a fresh clone to a working setup, explaining each step in plain words.

## Ground rules (read first, follow throughout)

- **Plain language, one step at a time.** Before each step, say in one or two sentences what it does
  and why. Avoid jargon; when you must use a term (VRAM, context, quantization), explain it once.
- **Ask before anything that changes the machine**: downloads (say file names and sizes), installing
  software, changing settings files, editing PATH, starting the server, running the fit test.
  Use AskUserQuestion for real choices. Read-only checks need no permission.
- **Secrets.** Never print `api-key.txt`. Never ask the user to paste an OpenRouter key into the chat:
  they put it into `openrouter-key.txt` themselves. You never create accounts or enter passwords.
- **System settings are the user's.** Firewall, network profile, NVIDIA Control Panel, BIOS: explain
  and let them do it (or run the provided script only after they agree).
- **Never start `claude-local` / `claude-openrouter` as an interactive session from inside this
  session.** The user runs them in a new terminal. A one-shot headless smoke test is fine *if the
  user agrees* (step 9).
- **Be honest about what is tested.** Everything was measured on one RTX 5090 with Claude Code
  `release.json → tested.claude_code`. Every other GPU's numbers are estimates until the fit test
  passes on it. Say so; never present an estimate as measured.
- **Official support is Windows + NVIDIA.** On macOS or Linux: say so plainly, then offer the cloud
  path (step 10) or, if the user wants to experiment, read `EXPANSIONS.md` with them - you can
  pilot a port together, but it is theirs, not supported by this project.
- Commands below are PowerShell. If your shell is Git Bash, use the same commands with `/` paths,
  or run them via `powershell -NoProfile -Command "..."`.
- If onboarding was done before (`config\machine.cmd` exists, profiles exist), say what is already
  set up and ask what they want to change instead of starting over.

Start with a short welcome: what Local Intelligence is (a private AI model server on their own GPU,
plus Claude Code pointed at it), that onboarding takes ~10 minutes of questions plus download time
(12-75 GB depending on choices), and that nothing changes without their OK.

## Step 1 - Python (needed by every path)

Check: `py -3 --version`. If missing, explain that the server's privacy log filter and these setup
scripts need Python, and offer to install it:
`winget install -e --id Python.Python.3.12` (ask first). If `py` is still not found afterwards, the
shell has an old PATH: look for `%LOCALAPPDATA%\Programs\Python\Launcher\py.exe` or
`C:\Windows\py.exe`, or ask the user to restart Claude Code in this folder.

## Step 2 - Claude Code version and the stable channel

1. `claude --version` → compare with `tested.claude_code` in `release.json`.
2. Explain: Claude Code has two update channels. **latest** gets every release; **stable** is about a
   week behind and skips releases with known regressions. This project is pinned to **stable**, and
   was tested with exactly `tested.claude_code`.
3. The `claude-local` / `claude-openrouter` profiles are created with `autoUpdatesChannel: "stable"`
   (step 9). But the `claude` program itself is **shared by every profile** on this PC, so their main
   Claude Code's channel decides which version gets installed. Read
   `%USERPROFILE%\.claude\settings.json` and report its `autoUpdatesChannel` (missing = latest).
4. If it is not `stable`, ask whether to switch their main Claude Code to stable too. Two ways:
   - they type `/config` → *Auto-update channel* → *stable* themselves (it asks whether to stay on
     the current version or move back to stable - either is fine); or
   - you add `"autoUpdatesChannel": "stable"` to that settings file (merge, keep every other key;
     back it up first). Add `"minimumVersion": "<their current version>"` only if they want to stay
     on their current version until stable catches up.
   Do not touch anything else in `~/.claude`. Never put server URLs or keys there.
5. If the installed version differs from the tested one, tell them clearly: **"this version of
   Claude Code will most likely work, but it is NOT tested with this project."** The launchers print
   the same warning every time. If they want the exact tested version, the official installer takes
   a version: `& ([scriptblock]::Create((irm https://claude.ai/install.ps1))) <version>` - their
   call; show it, don't run it unasked.

## Step 3 - Hardware check

Run `py -3 lib\plan-config.py` (read-only: it runs `lib\hardware-check.ps1` and prints a JSON
verdict). Summarise for the user: GPU, VRAM, driver, whether the desktop is drawing on the NVIDIA
GPU, integrated GPU present or not, RAM, free disk space.

- `verdict: need-bandwidth` → the GPU is not in `release.json → gpus`. Look up its memory
  bandwidth (GB/s) from the vendor's spec page, confirm with the user, re-run with
  `--bandwidth <GB/s>`.
- Several NVIDIA GPUs → the planner picks the one with most VRAM; multi-GPU is not supported (see
  `EXPANSIONS.md`). Offer `--gpu N` if they want another.
- `llama_server_running: true` → a server is up and its VRAM counts as "in use". Ask them to stop it
  (Ctrl+C in its window) and re-run.

## Step 4 - The verdict: local or cloud

The rule (from `release.json → thresholds`): local hosting is recommended only with **at least the
16 GB class of VRAM AND at least 896 GB/s of memory bandwidth** (half of the RTX 5090 this was built
on). Below either → recommend OpenRouter.

- **openrouter**: explain *why* using the planner's reasons, in plain words. For a GPU that is
  decent but under the bar, be explicit: *we recommend the cloud because locally you would not get
  enough context for a coding session (Claude Code needs ~64K tokens; it compacts at context − 33K),
  or speeds anywhere near the normal Claude Code experience.* Then go to step 10. If they insist on
  trying locally anyway, it is their machine: explain that nothing here is sized or tested for it,
  and that you would be improvising together.
- **fix-then-local**: usually an old NVIDIA driver (the CUDA 13 build needs 580+). Tell them to
  update it from NVIDIA's site or the NVIDIA app, then re-run step 3.
- **local**: continue. Tier `32gb` = the reference setup; `24gb` and `16gb` = estimated presets.

**Free VRAM is context.** If the planner notes the desktop is using the GPU and an integrated GPU
exists, recommend plugging the monitor into the motherboard's video port (may need "iGPU" / "IGD
multi-monitor" enabled in the BIOS) - it gives that VRAM back. Also: close GPU-hungry apps
(browsers with hardware acceleration, games, video tools, RGB/wallpaper apps) before serving.
Offer to re-run step 3 after any change.

## Step 5 - Choose models and write the config

Explain the options the planner offered, with their contexts and status (measured vs ESTIMATE):

| Model | Best for | Notes |
|---|---|---|
| **Qwen 3.8 27B** (`qwen3.8-27b`) | **Claude Code / agentic coding** - best on our tests | recommend this first. 16 GB cards: 3-bit, UNTESTED, restrictive context - say so |
| Gemma 4 31B (`gemma-4-31b`) | chat, writing, reading fine print in images | on 24 GB only ~40K context: chat, not coding sessions |
| Gemma 4 26B MoE (`gemma-4-26b`) | very fast bulk work, search in short documents | weak at depth: stops calling tools in long sessions. Not for Claude Code |
| Gemma 4 31B uncensored | the 31B with refusals removed | 32 GB tier only; built locally (step 6) |

STANDARD = more context; TURBO = faster (speculative decoding, "MTP") with less context. A context
of 0 means "not offered on this GPU".

Ask: which models (default: Qwen only), and whether other devices on their home network should be
able to use the server (default: no - this computer only). Then write the config:
`py -3 lib\plan-config.py --write` (add `--lan` for network sharing). Show them the file
`config\machine.cmd` it wrote and what it means.

## Step 6 - Downloads

`py -3 lib\download.py --list` shows each bundle's size. Needed: `llamacpp` (0.6 GB, the server
program) plus one bundle per chosen model:

| Bundle | Size | For |
|---|---|---|
| `qwen-q4` | 18.5 GB | Qwen on 24 GB+ |
| `qwen-q3` | 11.9 GB | Qwen on 16 GB (UNTESTED quant) |
| `gemma-31b` | 18.8 GB | Gemma 31B (and the base for the uncensored build) |
| `gemma-26b` | 15.7 GB | the MoE |

Check free disk space against the total (plus ~10% slack), tell them the total, ask, then run
`py -3 lib\download.py llamacpp <bundles...>` in the background and report progress now and then.
Downloads resume if interrupted (just run the same command again) and every file is checked against
a pinned sha256. Files come from GitHub (llama.cpp) and Hugging Face (models) at fixed revisions.

**Uncensored build** (only if chosen; needs `gemma-31b` first): explain it is an abliteration
(refusal behaviour edited out of the weights), built here from two public inputs; it fetches ~2.7 GB
more. Needs numpy (`py -3 -m pip install numpy`, ask) and `curl` (built into Windows). Run:
`py -3 models\gemma-4-31B-it-qat-heretic\build-heretic-gguf.py models\gemma-4-31B-it-qat\gemma-4-31B-it-qat-UD-Q4_K_XL.gguf models\gemma-4-31B-it-qat-heretic\gemma-4-31B-it-qat-heretic-Q4_0-attnQ8_0.gguf`
It verifies its output's sha256 itself.

## Step 7 - First start and smoke test

Explain how they will normally run it: **double-click `Start-Local-LLM-Server.bat`**, pick a model
and profile; it creates `api-key.txt` (a random password for the server) on first run; Ctrl+C stops it.

For the first check, ask whether you may start it yourself. If yes, start it **in the background**
by piping the menu keys into it, e.g. Qwen STANDARD (verified form, from Git Bash):
`printf '4\n1\n' | powershell -NoProfile -Command "& '<full path to this folder>\Start-Local-LLM-Server.bat'"`
From PowerShell the equivalent is `"4`n1`n" | powershell -NoProfile -Command "& '<full path>\Start-Local-LLM-Server.bat'"`.
Model keys: 1 = 31B, 2 = MoE, 3 = uncensored, 4 = Qwen; then profile 1 = STANDARD, 2 = TURBO (the
MoE has no profile step - send one extra newline for its pause instead). Then poll `http://127.0.0.1:8080/health` until it answers (loading takes
10-60 s), read `/props` (model alias, `n_ctx`) and send one chat with a generous `max_tokens`
(thinking is on: a small budget returns empty content):

```powershell
$k = (Get-Content api-key.txt -Raw).Trim()
Invoke-RestMethod http://127.0.0.1:8080/v1/chat/completions -Method Post -ContentType 'application/json' `
  -Headers @{Authorization = "Bearer $k"} `
  -Body '{"model":"qwen3.8-27b","messages":[{"role":"user","content":"Say hello in five words."}],"max_tokens":2000}'
```

Stop it afterwards with `taskkill /IM llama-server.exe /F` (always do this before starting another).

## Step 8 - Fit test (only with a green light)

If any chosen profile's status is ESTIMATE, explain: *the context sizes for your GPU are calculated,
not measured. Too large, and the server silently slows to a crawl (Gemma) or crashes on an image
(Qwen). A short test proves the size: it fills the context to ~99% and sends the largest images.*
Say it takes ~2-10 minutes per profile and uses the GPU fully. **Ask before running it.**

For each profile they will actually use: start the server with that profile (step 7), run
`py -3 lib\fit-test.py`, stop the server.
- **PASS** → update that profile's `_NOTE` line in `config\machine.cmd` to `fit test passed <date>`.
- **SPILL / CRASH** → lower that profile's `CTX_...` value by 4096 (8192 if it crashed), then ask
  before retesting. Repeat until it passes. If it ends below 65536 on the profile meant for Claude
  Code, tell them coding sessions will be cramped and suggest the iGPU fix or the cloud.
- If they decline the test: keep the estimates, and tell them the signs of a too-large context
  (sudden extreme slowness on long conversations; Qwen server closing after an image) and that you
  can run the test any time. Offer more testing if anything looks off later.

## Step 9 - Claude Code profile (`claude-local`)

1. **Permission mode** - ask with AskUserQuestion, bypass first (the project default):
   - **Bypass (recommended by this project):** Claude works without stopping to ask - noticeably
     faster sessions - but it can run any command and edit any file without asking. Use it in
     folders that are backed up or in git.
   - **Ask first (Claude Code's normal mode):** Claude asks before commands and edits - safer, but
     every step waits for your click, so sessions are slower. Locally there is no bill either way.
     (On OpenRouter, not bypassing can mean extra calls and a somewhat higher bill.)
2. **Web search** - ask: *Claude Code's built-in web search only works with Anthropic's servers, so
   it is switched off here. Optionally, searches can go through Exa, a third-party search service
   (free, no account). Your files never go to Exa, but every search query does - that part is not
   private. Without it, Claude can still open specific web pages, just not search.*
3. Create it: `py -3 lib\make-profile.py local --mode bypass|default [--exa]`. It writes only
   `%USERPROFILE%\.claude-local` (backs up an existing settings file first).
4. Offer to add this folder to their user PATH so `claude-local` works from any folder
   (ask first; it is a persistent setting):
   `[Environment]::SetEnvironmentVariable('Path', [Environment]::GetEnvironmentVariable('Path','User') + ';' + (Get-Location).Path, 'User')`
   Terminals opened before this won't see it.
5. Explain how to use it: start the server, then in a **new** terminal run `claude-local` in any
   project folder. It reads the model and context from the running server, so restart
   `claude-local` after switching models. Plain `claude` stays their normal Claude Code.
6. Optional headless smoke test, if they agree and the server is running:
   `.\claude-local.cmd -p "Reply with the single word: ready" --permission-mode default`

## Step 10 - The cloud path (`claude-openrouter`) - instead of steps 5-9

1. Explain OpenRouter: a service that runs open models in the cloud and bills per token (prepaid
   credits). The model is the same Qwen 3.8 27B, with full 262K context. Prices change - send them to
   `https://openrouter.ai/qwen/qwen3.8-27b` to see current ones. Say it plainly: **this path is not
   tested by this project**, and OpenRouter only guarantees Claude Code with Anthropic's own models.
2. They create an account and an API key at `https://openrouter.ai/keys` themselves, and save the
   key into `openrouter-key.txt` in this folder (Notepad is fine). Not in the chat. Wait until they
   say it's done; check the file exists (don't print it).
3. Suggest excluding providers that serve this model without tool calling or with a short context
   (at the time of writing: Cerebras) in their OpenRouter account's provider settings.
4. Permission mode and web search: same questions as step 9 (for the bill note, the OpenRouter line
   now applies). Then `py -3 lib\make-profile.py openrouter --mode ... [--exa]`, and the PATH offer.
5. Optional smoke test (costs a fraction of a cent):
   `.\claude-openrouter.cmd -p "Reply with the single word: ready" --permission-mode default`

## Step 11 - Optional: share with other devices on the home network

Only if they chose it in step 5. Explain the two Windows changes `setup-network-once-ADMIN.ps1`
makes (network marked Private; firewall rule for port 8080, local subnet only) - they run it
themselves, as Administrator. Then create `CONNECT-mine.md` (git-ignored) from
`CONNECT-TEMPLATE.md`, filling `<SERVER_IP>` (from `lib\get-lan-ip.ps1`), `<PORT>`, `<MODEL_ID>`
and `<API_KEY>` (read from `api-key.txt` into the file only - don't echo it in the chat). Tell them
that file contains their server password: share it only with their own devices.

## Step 12 - Summary card

Finish with a short, scannable summary:
- what is installed and where (models, profiles, config), and disk space used;
- how to start / stop the server, and how to start `claude-local` or `claude-openrouter`;
- their contexts and which are **measured / fit-tested / still estimates**;
- the Claude Code version note (tested vs installed, channel);
- what is untested on their machine, and that they can ask Claude in this folder any time
  ("change my config", "run the fit test", "add the 31B", "why is it slow?");
- where to read more: `README.md`, `REFERENCE.md` (how everything works), `EXPANSIONS.md` (ideas).
