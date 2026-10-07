"""Turn a hardware survey into a recommendation and (optionally) config\\machine.cmd.

    py -3 lib\\plan-config.py                      # survey this PC, print the verdict, change nothing
    py -3 lib\\plan-config.py --write [options]    # also write config\\machine.cmd
    py -3 lib\\plan-config.py --hw saved.json ...  # use a saved lib\\hardware-check.ps1 output instead

Options (all optional):
    --gpu N              which NVIDIA GPU (nvidia-smi index; default: the one with most VRAM)
    --bandwidth GBS      memory bandwidth if the GPU is not in release.json's table
    --desktop-mib N      VRAM the desktop/other apps hold (default: what nvidia-smi reports now)
    --lan                bind 0.0.0.0 so other devices on the network can connect (default 127.0.0.1)
    --port N             default 8080

Every context printed for a GPU other than a sterile RTX 5090 is an ESTIMATE from the sizing
constants in release.json. Prove it with lib\\fit-test.py before relying on it.
Standard library only.
"""
import argparse, datetime, json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REL = json.load(open(os.path.join(ROOT, "release.json"), encoding="utf-8"))
TH, SZ = REL["thresholds"], REL["sizing"]

# Profile -> (menu label, image-cap variable it depends on)
LABELS = {
    "CTX_D_STD": "Gemma 4 31B STANDARD", "CTX_D_TURBO": "Gemma 4 31B TURBO (MTP)",
    "CTX_H_STD": "Gemma 4 31B uncensored STANDARD", "CTX_H_TURBO": "Gemma 4 31B uncensored TURBO (MTP)",
    "CTX_M": "Gemma 4 26B-A4B MoE (MTP)",
    "CTX_Q_STD": "Qwen 3.8 27B STANDARD (4-bit)", "CTX_Q_TURBO": "Qwen 3.8 27B TURBO (4-bit, MTP)",
    "CTX_Q3_STD": "Qwen 3.8 27B STANDARD (3-bit, UNTESTED)",
}


def bandwidth_for(name):
    best = None
    for k, v in REL["gpus"].items():
        if k.startswith("_"):
            continue
        if k.lower() in name.lower() and (best is None or len(k) > len(best[0])):
            best = (k, v)
    return best[1] if best else None


