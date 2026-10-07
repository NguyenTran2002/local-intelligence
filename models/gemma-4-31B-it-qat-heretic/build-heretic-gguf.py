"""Rebuild gemma-4-31B-it-qat-heretic-Q4_0-attnQ8_0.gguf from its two public, pinned inputs.

  base    : Unsloth gemma-4-31B-it-qat-UD-Q4_K_XL.gguf (the production file, already on disk)
  edits   : llmfan46's Heretic (ARA) abliterated BF16 weights - only the 26 tensors it changed,
            blk.10-35 attn_output (o_proj), range-fetched from Hugging Face (~2.73 GB)

  Each edited tensor is quantized with llama.cpp's reference Q8_0 (quantize_row_q8_0_ref) and
  replaces the corresponding Q4_0 tensor. Every other tensor and every metadata entry is copied
  from the Unsloth file byte-for-byte - so the current chat template ships inside the output -
  except general.name, plus one added general.description.

  The 26 Q8_0 tensors this produces were verified byte-identical to EZForever's independently made
  gemma-4-31B-it-qat-uncensored-heretic-UDmerge-Q4_K_XXL.gguf (commit 1546c317a1a3).

Requires: Python 3.9+, numpy, curl on PATH.
Usage:    python build-heretic-gguf.py <unsloth UD-Q4_K_XL.gguf> <output.gguf>
"""
import hashlib
import json
import os
import struct
import subprocess
import sys

import numpy as np

LF_REPO = "llmfan46/gemma-4-31B-it-qat-q4_0-unquantized-uncensored-heretic"
LF_COMMIT = "ce415cf3ceaee8f1bdf57563b4dac279da83fcd3"
LF_SHARD = "model-00001-of-00002.safetensors"      # all 26 edited tensors live in shard 1
LF_URL = "https://huggingface.co/%s/resolve/%s/%s" % (LF_REPO, LF_COMMIT, LF_SHARD)
LAYERS = range(10, 36)                               # layers 9 and 36 are unchanged in the BF16
ALIGN = 32
EXPECTED_SHA256 = "05d2e0f8b5ef5ae4b852bdd8ca1504bd276252b958d0bbb3bf6c55022aae8915"
SOURCE_SHA256 = "00b5a7c497f0c8934033088c10a7fa9a4c015e46ee6d89e9c6890650ba5d0e71"   # the Unsloth input

NEW_NAME = "Gemma-4 31B IT QAT Heretic (llmfan46 ARA, attn_output Q8_0)"
DESCRIPTION = (
    "Unsloth gemma-4-31B-it-qat UD-Q4_K_XL (commit 43cc1aeb31adf47ec06a854507ce552cd9862e6f), "
    "with blk.10-35.attn_output.weight replaced by llama.cpp reference Q8_0 of "
    "llmfan46/gemma-4-31B-it-qat-q4_0-unquantized-uncensored-heretic "
    "(commit ce415cf3ceaee8f1bdf57563b4dac279da83fcd3, Heretic v1.2.0 ARA). "
    "Replaced tensors are byte-identical to EZForever UDmerge-Q4_K_XXL (commit 1546c317a1a3). "
    "All other tensors and metadata are Unsloth's, verbatim.")
TY = {0: (1, 4), 2: (32, 18), 8: (32, 34)}          # F32, Q4_0, Q8_0 : (block elems, block bytes)


def fetch(a, n):
    b = subprocess.run(["curl", "-sS", "-L", "--fail", "-m", "1800", "-r", "%d-%d" % (a, a + n - 1), LF_URL],
                       capture_output=True, check=True).stdout
    if len(b) != n:
        raise IOError("short read: %d of %d bytes" % (len(b), n))
    return b


def q8_0(x):
    """llama.cpp quantize_row_q8_0_ref, bit-exact: fp32 arithmetic, roundf, f16 scale."""
    f32 = np.float32
    b = x.reshape(-1, 32).astype(f32)
    d = (np.abs(b).max(1) / f32(127)).astype(f32)
    inv = np.where(d != 0, f32(1) / np.where(d == 0, f32(1), d), f32(0)).astype(f32)
    v = (b * inv[:, None]).astype(f32)
    q = (np.sign(v) * np.floor(np.abs(v) + f32(0.5))).astype(np.int8)
    out = np.empty((b.shape[0], 34), np.uint8)
    out[:, :2] = d.astype(np.float16).view(np.uint8).reshape(-1, 2)
    out[:, 2:] = q.view(np.uint8)
    return out.tobytes()


