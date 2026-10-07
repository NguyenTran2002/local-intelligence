# CLAUDE.md — Local Intelligence

## First: onboarding

If the user says **"Onboard me"** (or "set this up", "get started", anything similar), or asks to use
the project while `config\machine.cmd` does not exist yet, **run the `onboard` skill**
(`.claude/skills/onboard/SKILL.md`) and follow it step by step. The user may be a complete beginner:
plain language, one step at a time, ask before changing anything.

## What this is

Two things that share one NVIDIA GPU:

1. **A local model server** — upstream llama.cpp (`b11065`, unmodified) serving one model at a time
   through an OpenAI- and Anthropic-compatible API on `http://127.0.0.1:8080`, with vision. Four
   models: **Qwen 3.8 27B** (`qwen3.8-27b`, best for agentic coding), **Gemma 4 31B**
   (`gemma-4-31b`), the **Gemma 4 26B-A4B MoE** (`gemma-4-26b`, fast, weak at depth) and an
   **uncensored 31B** (`gemma-4-31b-uncensored`, built locally). Launcher:
   `Start-Local-LLM-Server.bat`.
2. **Claude Code pointed at it** — `claude-local.cmd` runs the user's own Claude Code CLI with a
   separate profile (`%USERPROFILE%\.claude-local`) against the server. For machines too weak to
   host the model, `claude-openrouter.cmd` does the same against OpenRouter's cloud Qwen 3.8.

**This is not an application codebase.** The deliverable is a correctly configured upstream binary
plus launcher glue. Resist writing code: llama.cpp already implements the API, and anything
hand-rolled here would be worse.

**Officially supported: Windows 11 + NVIDIA** (Turing or newer, driver 580+). Everything was
measured on **one RTX 5090 (32 GB)**; other GPUs run on estimated presets until `lib\fit-test.py`
passes on them. macOS / Linux: not supported — `EXPANSIONS.md` has head-start notes if the user
wants to port it with you.

## Layout

```
Start-Local-LLM-Server.bat     double-click: model, then profile. Ctrl+C stops it
claude-local.cmd               Claude Code -> local server   (profile %USERPROFILE%\.claude-local)
claude-openrouter.cmd          Claude Code -> OpenRouter     (profile %USERPROFILE%\.claude-openrouter)
release.json                   SINGLE SOURCE: tested versions, pinned downloads + sha256, GPU table,
                               tier thresholds, VRAM sizing constants
config\machine.cmd             this PC's contexts/host/port, written by lib\plan-config.py (git-ignored)
api-key.txt                    the server's key, created on first launch (git-ignored, never print it)
openrouter-key.txt             the user's OpenRouter key, created BY THE USER (git-ignored)
lib\hardware-check.ps1         read-only hardware survey (JSON)
lib\plan-config.py             survey -> verdict (local / OpenRouter), contexts, --write config
lib\download.py                resumable, sha256-verified downloads of release.json bundles
lib\fit-test.py                worst-case VRAM test against the running server
lib\make-profile.py            creates the claude-local / claude-openrouter profile
lib\zdr-log-filter.py          writes logs\*.log with model/user text redacted (see Privacy)
models\                        weights (git-ignored) + the uncensored build script + Qwen's patched template
llamacpp\                      llama.cpp binaries (git-ignored) + MANIFEST.md
setup-network-once-ADMIN.ps1   OPTIONAL LAN sharing: firewall rule + Private network (user runs it)
CONNECT-TEMPLATE.md            client guide for other devices; onboarding fills CONNECT-mine.md
REFERENCE.md                   how everything works, with the measurements behind it
EXPANSIONS.md                  head-start notes: Mac, Linux, remote access, bigger GPUs
```

## Rules that matter

- **Measure, don't infer.** Nearly every wrong belief in this project came from trusting a table,
  a doc or a linear extrapolation. A context size is proven only by the worst case: a max-size
  image (1920×1920 for Gemma, 2048×2048 for Qwen), then a prompt at ~99% of context
  (`lib\fit-test.py`). Boot VRAM and small-image probes both miss ~1 GB.
- **VRAM overflow is silent.** Past usable VRAM, Windows' CUDA sysmem fallback moves the overflow
  into system RAM: prefill drops ~7× (1,200 → 175 tok/s), **no error, no log line**. Qwen instead
  **crashes** on the next image. A spill looks like a slow server, not a broken one.
- **Anything else on the GPU changes the numbers** — including a monitor plugged into it. Recommend
  the integrated GPU for the desktop when one exists.
