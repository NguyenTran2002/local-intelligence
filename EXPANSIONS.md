# Expansions — head-start notes for your Claude

**None of this is officially supported or tested by this project.** These are notes for the
user's own Claude Code, which knows this machine far better than we do, to pilot extensions *with
the user's agreement*. The measured facts in `REFERENCE.md` still apply wherever the same binary and
models run; everything else must be measured on the new setup (`lib\fit-test.py` logic is portable).

## Apple Silicon Macs (Metal)

- llama.cpp ships macOS arm64 builds with Metal; every launcher flag maps across, except the CUDA
  build choice. Port the launcher as a shell script; keep the flags table in `CLAUDE.md` intact.
- **Unified memory is shared with macOS and every running app.** The GPU can only wire part of RAM
  (by default roughly 65–75% on larger machines; `sysctl iogpu.wired_limit_mb` shows/raises it —
  raising it is a system setting, the user's call). Before sizing, measure what the system and the
  user's usual apps already hold (Activity Monitor → Memory, or `vm_stat`) and size from what is
  actually free, with a generous margin: overcommit means swapping, not a clean error.
- **Bandwidth is the catch.** M-series Max chips are ~400–550 GB/s, Ultra ~800 GB/s — below this
  project's 896 GB/s bar, so the honest recommendation is still the cloud path for Claude Code. A
  large-memory Mac can still be a fine *chat* server, or run the MoE (only ~4B parameters active
  per token, so it decodes far faster than its size suggests).
- A Mac can always be a **client** of a Windows server (see "Remote access").

## Linux + NVIDIA

- llama.cpp publishes Linux CUDA builds; the flags are identical. Port `Start-Local-LLM-Server.bat`
  to bash (pass paths as quoted single arguments) and keep the ZDR log pipe
  (`2>&1 | python3 lib/zdr-log-filter.py <log>` with `--log-prefix --log-timestamps --log-colors off`).
- Linux has **no sysmem fallback**: an oversized context fails at allocation instead of silently
  spilling — friendlier, but re-run the fit test anyway (images allocate late).
- `lib/plan-config.py` and `lib/fit-test.py` are plain Python; `hardware-check.ps1` needs a
  replacement (`nvidia-smi --query-gpu=...` gives the same fields).

## Sharing on the home network (LAN)

Onboarding offers this (`--lan` → `HOST=0.0.0.0`, then `setup-network-once-ADMIN.ps1` and
`CONNECT-mine.md`). Notes: the API key is required for every request; two slots means a third client
queues; request bodies above the server's fixed limit return HTTP 413 (resize images); a Claude Code
session with a subagent already uses both slots.

## Remote access from your own devices (Tailscale)

Worked well in this project's original setup, but is not shipped. Lessons:
- Use `tailscale serve --bg --http=<port> http://127.0.0.1:8080` (tailnet only). **Never Funnel**
  (that publishes to the internet).
- `serve --http` routes by **host name**: clients must use `http://<machine>.<tailnet>.ts.net:<port>`;
  the bare tailnet IP answers 404.
- On Windows the Tailscale installer adds a firewall rule accepting **every port** on the tailnet
  address. The real gate is the **tailnet access policy** (admin console): allow only the serve port,
  e.g. `{"action":"accept","src":["autogroup:member"],"dst":["autogroup:self:<port>"]}`. Without
  it, tailnet devices reach 8080 directly even with "serve" off.
- The serve setting persists across reboots: reset it (`tailscale serve reset`) when stopping.
- Do not run another VPN on the client at the same time (DNS ranges can collide with Tailscale's
  100.64.0.0/10 and break name resolution).
- If you want Tailscale's own client log uploads off: `TS_NO_LOGS_NO_SUPPORT=true` for the Windows
  service (`C:\ProgramData\Tailscale\tailscaled-env.txt`) and as a user env var for the tray app.

## Bigger GPUs (48–96 GB)

The 31B profiles can grow toward the model maximum (262,144) — `lib\plan-config.py` estimates it.
More slots (`-np 3`+, still with `-kvu`) let more clients/subagents run at once; each Gemma slot adds
~640 MiB of sliding-window cache. Re-run the fit test after any change.

## Multi-GPU

Not covered. llama.cpp can split a model across GPUs (`--split-mode`, `--tensor-split`), but the
sizing constants here assume one GPU; measure from scratch.

## Smaller or slower GPUs (below the bar)

Possible, not recommended for Claude Code: lower-bit quants (Qwen 3.8 down to ~6 GB at IQ1, quality
falls fast), CPU offload of some layers (`-ngl` below 99: works, much slower), or the MoE text-only
(drop `-mm`). Fine for chat experiments; for coding sessions the cloud path is the better experience.

## A crash instead of a silent slowdown

NVIDIA Control Panel → Manage 3D settings → *CUDA – Sysmem Fallback Policy* → *Prefer No Sysmem
Fallback* (globally or for `llama-server.exe`). Then a too-large context fails loudly instead of
running 7× slower. A system setting: explain it, let the user decide.
