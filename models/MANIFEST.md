# Model weights — not in the repo

Downloaded by `py -3 lib\download.py <bundle>` from Hugging Face at **pinned revisions**, each file
checked against its sha256 (the Hugging Face LFS id). The authoritative list, with sizes and hashes,
is `release.json → downloads`; this page explains it. All repos are public and ungated.

| Bundle | Folder | Source @ revision | Files |
|---|---|---|---|
| `qwen-q4` | `qwen3.8-27B/` | `unsloth/Qwen3.8-27B-GGUF` @ `4ca72078` | `Qwen3.8-27B-UD-Q4_K_XL.gguf` (17.56 GB, MTP head built in), `mmproj-F16.gguf` (0.93 GB) |
| `qwen-q3` | `qwen3.8-27B/` | same | `Qwen3.8-27B-UD-IQ3_XXS.gguf` (10.93 GB, **untested here**), `mmproj-F16.gguf` |
| `gemma-31b` | `gemma-4-31B-it-qat/` | `unsloth/gemma-4-31B-it-qat-GGUF` @ `43cc1aeb` | `gemma-4-31B-it-qat-UD-Q4_K_XL.gguf` (17.29 GB), `mmproj-F16.gguf` (1.20 GB), `mtp-gemma-4-31B-it.gguf` (0.28 GB, TURBO drafter) |
| `gemma-26b` | `unsloth-26B-A4B-qat/` | `unsloth/gemma-4-26B-A4B-it-qat-GGUF` @ `7b92b5b2` | `gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf` (14.25 GB), `mmproj-F16.gguf` (1.19 GB), `mtp-gemma-4-26B-A4B-it.gguf` (0.25 GB) |

**The model files contain no vision tensors** — the `mmproj-F16.gguf` next to each is its vision
tower. **The three `mmproj-F16.gguf` files are different** (projection dims 5376 / 2816 / 5120 for
31B / MoE / Qwen) and pairing the wrong one is silently wrong, not an error. Keep each model in its
own folder, as the launcher expects.

## The uncensored 31B — built, not downloaded

`gemma-4-31B-it-qat-heretic/gemma-4-31B-it-qat-heretic-Q4_0-attnQ8_0.gguf` (17,970,293,536 bytes,
sha256 `05d2e0f8b5ef5ae4b852bdd8ca1504bd276252b958d0bbb3bf6c55022aae8915`) is the `gemma-31b` model
file with only the 26 `attn_output` tensors of layers 10–35 replaced by llama.cpp reference Q8_0 of
llmfan46's abliterated weights (`llmfan46/gemma-4-31B-it-qat-q4_0-unquantized-uncensored-heretic`
@ `ce415cf3`; ~2.73 GB is range-fetched, not the whole repo). It uses the 31B's vision tower and
drafter.

```
py -3 models\gemma-4-31B-it-qat-heretic\build-heretic-gguf.py ^
   models\gemma-4-31B-it-qat\gemma-4-31B-it-qat-UD-Q4_K_XL.gguf ^
   models\gemma-4-31B-it-qat-heretic\gemma-4-31B-it-qat-heretic-Q4_0-attnQ8_0.gguf
```

Needs Python 3.9+, numpy and curl. The script checks its input and output hashes. Why it is built
rather than downloaded: `REFERENCE.md` §8.

## Qwen's patched chat template

`qwen3.8-27B/qwen3.8-chat-template-patched.jinja` is the template embedded in the Qwen GGUF with one
line changed (line 110), so a system message after the first turn is rendered in place instead of
raising an error (HTTP 500 that breaks the rest of the conversation). The launcher passes it with
`--chat-template-file`.
