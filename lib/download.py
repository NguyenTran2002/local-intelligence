"""Download what release.json lists - resumable, parallel, sha256-verified. Standard library only.

    py -3 lib\\download.py --list                 sizes of every bundle, and what is already here
    py -3 lib\\download.py llamacpp qwen-q4       fetch bundles (names from release.json "downloads")

Each file is fetched in N parallel HTTP range segments into <dest>.partial; progress is saved to
<dest>.progress.json, so an interrupted download (closed window, power cut, network drop) resumes
where it stopped when you run the same command again. The final name appears only after the
sha256 matches the pinned value. The llamacpp bundle is also extracted into llamacpp\\bin.
"""
import hashlib, json, os, sys, threading, time, urllib.request, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REL = json.load(open(os.path.join(ROOT, "release.json"), encoding="utf-8"))
BUNDLES = {k: v for k, v in REL["downloads"].items() if not k.startswith("_")}
MAX_FAILS = 40          # consecutive failures per segment before giving up (a re-run resumes)


def url_of(bundle, f):
    if "url" in f:
        return f["url"]
    return "https://huggingface.co/%s/resolve/%s/%s" % (bundle["repo"], bundle["revision"], f["name"])


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 24), b""):
            h.update(blk)
    return h.hexdigest()


def download(url, dest, size, sha, nseg=6):
    rel = os.path.relpath(dest, ROOT)
    if os.path.exists(dest) and os.path.exists(dest + ".ok") and os.path.getsize(dest) == size:
        print("SKIP (already verified)", rel); return True
    if os.path.exists(dest) and os.path.getsize(dest) == size:
        print("CHECK", rel, "(present, verifying sha256)", flush=True)
        if sha256_file(dest) == sha:
            open(dest + ".ok", "w").write(sha); print("OK   ", rel); return True
        print("  sha256 mismatch - downloading again")
    if size < 64 << 20:
        nseg = 1
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    part, prog = dest + ".partial", dest + ".progress.json"
    seg = size // nseg
    ranges = [(i * seg, (size if i == nseg - 1 else (i + 1) * seg) - 1) for i in range(nseg)]
    done = [0] * nseg
    if os.path.exists(prog) and os.path.exists(part):
        p = json.load(open(prog))
        if p.get("size") == size and p.get("nseg") == nseg:
            done = p["done"]
    if not os.path.exists(part):
        with open(part, "wb") as f:
            f.truncate(size)
    lock = threading.Lock()
    failed = [False] * nseg

    def save():
        with lock:
            tmp = prog + ".tmp"
            json.dump({"size": size, "nseg": nseg, "done": done}, open(tmp, "w"))
            os.replace(tmp, prog)

    def worker(i):
        a, b = ranges[i]
        fails = 0
        while a + done[i] <= b:
            start = a + done[i]
            try:
                req = urllib.request.Request(url, headers={"Range": "bytes=%d-%d" % (start, b),
                                                           "User-Agent": "local-intelligence-downloader"})
                with urllib.request.urlopen(req, timeout=60) as r, open(part, "r+b") as f:
                    if r.status != 206:      # a server ignoring Range would overwrite other segments
                        raise IOError("expected HTTP 206, got %s" % r.status)
                    f.seek(start)
                    last = time.time()
                    while True:
                        chunk = r.read(min(1 << 20, b - (a + done[i]) + 1))
                        if not chunk:
                            break
                        f.write(chunk)
                        done[i] += len(chunk)
                        if time.time() - last > 5:     # data on disk BEFORE progress says so
                            f.flush(); os.fsync(f.fileno()); save(); last = time.time()
                        if a + done[i] > b:
                            break
                    f.flush(); os.fsync(f.fileno())
                save()
                fails = 0
            except Exception as e:
                fails += 1
                save()
                if fails >= MAX_FAILS:
                    print("  segment %d gave up after %d failures: %s" % (i, fails, e), flush=True)
                    failed[i] = True
                    return
                time.sleep(min(60, 5 * fails))

    print("GET  ", rel, "%.2f GB" % (size / 1e9), flush=True)
    t0, got0 = time.time(), sum(done)
    th = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(nseg)]
    [t.start() for t in th]
    while any(t.is_alive() for t in th):
        time.sleep(10)
        g = sum(done)
        print("  %s  %6.2f / %.2f GB  %5.1f MB/s" % (time.strftime("%H:%M:%S"), g / 1e9, size / 1e9,
              (g - got0) / 1e6 / max(1, time.time() - t0)), flush=True)
    [t.join() for t in th]
    if any(failed) or sum(done) != size:
        print("INCOMPLETE", rel, "- run the same command again to resume.")
        return False
    print("SHA  ", rel, flush=True)
    if sha256_file(part) != sha:
        print("SHA256 MISMATCH - deleting the partial file; run again to re-download.")
        os.remove(prog); os.remove(part)
        return False
    os.replace(part, dest)
    open(dest + ".ok", "w").write(sha)
    os.remove(prog)
    print("OK   ", rel, flush=True)
    return True


def extract_llamacpp(bundle):
    out = os.path.join(ROOT, bundle["extract_to"])
    os.makedirs(out, exist_ok=True)
    for f in bundle["files"]:
        z = os.path.join(ROOT, bundle["dir"], f["name"])
        with zipfile.ZipFile(z) as zf:
            for m in zf.infolist():
                if m.is_dir():
                    continue
                name = os.path.basename(m.filename)       # flatten: everything lives in llamacpp\bin
                with zf.open(m) as src, open(os.path.join(out, name), "wb") as dst:
                    dst.write(src.read())
    exe = os.path.join(out, "llama-server.exe")
    print("EXTRACTED to", os.path.relpath(out, ROOT), "- llama-server.exe present:", os.path.exists(exe))
    return os.path.exists(exe)


def main():
    args = sys.argv[1:]
    if not args or args[0] == "--list":
        for k, b in BUNDLES.items():
            tot = sum(f["size"] for f in b["files"])
            have = all(os.path.exists(os.path.join(ROOT, b["dir"], f["name"])) for f in b["files"])
            print("%-10s %6.2f GB  %s%s" % (k, tot / 1e9, "present  " if have else "", b.get("_comment", "")))
        return
    bad = [a for a in args if a not in BUNDLES]
    if bad:
        sys.exit("Unknown bundle(s): %s. Known: %s" % (", ".join(bad), ", ".join(BUNDLES)))
    ok = True
    for k in args:
        b = BUNDLES[k]
        for f in b["files"]:
            ok &= download(url_of(b, f), os.path.join(ROOT, b["dir"], f["name"]), f["size"], f["sha256"])
        if k == "llamacpp" and ok:
            ok &= extract_llamacpp(b)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