class Raw:
    """GGUF v3 header parser that keeps each KV entry's raw bytes, so they can be copied verbatim."""
    SIZES = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}

    def __init__(self, buf):
        self.b, self.o = buf, 0

    def rd(self, fmt):
        v = struct.unpack_from(fmt, self.b, self.o)
        self.o += struct.calcsize(fmt)
        return v[0] if len(v) == 1 else v

    def rstr(self):
        n = self.rd("<Q")
        s = self.b[self.o:self.o + n]
        self.o += n
        return s.decode("utf-8")

    def skip(self, t):
        if t == 8:
            self.o += 8 + struct.unpack_from("<Q", self.b, self.o)[0]
        elif t == 9:
            et, n = self.rd("<I"), self.rd("<Q")
            if et in self.SIZES:
                self.o += n * self.SIZES[et]
            else:
                for _ in range(n):
                    self.skip(et)
        else:
            self.o += self.SIZES[t]


def kv_string(key, val):
    k, v = key.encode(), val.encode()
    return struct.pack("<Q", len(k)) + k + struct.pack("<I", 8) + struct.pack("<Q", len(v)) + v


def align(n):
    return (n + ALIGN - 1) // ALIGN * ALIGN


def main(src, out):
    # 1. the 26 edited tensors, as Q8_0
    hl = struct.unpack("<Q", fetch(0, 8))[0]
    hdr = json.loads(fetch(8, hl))
    base = 8 + hl
    q8 = {}
    for L in LAYERS:
        h = hdr["model.language_model.layers.%d.self_attn.o_proj.weight" % L]
        assert h["dtype"] == "BF16", h
        s, e = h["data_offsets"]
        raw = fetch(base + s, e - s)
        x = (np.frombuffer(raw, np.uint16).astype(np.uint32) << 16).view(np.float32)
        assert np.isfinite(x).all(), "non-finite value in layer %d" % L
        q8["blk.%d.attn_output.weight" % L] = q8_0(x)
        print("  fetched + quantized layer %d" % L, flush=True)

    # 2. parse the Unsloth header
    f = open(src, "rb")
    p = Raw(f.read(64 << 20))
    magic, ver = p.rd("<4sI")
    assert magic == b"GGUF" and ver == 3
    n_t, n_kv = p.rd("<Q"), p.rd("<Q")
    kvs = []
    for _ in range(n_kv):
        s = p.o
        key = p.rstr()
        p.skip(p.rd("<I"))
        kvs.append((key, p.b[s:p.o]))
    assert "general.alignment" not in dict(kvs)
    tensors = []
    for _ in range(n_t):
        name = p.rstr()
        dims = [p.rd("<Q") for _ in range(p.rd("<I"))]
        ty, off = p.rd("<I"), p.rd("<Q")
        tensors.append((name, dims, ty, off))
    src_data = align(p.o)

    # 3. new header: Unsloth KV verbatim (name replaced, description added), recomputed tensor table
    out_kv = [kv_string(k, NEW_NAME) if k == "general.name" else r for k, r in kvs]
    out_kv.append(kv_string("general.description", DESCRIPTION))
    plan, cur = [], 0
    for name, dims, ty, off in tensors:
        n = int(np.prod(dims, dtype=np.int64))
        new_ty = 8 if name in q8 else ty
        be, bb = TY[new_ty]
        nbytes = n // be * bb
        plan.append((name, dims, ty, off, new_ty, nbytes, cur))
        cur = align(cur + nbytes)
    assert sum(1 for x in plan if x[0] in q8) == len(q8) == 26
    head = bytearray(b"GGUF" + struct.pack("<IQQ", 3, n_t, len(out_kv)))
    for r in out_kv:
        head += r
    for name, dims, _, _, new_ty, _, new_off in plan:
        nm = name.encode()
        head += struct.pack("<Q", len(nm)) + nm + struct.pack("<I", len(dims))
        head += b"".join(struct.pack("<Q", d) for d in dims) + struct.pack("<IQ", new_ty, new_off)
    data_start = align(len(head))
    head += b"\0" * (data_start - len(head))

    # 4. write, then atomically rename
    tmp = out + ".partial"
    h = hashlib.sha256()
    with open(tmp, "wb") as w:
        def put(b):
            w.write(b)
            h.update(b)
        put(bytes(head))
        for i, (name, dims, ty, off, new_ty, nbytes, new_off) in enumerate(plan):
            assert w.tell() == data_start + new_off
            if name in q8:
                put(q8[name])
            else:
                f.seek(src_data + off)
                left = nbytes
                while left:
                    b = f.read(min(left, 64 << 20))
                    put(b)
                    left -= len(b)
            if i < len(plan) - 1:
                put(b"\0" * (align(w.tell() - data_start) - (w.tell() - data_start)))
    digest = h.hexdigest()
    os.replace(tmp, out)
    print("wrote %s  sha256 %s" % (out, digest))
    if digest != EXPECTED_SHA256:
        sys.exit("MISMATCH: expected %s - check the Unsloth input is sha256 %s" % (EXPECTED_SHA256, SOURCE_SHA256))
    print("matches the reference build byte-for-byte")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
