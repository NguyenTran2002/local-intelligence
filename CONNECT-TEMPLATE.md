# Connecting to a Local Intelligence server from another device

> **Template.** Onboarding fills the placeholders (`<SERVER_IP>`, `<PORT>`, `<API_KEY>`,
> `<MODEL_ID>`) into `CONNECT-mine.md`, which is git-ignored because it contains the server's key.
> Hand that copy only to your own devices. The server must have been set up for LAN sharing
> (onboarding's network option + `setup-network-once-ADMIN.ps1` on the server PC).

## 1. Connection details

| | |
|---|---|
| Base URL (OpenAI-compatible) | `http://<SERVER_IP>:<PORT>/v1` |
| Base URL (Anthropic-compatible) | `http://<SERVER_IP>:<PORT>` (routes `/v1/messages`) |
| API key | `<API_KEY>` — send as `Authorization: Bearer <API_KEY>` |
| Model id | `<MODEL_ID>` — whichever model the server PC started; `GET /props` reports it as `model_alias` |
| Context | read `/props` → `default_generation_settings.n_ctx`; exceeding it is HTTP 400, not a truncation |

## 2. Check it first

```bash
curl -sS http://<SERVER_IP>:<PORT>/health
curl -sS http://<SERVER_IP>:<PORT>/v1/chat/completions \
  -H "Content-Type: application/json" -H "Authorization: Bearer <API_KEY>" \
  -d '{"model":"<MODEL_ID>","messages":[{"role":"user","content":"hi"}],"max_tokens":2000}'
```

## 3. When it doesn't connect

| Symptom | Cause | Fix |
|---|---|---|
| `Connection refused` | Server not running, or started in local-only mode | Start it on the server PC; check `HOST=0.0.0.0` in its `config\machine.cmd` |
| Times out | Windows Firewall, or you are on another subnet / guest Wi-Fi | Run `setup-network-once-ADMIN.ps1` on the server PC; be on the same network |
| Ping fails, curl works | Normal — ICMP may be blocked | Ignore ping |
| `401` | Wrong key or missing header | One line, no quotes |
| `400` with a context message | Prompt larger than the server's context | Shorten, or ask for a bigger profile |
| Empty `content` | `max_tokens` too small — thinking used it all | Raise it (≥ 2,000) |
| `413` | Request body above the server's fixed limit | Resize images (JPEG/WEBP, ~2,500 px long edge) |
| Hangs 60–120 s | Long prompt still prefilling — not a hang | Client timeout 600 s, stream |

If the server PC's IP changed (DHCP), re-run `lib\get-lan-ip.ps1` there.

## 4. Wiring it into a client

Any OpenAI SDK works by overriding the base URL:

```python
from openai import OpenAI
client = OpenAI(base_url="http://<SERVER_IP>:<PORT>/v1", api_key="<API_KEY>", timeout=600.0)
r = client.chat.completions.create(model="<MODEL_ID>", max_tokens=2000,
                                   messages=[{"role": "user", "content": "Hello"}])
print(r.choices[0].message.content)
```

**Don't override the sampler** (`temperature`, `top_p`, `top_k`): the server already runs each
vendor's reference values. Traps that return 200 silently: `repetition_penalty` is ignored (use
`repeat_penalty` or `frequency_penalty`); `presence_penalty` is inert in −2…2; `seed` is not
bit-exact.

**Claude Code on another Windows PC** can use this server too: copy `claude-local.cmd` and
`api-key.txt` there, set `LOCAL_LLM_URL=http://<SERVER_IP>:<PORT>` before running it, and create
the profile with `lib\make-profile.py`. Not tested by the project.

## 5. Limits and speed

- **2 requests at a time**; a third queues. A Claude Code session with a subagent uses both.
- Prefill is slow on long prompts (~1,200–3,400 tokens/s on the reference GPU): a cold 130K-token
  request takes over a minute before the first token. Set client timeouts to **600 s** and stream.
- English is ~4.2 characters per token. Exact count: `POST /v1/chat/completions/input_tokens`.

## 6. Thinking is always on

- Budget `max_tokens` generously. Turn it off per request with `"reasoning_effort": "none"`
  (or `"chat_template_kwargs": {"enable_thinking": false}`), and **keep the same setting for the
  whole conversation** — flipping it invalidates the entire prompt cache.
- Cap it per request: `"thinking_budget_tokens": 4096`. Past ~64K tokens of context, about 1 Gemma
  request in 12 otherwise thinks until `max_tokens` runs out.
- Qwen only: `reasoning_effort` accepts `none`, `low`, `medium`, `high`, `xhigh` — **anything else is
  HTTP 500**.

## 7. Staying fast: prompt caching

The server caches by prefix: a growing conversation reprocesses only the new tokens. Keep the
beginning of the prompt byte-identical (fixed system prompt, stable tool order, no timestamps at the
top, append — don't rewrite earlier turns). Check `usage.prompt_tokens_details.cached_tokens`.

## 8. Images

`image_url` content parts with `data:` URIs. JPEG, PNG, BMP, GIF, TGA and WEBP all work (format is
sniffed from the bytes). Gemma caps an image at 1,600 tokens (~3.7 MP), Qwen at 4,096 (~4.2 MP);
larger images are downscaled, never cropped. Every image is resent each turn — keep them small.

## 9. What the API supports

Upstream llama.cpp, unmodified: `/v1/chat/completions`, `/v1/completions`, `/v1/models`,
`/v1/responses`, `/v1/embeddings`, `/v1/messages`, `/v1/messages/count_tokens`, `/health`,
`/metrics`, `/props`. Streaming, vision, tool calling (OpenAI `tools` / `tool_choice`, verified
round trip), JSON-schema output, grammars. `/slots` is disabled on purpose (privacy).

## 10. What you cannot do from here

Start/stop the server, change the model, profile or any flag — those happen on the server PC.
If `/props` shows `gemma-4-26b` (the MoE) and you need agentic work beyond ~32K tokens, ask for Qwen
or the 31B: the MoE stops calling tools at depth without an error.