def floor_to(x, step):
    return int(x // step * step)


def estimate(prof, usable, qwen_cap=None):
    p = SZ["profiles"][prof]
    fixed = p["fixed"]
    if qwen_cap is not None and p["model"].startswith("qwen"):
        enc = SZ["qwen_encoder_mib"]
        fixed += enc[str(qwen_cap)] - enc["4096"]
    room = usable - fixed - SZ["margin_untested_mib"]
    if room <= 0:
        return 0
    ctx = floor_to(room / p["slope"] * 1024, SZ["round_to"])
    return min(ctx, p["max"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hw", help="saved hardware-check.ps1 output (default: run the survey now)")
    ap.add_argument("--gpu", type=int)
    ap.add_argument("--bandwidth", type=float)
    ap.add_argument("--desktop-mib", type=int)
    ap.add_argument("--lan", action="store_true")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    if a.hw:
        raw = open(a.hw, "rb").read()
        # PowerShell 5.1's ">" writes UTF-16; Out-File -Encoding utf8 writes a BOM. Accept all.
        text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8-sig")
    else:
        ps = os.path.join(ROOT, "lib", "hardware-check.ps1")
        text = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps],
                              capture_output=True, text=True, timeout=120).stdout
    hw = json.loads(text)
    report_hw = {k: hw.get(k) for k in ("os", "cpu", "ram_mib", "repo_drive_free_gb", "python", "numpy",
                                        "claude_version", "other_display_adapters", "llama_server_running")}
    gpus = hw.get("nvidia_gpus") or []
    if isinstance(gpus, dict):
        gpus = [gpus]
    reasons, notes = [], []

    if not gpus:
        reasons.append("No NVIDIA GPU found (or the NVIDIA driver is not installed).")
        g = None
    else:
        g = next((x for x in gpus if x["index"] == a.gpu), None) if a.gpu is not None \
            else max(gpus, key=lambda x: x["vram_total_mib"])
        if g is None:
            sys.exit("No GPU with index %s" % a.gpu)

    report = {"gpu": g and g["name"], "verdict": None, "tier": None, "reasons": reasons,
              "notes": notes, "profiles": {}, "system": report_hw, "all_nvidia_gpus": gpus}

    if g:
        total = g["vram_total_mib"]
        bw = a.bandwidth or bandwidth_for(g["name"])
        report["vram_total_mib"], report["bandwidth_gbs"] = total, bw
        if bw is None:
            reasons.append("Memory bandwidth of '%s' is unknown: look up its spec and re-run with --bandwidth."
                           % g["name"])
        elif bw < TH["min_bandwidth_gbs"]:
            reasons.append("Memory bandwidth %d GB/s is below %d GB/s (half of the RTX 5090 this was "
                           "built on). Generation speed is limited by bandwidth, so a coding session would "
                           "be far slower than Claude Code normally is." % (bw, TH["min_bandwidth_gbs"]))
        if total < TH["min_vram_mib"]:
            reasons.append("%d MiB of VRAM is below the 16 GB class (%d MiB). The models would not fit with "
                           "enough context for a Claude Code session (it needs >= %d tokens)."
                           % (total, TH["min_vram_mib"], TH["claude_code_min_ctx"]))
        try:
            if int(g["driver"].split(".")[0]) < TH["min_driver_major"]:
                reasons.append("NVIDIA driver %s is older than %d - the CUDA 13 build needs %d+. "
                               "Update the driver (this alone is fixable)." % (g["driver"], TH["min_driver_major"],
                                                                               TH["min_driver_major"]))
        except ValueError:
            pass
        cc = g.get("compute_cap") or ""
        try:
            if cc and float(cc) < float(TH["min_compute_capability"]):
                reasons.append("GPU generation (compute %s) is older than Turing; the CUDA 13 build does not "
                               "support it." % cc)
        except ValueError:
            pass

        desktop = a.desktop_mib if a.desktop_mib is not None else g["vram_used_mib"]
        if hw.get("llama_server_running"):
            notes.append("llama-server is running now: its VRAM is counted as 'desktop'. Stop it and re-run "
                         "for a correct estimate.")
        sterile = desktop < 300
        report["desktop_in_use_mib"] = desktop
        if (g.get("display_active", "").lower() == "enabled") or not sterile:
            igpu = [d["name"] for d in hw.get("other_display_adapters") or []]
            msg = "The desktop is using %d MiB of this GPU." % desktop
            if igpu:
                msg += (" This PC also has %s: plugging the monitor into the motherboard instead gives that "
                        "VRAM back to the model (more context)." % ", ".join(igpu))
            else:
                msg += " No integrated GPU was found, so that VRAM stays taken."
            notes.append(msg)

    hard_fail = [r for r in reasons if "driver" not in r and "unknown" not in r]
    if g and report.get("bandwidth_gbs") is None:
        report["verdict"] = "need-bandwidth"
    elif not g or hard_fail:
        report["verdict"] = "openrouter"
    elif reasons:
        report["verdict"] = "fix-then-local"
    else:
        report["verdict"] = "local"

    if g and report["verdict"] in ("local", "fix-then-local"):
        total = g["vram_total_mib"]
        usable = total - SZ["unusable_mib"] - report["desktop_in_use_mib"]
        is_ref = "RTX 5090" in g["name"] and report["desktop_in_use_mib"] < 300
        if total >= 31000:
            report["tier"] = "32gb"
        elif total >= 23000:
            report["tier"] = "24gb"
        else:
            report["tier"] = "16gb"
        tier = report["tier"]
        qcap = 4096 if tier != "16gb" else 1600
        report["qwen_image_cap"] = qcap
        for prof in SZ["profiles"]:
            if prof.startswith("_"):
                continue
            p = SZ["profiles"][prof]
            if prof == "CTX_Q3_STD" and tier != "16gb":
                continue
            if prof != "CTX_Q3_STD" and tier == "16gb" and p["model"] != "gemma-26b":
                continue          # 4-bit 27-31B weights alone exceed 16 GB
            if p["model"] == "uncensored" and tier != "32gb":
                continue
            if is_ref and p["measured_5090"]:
                ctx, status = p["measured_5090"], "measured on this GPU model (sterile RTX 5090)"
            else:
                ctx, status = estimate(prof, usable, qcap), "ESTIMATE - untested on this GPU"
            if ctx < TH["min_offered_ctx"]:
                ctx, status = 0, "does not fit usefully"
            report["profiles"][prof] = {"label": LABELS[prof], "ctx": ctx, "status": status,
                                        "claude_code_ok": ctx >= TH["claude_code_min_ctx"]}
        if tier == "16gb":
            notes.append("16 GB cards run Qwen 3.8 at 3-bit (UD-IQ3_XXS). That quant has NOT been tested by this "
                         "project, and context is restrictive: Claude Code compacts at context - 33K.")
        ram = hw.get("ram_mib") or 0
        report["cram_mib"] = max(2048, min(24576, int(ram * 0.375) // 1024 * 1024))

    print(json.dumps(report, indent=2))

    if a.write:
        if report["verdict"] not in ("local", "fix-then-local"):
            sys.exit("Not writing config\\machine.cmd: verdict is '%s', not local hosting." % report["verdict"])
        os.makedirs(os.path.join(ROOT, "config"), exist_ok=True)
        path = os.path.join(ROOT, "config", "machine.cmd")
        L = ["@echo off",
             "rem Written by lib\\plan-config.py on %s for: %s" % (datetime.date.today(), g["name"]),
             "rem Re-run onboarding (or plan-config.py --write) to regenerate. A context of 0 hides that profile.",
             "rem Contexts marked ESTIMATE are not proven until lib\\fit-test.py passes on this GPU.",
             'set "TIER=%s"' % report["tier"],
             'set "GPU_NAME=%s"' % g["name"].replace("%", ""),
             'set "HOST=%s"' % ("0.0.0.0" if a.lan else "127.0.0.1"),
             'set "PORT=%d"' % a.port,
             'set "CRAM=%d"' % report["cram_mib"],
             'set "Q_IMGMAX=%d"' % report["qwen_image_cap"]]
        for prof in SZ["profiles"]:
            if prof.startswith("_"):
                continue
            pr = report["profiles"].get(prof)
            L.append('set "%s=%d"' % (prof, pr["ctx"] if pr else 0))
            L.append('set "%s_NOTE=%s"' % (prof, pr["status"] if pr else "not offered on this GPU"))
        open(path, "w", newline="\r\n").write("\n".join(L) + "\n")
        print("\nwrote", path, file=sys.stderr)


if __name__ == "__main__":
    main()
