"""Worst-case VRAM fit test against the RUNNING server. Standard library only.

    py -3 lib\\fit-test.py [--url http://127.0.0.1:8080]

What it does (in this order, because this is what actually fills VRAM):
  1. a short prompt                    -> shallow prefill speed (the baseline)
  2. one max-size image                -> the vision encoder's one-time allocation (~0.2-1.1 GB)
  3. a prompt at ~99% of the context   -> the full KV cache; deep prefill speed
  4. two max-size images at once       -> both slots busy on top of the deep cache
while sampling nvidia-smi every 0.5 s for the peak.

Verdict:
  PASS   - every request answered, deep prefill at normal speed.
  SPILL  - deep prefill collapsed (Windows moved VRAM into system RAM: no error, just ~7x slower).
  CRASH  - a request failed or the server died (Qwen does this instead of spilling).
On SPILL or CRASH: lower that profile's context in config\\machine.cmd by one or two steps of 4096
and run again. Takes ~2-10 minutes depending on the GPU and context.
"""
import argparse, base64, json, os, random, struct, subprocess, sys, threading, time, urllib.request, zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def call(base, key, path, body=None, timeout=3600):
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read()[:300].decode("utf-8", "replace")}
    except Exception as e:
        return 0, {"error": str(e)[:300]}


def png(w, h, seed):
    """A busy synthetic RGB image, so the encoder sees real work. Pure Python."""
    rows = []
    for y in range(h):
        r = bytearray(1 + 3 * w)
        r[1::3] = bytes(((x * 7 + y * 3 + seed) & 255) for x in range(w))
        r[2::3] = bytes(((x ^ y) & 255) for x in range(w))
        r[3::3] = bytes((255 if ((x // 64 + y // 64) % 2) else 0) for x in range(w))
        rows.append(bytes(r))
    raw = b"".join(rows)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw, 1)) + chunk(b"IEND", b""))


def filler(n_chars):
    rnd = random.Random(1234)
    words = ("the server model context memory token image cache layer value request answer local graphics "
             "card prompt reply window budget profile speed test check result system file index slot "
             "batch decode prefill vision encoder tensor weight launcher").split()
    out, size = [], 0
    while size < n_chars:
        s = " ".join(rnd.choice(words) for _ in range(rnd.randint(8, 18))).capitalize() + ". "
        out.append(s); size += len(s)
    return "".join(out)[:n_chars]


class Peak(threading.Thread):
    def __init__(self, index):
        super().__init__(daemon=True); self.index, self.peak, self.run_ = index, 0, True
        self.total = None

    def run(self):
        while self.run_:
            try:
                o = subprocess.run(["nvidia-smi", "-i", str(self.index), "--query-gpu=memory.used,memory.total",
                                    "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10)
                used, total = [int(x) for x in o.stdout.strip().split(",")]
                self.peak, self.total = max(self.peak, used), total
            except Exception:
                pass
            time.sleep(0.5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("LOCAL_LLM_URL", "http://127.0.0.1:8080"))
    ap.add_argument("--gpu", type=int, default=0)
    a = ap.parse_args()
    key = open(os.path.join(ROOT, "api-key.txt"), encoding="utf-8").read().strip()

    st, props = call(a.url, key, "/props", timeout=10)
    if st != 200:
        sys.exit("No server answering at %s (%s). Start Start-Local-LLM-Server.bat first." % (a.url, props))
    alias = props.get("model_alias", "")
    n_ctx = props["default_generation_settings"]["n_ctx"]
    vision = (props.get("modalities") or {}).get("vision", False)
    qwen = "qwen" in alias.lower()
    w = h = 2048 if qwen else 1920        # exactly the image-token cap: 2048^2/32^2 = 4096, 1920^2/48^2 = 1600
    print("server: %s, context %d, vision %s" % (alias, n_ctx, vision), flush=True)

    mon = Peak(a.gpu); mon.start(); time.sleep(1.5)
    boot = mon.peak
    print("VRAM in use before the test: %d MiB of %s" % (boot, mon.total), flush=True)
    results, ok = {}, True

    def chat(content, max_tokens=48):
        t0 = time.time()
        st, r = call(a.url, key, "/v1/chat/completions", {
            "model": alias, "max_tokens": max_tokens, "temperature": 0, "cache_prompt": False,
            "messages": [{"role": "user", "content": content}],
            "chat_template_kwargs": {"enable_thinking": False}, "reasoning_effort": "none"})
        return st, r, time.time() - t0

    # 1. shallow
    st, r, _ = chat(filler(16000) + "\n\nIn one word, what is the text above about?")
    ok &= st == 200
    shallow = (r.get("timings") or {}).get("prompt_per_second", 0) if st == 200 else 0
    print("1. shallow prompt       : HTTP %s  prefill %.0f tok/s" % (st, shallow), flush=True)

    imgs = []
    if vision:
        print("   (building %dx%d test images...)" % (w, h), flush=True)
        imgs = [base64.b64encode(png(w, h, s)).decode() for s in (1, 2, 3)]

        def ask_img(i, out):
            st, r, dt = chat([{"type": "image_url", "image_url": {"url": "data:image/png;base64," + imgs[i]}},
                              {"type": "text", "text": "Describe the pattern in five words."}])
            out.append((st, (r.get("usage") or {}).get("prompt_tokens") if st == 200 else r.get("error")))
        out = []; ask_img(0, out)
        ok &= out[0][0] == 200
        print("2. max-size image       : HTTP %s  prompt_tokens %s" % out[0], flush=True)
    else:
        print("2. max-size image       : skipped (server has no vision tower loaded)")

    # 3. deep: calibrate chars/token, then fill to ~99%
    sample = filler(200000)
    st, t = call(a.url, key, "/tokenize", {"content": sample})
    cpt = len(sample) / max(1, len(t.get("tokens", [1])))
    target = int(n_ctx * 0.99) - 600
    st, r, dt = chat(filler(int(target * cpt)) + "\n\nIn one word, what is the text above about?")
    ok &= st == 200
    deep = (r.get("timings") or {}).get("prompt_per_second", 0) if st == 200 else 0
    ptok = (r.get("usage") or {}).get("prompt_tokens") if st == 200 else r.get("error")
    print("3. ~99%% of context      : HTTP %s  prompt_tokens %s of %d  prefill %.0f tok/s  (%.0f s)"
          % (st, ptok, n_ctx, deep, dt), flush=True)

    if vision:
        out = []
        th = [threading.Thread(target=ask_img, args=(i, out)) for i in (1, 2)]
        [x.start() for x in th]; [x.join() for x in th]
        ok &= all(o[0] == 200 for o in out)
        print("4. two images at once   : %s" % out, flush=True)

    time.sleep(1.5); mon.run_ = False
    alive = call(a.url, key, "/health", timeout=10)[0] == 200
    total = mon.total or 0
    print("\nVRAM peak %d MiB of %d  (headroom %d MiB)" % (mon.peak, total, total - mon.peak))
    # Normal deep prefill is ~35-45% of shallow; a spill into system RAM drops it to ~5%.
    spill = shallow and deep and deep < 0.15 * shallow
    if not alive or not ok:
        print("VERDICT: CRASH - a request failed or the server stopped. Lower this profile's context and retest.")
        sys.exit(2)
    if spill:
        print("VERDICT: SPILL - deep prefill fell to %.0f%% of shallow: VRAM overflowed into system RAM. "
              "Lower this profile's context and retest." % (100 * deep / shallow))
        sys.exit(3)
    print("VERDICT: PASS - this profile fits this GPU at %d tokens of context." % n_ctx)


if __name__ == "__main__":
    main()
