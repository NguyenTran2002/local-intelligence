# llama.cpp — not in the repo

The server is **stock, unmodified upstream llama.cpp**, release **`b11065`** (commit `ce8caa6e6`),
Windows x64 with **CUDA 13.4**. `py -3 lib\download.py llamacpp` fetches the three release zips
(sha256-checked, sizes in `release.json`) and extracts them together into `llamacpp\bin\`.
All three are required — the CUDA zip alone does not contain the executables.

```
https://github.com/ggml-org/llama.cpp/releases/download/b11065/llama-b11065-bin-win-cpu-x64.zip
https://github.com/ggml-org/llama.cpp/releases/download/b11065/llama-b11065-bin-win-cuda-13.4-x64.zip
https://github.com/ggml-org/llama.cpp/releases/download/b11065/cudart-llama-bin-win-cuda-13.4-x64.zip
```

Expected after extraction (as on the reference machine):

```
llama-server.exe        sha256 28959d8d99e614cb0a40405ca2975de5a6e8368873e6d3b9341178f4b114f2d8
llama-server-impl.dll   sha256 3e95e944082366a9385ab6de0b92ad750d43dd0ac481dee81d68143fea663ec8
ggml-cuda.dll           sha256 71c85d0674bb3683d6c9c786a91b919715dccd4d55af6bf46c5e1596213acafa
```

The `.exe` files are ~9 KB launcher stubs paired with `-impl.dll` files that hold the code — a
9,216-byte `llama-server.exe` is correct, not a truncated download.

**Why CUDA 13.4:** the RTX 50 series (Blackwell, sm_120) needs CUDA 12.8+; the commonly linked
CUDA 12.4 build has no kernels for it at all. CUDA 13 needs **NVIDIA driver 580 or newer** and
supports **Turing (RTX 20) and newer**; Pascal/Volta and older are not supported by this build.
