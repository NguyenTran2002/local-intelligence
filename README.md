# Local Intelligence

**Your own private AI model server on your own NVIDIA GPU, with Claude Code pointed at it.**

Local Intelligence runs open models on your Windows PC through
[llama.cpp](https://github.com/ggml-org/llama.cpp), with an OpenAI- and Anthropic-compatible API and
vision. It also runs your Claude Code against that server, in its own separate profile. Your
prompts, code and files never leave the machine.

| Model | Good at |
|---|---|
| **Qwen 3.8 27B** | agentic coding with Claude Code: best on every coding test here |
| **Gemma 4 31B** | chat, writing, reading fine print in images |
| **Gemma 4 26B-A4B MoE** | very fast bulk work over short documents |
| **Gemma 4 31B uncensored** | the 31B with refusals edited out (built on your PC) |

If your GPU isn't strong enough, onboarding says so plainly. It then sets up the same Claude Code
experience against **Qwen 3.8 27B on [OpenRouter](https://openrouter.ai)**, a pay-per-token cloud
service.

## Get started

You need [Claude Code](https://code.claude.com) and [git](https://git-scm.com).

1. **Clone** the repo (or download it as a ZIP).
   ```
   git clone <this repository's URL>
   cd <the cloned folder>
   ```
2. **Start Claude Code** in that folder:
   ```
   claude
   ```
3. **Type:**
   ```
   Onboard me
   ```
4. **Done.** Claude guides you through the setup, and nothing on your machine changes without your OK:
   - checks your hardware;
   - recommends local or cloud, and explains why;
   - downloads and verifies the models;
   - sizes everything for your GPU and tests that it fits (only if you agree);
   - creates the `claude-local` (or `claude-openrouter`) command.

After that:
- **Start the server:** double-click `Start-Local-LLM-Server.bat`.
- **Use Claude Code against it:** run `claude-local` in any project folder.
- **Change anything later:** ask Claude in this folder.

## Requirements

| | Local hosting | Cloud (OpenRouter) |
|---|---|---|
| OS | **Windows 11** | Windows 11 |
| GPU | NVIDIA, **16 GB+ VRAM** and **≥ 896 GB/s** memory bandwidth (RTX 5090 / 4090 / 3090 / 5080 / 5070 Ti class), driver 580+ | any |
| Disk | 13–75 GB, depending on the models you pick | ~0 |
| Other | Python 3 (onboarding can install it) | an OpenRouter account with credits |

**What's measured and what's estimated:**
- **Measured:** everything on one RTX 5090. The numbers are in [REFERENCE.md](REFERENCE.md).
- **Estimated:** other GPUs get calculated settings, and a short fit test confirms them on your card.
- **24 GB cards** (4090, 3090) run Qwen 3.8 at 4-bit with roughly 100–120K tokens of context.
- **16 GB cards** (5080, 5070 Ti) run Qwen 3.8 at 3-bit with roughly 64–80K. That quantization is
  **untested** here and the context is tight for Claude Code.

**Why the bandwidth bar?** A model's generation speed is limited by how fast the GPU reads its own
memory. Below about half of an RTX 5090, a coding session would be far slower than Claude Code
normally is. Below 16 GB, the models don't fit with enough context for a session. In either case
the cloud path is the better experience.

macOS and Linux are not supported. [EXPANSIONS.md](EXPANSIONS.md) has notes if you want to port it
with your own Claude.

## Versions

Pinned and tested:
- **llama.cpp `b11065`**
- **Claude Code `2.1.285`** on the **stable** release channel

The `claude-local` profile follows the stable channel, and onboarding offers to move your main
Claude Code there too. If your Claude Code version is different, the launchers tell you it **will
most likely work but is NOT tested**.

## Privacy

Serving locally, nothing leaves your machine:
- the cache lives in memory only;
- the server's log files keep metadata only, because a filter redacts any model output the server
  would otherwise echo into them.

Two opt-ins are not private, and onboarding asks about each:
- **Exa web search:** your search queries go to Exa.
- **The OpenRouter path:** everything goes to OpenRouter and its providers.

## What's in here

| | |
|---|---|
| `Start-Local-LLM-Server.bat` | the server launcher: pick a model, then a profile |
| `claude-local.cmd` / `claude-openrouter.cmd` | Claude Code against the local server or OpenRouter |
| `release.json` | pinned versions, downloads and sha256s, GPU tiers, sizing constants |
| `lib/` | hardware check, config planner, downloader, fit test, profile maker, log filter |
| `CLAUDE.md`, `.claude/skills/onboard/` | what your Claude reads: rules, traps, the onboarding procedure |
| `REFERENCE.md` | how it all works, and the measurements behind every number |
| `EXPANSIONS.md` | ideas: Mac, Linux, LAN sharing, remote access, bigger GPUs |
| `CONNECT-TEMPLATE.md` | how other devices on your network connect |

Models and llama.cpp are downloaded on demand at pinned versions. Nothing heavy is in the repo.

## License

[MIT](LICENSE). Each model has its own license: Gemma's terms for the Gemma models, and Qwen's
license for Qwen. llama.cpp is MIT.
