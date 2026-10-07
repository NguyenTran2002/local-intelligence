# Reference — how Local Intelligence works, and what was measured

Everything here was measured on **one machine**: an RTX 5090 (32 GB, 1,792 GB/s) on Windows 11, with
the desktop on the CPU's integrated GPU and nothing else on the 5090; llama.cpp `b11065` (CUDA 13.4
build); Claude Code `2.1.285`. Figures for any other GPU are estimates until `lib\fit-test.py`
passes there. "Our coding tests" = agentic and long-context tests built on an unseen public Python
codebase (~1.8 MB, published after the models' training data was likely frozen), with synthetic git
histories for the long-context reconstruction cases.

---

## 1. The models

| | Qwen 3.8 27B | Gemma 4 31B | Gemma 4 31B uncensored | Gemma 4 26B-A4B MoE |
|---|---|---|---|---|
| Model id | `qwen3.8-27b` | `gemma-4-31b` | `gemma-4-31b-uncensored` | `gemma-4-26b` |
| File | Unsloth UD-Q4_K_XL (17.6 GB); UD-IQ3_XXS (10.9 GB) on 16 GB cards | Unsloth QAT UD-Q4_K_XL (17.3 GB) | built locally (18.0 GB) | Unsloth QAT UD-Q4_K_XL (14.2 GB) |
| Tool calls at depth (0–~110K tokens) | **40/40** | 33/40 | 39/40 | 34/40 |
| Long-code reconstruction, exact (27 cases, 58K–187K) | **22/27** | 5/27 | 6/27 | 0/27 |
| Vision battery (7 images) | 7/7 | 7/7 | 7/7 | 7/7 |
| Claude Code long session (20–25 turns) | **24/24** | 18/22 | — | not for agentic work |
| Ultracode workflows | **2/2** | 0/3 | — | — |

**Pick Qwen for Claude Code.** Gemma 31B reads fine print in images best and writes well; the MoE is
~4× faster and exact for search under ~32K, but **stops calling tools at depth** (2/8 at 108K in an
earlier battery — a silent stall, not an error) and its long-context reconstruction collapses. Its
full-precision weights did no better, so that is the model, not the quantization.

**Quantization notes.** Unsloth's UD-Q4_K_XL of the 31B measured *better* than Google's own q4_0
(perplexity 5.45; KL divergence from full weights 0.0072 vs the MoE's 0.069). Qwen's Q5_K_XL halved
the KL divergence to BF16 but tied Q4 on every task test (reconstruction 22/27 each, tool calls
40/40 each), at ~8% less speed and ~57K less context — so Q4 ships. **Qwen's 3-bit UD-IQ3_XXS
(16 GB cards) has never been measured here.**

## 2. Profiles and speed (RTX 5090)

| | Context | MTP | Decode shallow | Decode at full context | Prefill shallow / full | Worst-case VRAM peak |
|---|---|---|---|---|---|---|
| 31B STANDARD | 200,704 | off | 66 tok/s | 24 | ~3,400 / 1,212 | 32,104 MiB |
| 31B TURBO | 153,600 | on | 80 (prose) – 149 (repetitive) | 58 | ~2,950 / 1,417 | 32,012 |
| Uncensored STANDARD | 188,416 | off | ~64 | 24 | ~3,400 / 1,267 | 32,102 |
| Uncensored TURBO | 144,384 | on | 151 | 55 | ~2,950 / 1,473 | 32,066 |
| MoE (single profile) | 262,144 | on | 258 | 99 | 16,600 / 3,731 | ~24,450 |
| Qwen STANDARD | 262,144 | off | 75 | 37 | ~3,300 / 1,292 | 31,210 (even with 16K-token images) |
| Qwen TURBO | 245,760 | on (built-in head, n-max 3) | 110 (thinking) – 145 | 60 | ~3,300 / 1,262 | 32,066 |

Decode speed is bound by memory bandwidth, so a GPU with half the bandwidth decodes roughly half as
fast. **TURBO** uses speculative decoding (MTP): a small drafter proposes tokens the model verifies.
It is distribution-exact (same outputs, statistically), only faster; it costs ~2 GB of VRAM, which
is why TURBO has less context. Acceptance: 31B 0.74 shallow → ~0.55 at depth; Qwen 0.71 flat; the
drafters work above their declared 131,072 context (verified to ~150K / 190K).

## 3. VRAM — how contexts are sized

- **Usable VRAM ends ~430 MiB below the total** (32,178 of 32,607 MiB on the 5090).
- **Past it, Windows spills silently**: CUDA sysmem fallback moves the overflow to system RAM —
  prefill 1,200 → 175 tok/s, no error, no log line. **Qwen TURBO crashes instead** (`CUDA error:
  the resource allocation failed` on the next image: the vision encoder's one-shot allocation is
  refused). If a loud crash is preferred over a silent slowdown: NVIDIA Control Panel → *CUDA –
  Sysmem Fallback Policy* → *Prefer No Sysmem Fallback* (a system setting; the user's call).
- **The worst case is a max-size image.** Every config grows ~1,100 MiB (Gemma) the first time a
  full-cap image goes through the encoder. The max-size image is *square*: 1920×1920 hits Gemma's
  1,600-token cap exactly; a 4096×2560 photo stops at 1,559 tokens and understates the peak ~35 MiB.
  Qwen: 2048×2048 = 4,096 tokens; its encoder buffer is 206 / 222 / 528 / 1,180 / 2,478 MiB at caps
  1,600 / 2,048 / 4,096 / 8,192 / 16,384.
- **Cost per 1,024 tokens of context** (q8_0 KV): Gemma 31B 54.5 MiB STANDARD, 66.5 TURBO (the drafter's
  buffers scale too — using STANDARD's slope for TURBO predicted a size that spilled); Qwen 41.6 MiB
  STANDARD, ~50 TURBO. MoE KV is 4× smaller per token (10,880 vs 43,520 bytes).
- **Sizing formula** (`lib\plan-config.py`, constants in `release.json → sizing`):
  `context = (total − 429 − VRAM already in use − fixed − 512 margin) / slope × 1024`, floored to a
  multiple of 4,096. `fixed` includes weights, vision tower, compute buffers and the max-image growth.
  Straight-line projections were off by >2 GB twice during this project — hence the fit test.
- **Anything else on the GPU breaks these numbers**, including a monitor plugged into it (~0.5–2 GB).
- Earlier "free at peak" figures in this project's history were wrong because they were computed
  against the total instead of the usable ceiling. Margins on the reference GPU: 74–166 MiB.

## 4. Vision

- The vision tower is a separate file (`mmproj-F16.gguf`); the model files contain no vision
  tensors. **Each model's mmproj is different despite the same file name** (projection dims 5376 /
  2816 / 5120 for 31B / MoE / Qwen) — pairing the wrong one is silently wrong, which is why each
  model lives in its own folder.
- **Gemma: 1 token ≈ 48×48 px** → tokens ≈ width × height / 2304, capped at **1,600** (~3.7 MP).
  That is above Gemma 4's documented 1,120 and measurably better: smallest digits in a 10.5 MP image
  read 10/30 at 1,120, 21/30 at 1,600, 24/30 at 2,048 (the most `-ub 2048` allows). Oversized images
  are **downscaled, never cropped**. Above ~4 MP there is nothing to gain: resize to ~2,500 px.
- **Qwen: 1 token ≈ 32×32 px**, capped at **4,096** (~4.2 MP); small images are upscaled to ≥1,024
  tokens (without it a legible digit image was misread). Gemma reads fine print better than Qwen.
- Formats: JPEG, PNG, BMP, GIF, TGA **and WEBP**; the format is sniffed from the bytes, the `data:`
  MIME label is ignored.
- **Images per conversation are limited only by context** (30 max-size images verified on every
  model: VRAM flat, only the new image processed each turn) — **and by request size**: bodies above
  a compile-time limit return **HTTP 413** (a 168 MB request failed). Clients resend every image
  each turn, so use resized JPEG/WEBP, not photo-sized PNGs.

## 5. Thinking

- **Always on by default.** Off per request: `"chat_template_kwargs": {"enable_thinking": false}` or
  the more portable `"reasoning_effort": "none"`. Flipping it **invalidates the whole prompt
  cache** (the template branches right after the first token) — pick one per conversation.
- Gemma: `low`/`medium`/`high` are indistinguishable; unknown strings are accepted with thinking on.
  **Qwen: levels are prompt text** — `low` / `medium` / `high`(=`xhigh`) / `xhigh` (default) work,
  `none` turns thinking off, **any other value → HTTP 500**.
- **`max_tokens` must be generous**: a small budget is consumed entirely by reasoning and returns
  empty `content` (measured: empty at 64 tokens 5/5, never at 256+ on a trivial question).
- **Runaway thinking at depth:** past ~64K tokens of context, about 1 Gemma request in 12 reasons
  until `max_tokens` runs out. Per-request cap: `thinking_budget_tokens` (alias
  `reasoning_budget_tokens`), e.g. 4,096 removed every runaway. `0` is *not* "off" (models then
  reason in `content`). A server-wide `--reasoning-budget N` exists but is deliberately not set.

## 6. Sampling

The launcher matches each vendor's reference: Gemma `--temp 1.0 --top-p 0.95 --top-k 64 --min-p
0.0`; Qwen `--top-k 20` with the rest equal (Qwen advises temp 0.7 / top-p 0.8 / presence 1.5 per
request for non-thinking use). Client traps (all return 200, none warn):

| Parameter | Behaviour |
|---|---|
| `repetition_penalty` | **Ignored** — not a llama.cpp name. Use `repeat_penalty` |
| `frequency_penalty` | Works at normal OpenAI magnitudes |
| `presence_penalty` | Inert across −2…2 (a flat offset); needs ~±20 |
| `seed` | Honoured but not bit-exact |

## 7. Qwen 3.8 specifics

- Hybrid architecture (16 full-attention + 48 recurrent layers), native vision, one built-in MTP
  layer. **Prompt caching works** via checkpoints: each agent step processes only the new tokens;
  clients that send `reasoning_content` back get the best reuse.
- **Patched chat template** (`models\qwen3.8-27B\qwen3.8-chat-template-patched.jinja`): the embedded
  one raises on any system/developer message after the first turn (HTTP 500, and every later request
  in that conversation fails). One line now renders it in place; normal conversations render
  byte-identically (24/24 verified).
- Censorship in the weights on some politically sensitive history (refuses or gives the official
  line through the bare API); the long Claude Code system prompt shifted that on the one topic
  tested. Other topics untested.

## 8. The uncensored 31B

An abliteration (llmfan46's "Heretic" ARA edit) of the QAT 31B, **built here** rather than
downloaded: the Unsloth file with only the 26 edited `attn_output` tensors (layers 10–35) swapped in
at Q8_0; everything else, including the current chat template, is Unsloth's byte for byte. Why not
the upstream GGUF: it is Google's naive q4_0 plus the edits, 4-bit rounding erases the edit in 10 of
26 layers, and it carries an older chat template that does not reopen thinking after a tool result.

Measured against the standard 31B: tool calls at depth 39/40 vs 33/40, reconstruction level,
vision 7/7, decode 1–3% slower, costs 651 MiB (hence the smaller contexts). Over-refusal on 250
benign-but-alarming prompts: 0 vs 1 (the stock model barely over-refuses anyway); mainly it drops
hedging (41 → 28 replies with disclaimers). Harmful-prompt refusal rate was **not** measured here.
`build-heretic-gguf.py` reproduces the reference file exactly (sha256 checked).

## 9. Claude Code on the server (`claude-local`)

**What the wrapper sets, for its own process only:** `CLAUDE_CONFIG_DIR` (its own profile),
`ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN` (the server and key), every model slot
(`ANTHROPIC_MODEL`, `ANTHROPIC_DEFAULT_{FABLE,OPUS,SONNET,HAIKU}_MODEL`,
`CLAUDE_CODE_SUBAGENT_MODEL`) → the loaded alias, `CLAUDE_CODE_MAX_CONTEXT_TOKENS` = the server's
context, `CLAUDE_CODE_ATTRIBUTION_HEADER=0` (a per-turn block that would break caching),
`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` (no telemetry or update checks from this profile).

**Profile settings** (`lib\make-profile.py`): `autoUpdatesChannel: stable`; `permissions.deny:
["WebSearch"]`; `skipWebFetchPreflight: true`; the chosen permission mode; optionally Exa.

**How it works:** llama.cpp has native `/v1/messages` (Anthropic format). Claude Code's fixed prompt
(system + tools) is ~16–17K tokens, plus any project `CLAUDE.md`. Prefix caching works: each agent
step re-processes only appended tokens.

**Effort and thinking:** `/effort` levels change nothing (the server ignores the field) — each model
always reasons at its highest level, uncapped except by Claude Code's 32,000 `max_tokens`.
Ultracode is client-side and works (on Qwen).

**Auto-compaction** triggers at `context − 33,000` (Claude Code's fixed buffer). Measured: 6/6 notes
recalled after compaction on both models; a compaction costs one slow turn (~1–2.5 min). **Below
~64K of context, Claude Code sessions are cramped** (system prompt + buffer eat most of it).

**Measured results** (headless and interactive):

| | Qwen 3.8 TURBO | Gemma 31B TURBO |
|---|---|---|
| Long session, 10 planted bugs + feature + refactor | **24/24** turns | 18/22 (coding 13/13, read probes 1/4) |
| 3 parallel subagents, then fixes | 3/3 | 3/3 |
| Ultracode workflow | **2/2** | 0/3 |
| Plan mode / AskUserQuestion | pass / pass | headless plan mode loops / asks in plain text |
| Images via Read, NotebookEdit, /code-review | pass | pass |
| Runaways / stalls / server errors | 0 / 0 / 0 | 0 / 0 / 0 |

**Bypass vs Claude Code's auto mode:** auto mode's safety classifier runs on the same model before
every command — a separate ~30K-token request, ~10 s each; one task took 62 s in auto mode and 12 s
in bypass. On OpenRouter those extra requests are billed.

**Web:**
- **WebSearch cannot work** off Anthropic's servers: empty results; Qwen burned 3–5 min on runaway
  generations, Gemma once invented a "cited" answer. Hence denied.
- **WebFetch works** (the page is fetched locally and summarised by the local model) — but unless
  `skipWebFetchPreflight` is set, each new hostname is first sent to `api.anthropic.com` for a
  blocklist check.
- **Exa's hosted MCP search** (`https://mcp.exa.ai/mcp?tools=web_search_exa`, keyless, search tool
  only): Qwen 3/3, Gemma 2/3 + 1 stale-but-faithful. **Search queries go to Exa — not private.** Its
  index can lag about a day on fast-moving pages.

**Limits:**
- **Two slots share one KV pool of `context` tokens.** When the main session plus a subagent exceed
  it, the idle one loses its cache silently (next step re-reads everything: ~70 s at 115K on Gemma,
  ~130 s at 190K on Qwen); two requests overflowing *at the same moment* both get HTTP 500. More
  agents than slots simply queue.
- A single huge paste (~200K tokens) can be refused by Claude Code itself before reaching the server.
- Cosmetic: `[claude-code:unrecognized_model]` on stderr; a made-up `costUSD` (nothing is billed
  locally).
- In bypass mode agents can read and change anything — use it in git-backed or disposable folders.

## 10. OpenRouter (`claude-openrouter`) — not tested by this project

Follows OpenRouter's official Claude Code guide: `ANTHROPIC_BASE_URL=https://openrouter.ai/api`,
the OpenRouter key as `ANTHROPIC_AUTH_TOKEN`, no Anthropic API key, model `qwen/qwen3.8-27b`.
OpenRouter only guarantees Claude Code with Anthropic's own models. Providers differ in context
length and tool support (one served 65,536 tokens without tool calling) — exclude such providers in
your OpenRouter settings. Billed per token; prices change.

## 11. Privacy details

- KV cache, `-cram` prompt cache and slot state live in RAM/VRAM only; `--slot-save-path` and
  `--log-prompts-dir` are unset; `--no-slots` stops other LAN clients reading in-flight prompts.
- `lib\zdr-log-filter.py`: llama-server echoes model output and client input into *warnings*
  (a tool call that fails to parse, output that misses the expected format, an invalid
  `tool_choice`) — no flag stops it. The filter shows everything on the console and writes the log
  with normal lines byte-identical, every warning/error cut to its source tag plus
  `[redacted by zdr-log-filter]`, unprefixed lines counted, and any line over 256 bytes reduced to
  its tag. Clean an old log: `py -3 lib\zdr-log-filter.py --rewrite [--dry-run] <log>`.
- `-lv 4`/`5` write request content at info/debug level, which the filter does not reliably catch.
  Use them only for deliberate debugging, then clean the log.
- The built-in web UI keeps chat history in the browser's localStorage (outside the server's
  control).

## 12. Known unknowns

1. Every GPU other than the RTX 5090 (all presets for 16/24 GB and 48 GB+ are estimates).
2. Qwen 3.8 at 3-bit (UD-IQ3_XXS) — quality and fit.
3. The OpenRouter path end to end.
4. Video input (`/props` says `video: true`; never sent one).
5. Claude Code sessions much longer than ~25 turns or with repeated compactions; LAN clients sharing
   the server with a Claude Code session.
6. Knowledge, multilingual and long-form prose quality (only compared by KL divergence).
7. The uncensored build's harmful-prompt refusal rate and MMLU on this file.