- **Never raise a context** in `config\machine.cmd` without re-running the fit test.
- **Kill a stray server first:** `taskkill /IM llama-server.exe /F` before starting another — a
  leftover instance holds most of the VRAM and the next boot fails or silently shrinks.
- **`max_tokens` must be generous** (≥ 2,000 for a smoke test): thinking is on, and a small budget is
  consumed entirely by reasoning, returning **empty** `content`.
- **Never put server URLs, keys or model names in `~/.claude/settings.json`** — that config is the
  user's normal Claude Code (and desktop app). The wrappers set everything per process, in their
  own profile folders. The one exception onboarding may make there, with consent:
  `autoUpdatesChannel: "stable"`.
- **Do not start `claude-local` / `claude-openrouter` interactively from inside a session.** The
  user runs them in a new terminal; a headless `-p` smoke test is fine with consent.
- **Versions are pinned:** llama.cpp `b11065`, Claude Code `release.json → tested.claude_code` on
  the **stable** channel. Any other Claude Code version: "will most likely work, but is NOT
  tested" — say it, don't hide it.
- **Read flags from `llamacpp\bin\llama-server.exe --help`**, not memory — names churn.
- Long downloads and tests: make them resumable; `lib\download.py` already is.

## Flags that fail silently — or fatally (in the launcher; don't change without re-measuring)

| Flag | If you get it wrong |
|---|---|
| `-np 2 -kvu` | Without `-kvu`, unified KV turns off and context **halves** |
| `-c <explicit>` | Default `0` = the model's maximum (262,144) — tries to allocate it all |
| `--temp 1.0 --top-p 0.95 --top-k 64` (Gemma) / `--top-k 20` (Qwen), `--min-p 0.0` | Binary defaults (0.8 / 40 / 0.05) differ from the vendors' references |
| no `--swa-full` | Enabling it caps Gemma near **26K** context |
| CUDA **13.4** build | The CUDA 12.4 build has **no Blackwell (sm_120) kernels** |
| Gemma `--image-max-tokens` ≤ `-ub` | Violating it **aborts the whole server** on the first image |
| `-ub 2048` (a power of two) | `-ub 2560` collapsed prefill to ~206 tok/s |
| `-ctk/-ctv q8_0` | Measured free in quality; f16 roughly halves the context |
| `-lv` stays at 3 | 4/5 write prompt content into the log |
| logs via the ZDR filter, not `--log-file` | `--log-file` stores model output echoed into warnings |
| Qwen: `--chat-template-file` the patched one | The embedded template returns HTTP 500 on a late system message — and the conversation stays broken |
| Qwen: `--image-min-tokens 1024` | Default 8 → small images encoded with a handful of tokens and misread |
| Qwen: never `-ctkd/-ctvd` | Out of memory at boot |
| paths with spaces | Always pass model/drafter paths as one quoted argument |

## Privacy (ZDR)

Nothing leaves the machine when serving locally. KV cache and prompt cache live in RAM/VRAM only;
`--slot-save-path` and `--log-prompts-dir` are unset; `--no-slots` hides other clients' prompts.
llama-server still echoes model output and client input into *warnings* at every verbosity, so the
launcher pipes its output through `lib\zdr-log-filter.py`: the console shows everything, the log
file keeps metadata only. No Python → the launcher refuses to start rather than log unfiltered.
Exceptions the user opts into: **Exa web search** (search queries go to Exa) and **OpenRouter**
(everything goes to OpenRouter and its providers).

## Design decisions (don't undo casually; each has a measured reason in REFERENCE.md)

- **Qwen 3.8 for Claude Code; the MoE never for agentic depth** — the MoE stops calling tools
  (2/8 at 108K) and reconstructs long code far worse; Qwen measured best on every coding test.
- **Thinking always on**, no server-wide thinking cap; clients may cap per request.
- **Small VRAM margins on the reference GPU** (74–166 MiB), because it ran with nothing else on it.
  Other GPUs get a 512 MiB margin until fit-tested.
- **One model at a time, manual start/stop.** Context is fixed at process start; "switching" is a
  restart.
- **Bound to 127.0.0.1 by default**; LAN sharing is opt-in (`--lan`).
- **The uncensored model is its own model id**, never swapped in under `gemma-4-31b`.
- **Claude Code's WebSearch is denied in the profiles** (it cannot work against another endpoint;
  measured runaways and one fabricated answer); Exa replaces it when the user opts in.
