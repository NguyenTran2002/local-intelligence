"""ZDR log filter for llama-server (2026-10-06). The server log must hold metadata only.

llama-server echoes model output into some warnings - a tool call that fails to parse ("got
exception: ... last read: '<model output>'") and output that misses the expected format (the raw
text dumped on lines without a log prefix). No llama.cpp flag stops that, so the launcher pipes the
server's output through this filter instead of using --log-file:

  llama-server ... --log-prefix --log-timestamps 2>&1 | py -3 zdr-log-filter.py <logfile>

  console : every line, unchanged (a console window is not stored)
  logfile : timestamped lines byte-identical, except
            - "got exception:" / "send_error:" lines: the error text is cut at its first ':' or
              quote or newline (max 120 chars) - the fixed wording stays, the payload goes
            - every other warning/error line: the same cut after its source tag (this also
              catches "unparsed peg-native output: <raw output>"; startup warnings lose detail)
            - any other line longer than 256 bytes: cut to its source tag (legit lines are <= 189)
            - lines without a log prefix (raw dumps): replaced by a count
Ctrl+C is ignored here, so the filter keeps logging the server's shutdown and exits at EOF.

Clean existing logs:  py -3 zdr-log-filter.py --rewrite [--dry-run] <log> [<log> ...]
"""
import os, re, signal, sys

TS = re.compile(rb"^\s*\d+\.\d+\.\d+\.\d+ [A-Z] ")
ANSI = re.compile(rb"\x1b\[[0-9;]*m")
MAX_LINE = 256
MARK = b" [redacted by zdr-log-filter]"


def _safe(text):
    """The fixed wording at the start of an error message, never its payload."""
    m = re.match(rb"[^:\"\\\n{}\[\]']{0,120}", text)       # 120: fits llama.cpp's longest fixed message
    return m.group(0).rstrip() if m else b""


def filter_line(raw):
    """Return (bytes to store, changed?) for one log line (with its line ending), or (None, True)
    for a line without a log prefix (the caller counts those)."""
    end = raw[len(raw.rstrip(b"\r\n")):]
    plain = ANSI.sub(b"", raw[:len(raw) - len(end)])
    if not plain.strip():
        return raw, False
    m = TS.match(plain)
    if not m:
        return None, True
    head, body = plain[:m.end()], plain[m.end():]
    if b"got exception:" in body:
        code = re.search(rb'"code":(\d+)', body)
        msg = re.search(rb'"message":"(.*)', body)
        out = body[:body.index(b"got exception:") + len(b"got exception:")]
        out += b" code=" + (code.group(1) if code else b"?") + b" " + (_safe(msg.group(1)) if msg else b"") + MARK
        return head + out + end, True
    if b"send_error:" in body and b"error: " in body.split(b"send_error:", 1)[1]:
        pre, err = body.split(b"send_error:", 1)
        tid, msg = err.split(b"error: ", 1)
        safe = _safe(msg)
        if safe == msg.rstrip():
            return raw, False                          # nothing after the fixed wording
        return head + pre + b"send_error:" + tid + b"error: " + safe + MARK + end, True
    if head.rstrip().endswith((b" W", b" E")) and b": " in body:
        # any other warning/error: keep "<source tag>: <fixed wording>", cut whatever follows the
        # wording's first ':' / quote / bracket - e.g. "unparsed peg-native output: <raw output>"
        tag, msg = body.split(b": ", 1)
        safe = _safe(msg)
        if safe != msg.rstrip():
            return head + tag + b": " + safe + MARK + end, True
    if len(plain) > MAX_LINE:
        tag = _safe(body)[:60]
        return head + tag + b" [long line redacted by zdr-log-filter: %d bytes]" % len(plain) + end, True
    return raw, False


def stream(logfile):
    signal.signal(signal.SIGINT, signal.SIG_IGN)       # the server owns Ctrl+C; we log to EOF
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, signal.SIG_IGN)
    con, src = sys.stdout.buffer, sys.stdin.buffer
    log, pending = None, 0
    try:
        log = open(logfile, "wb")
    except OSError as e:
        con.write(b"[zdr-log-filter] cannot open log file (%s) - console only\r\n" % str(e).encode()); con.flush()
    for raw in iter(src.readline, b""):
        try:
            con.write(raw); con.flush()
        except OSError:
            pass
        if log is None:
            continue
        try:
            out, _ = filter_line(raw)
            if out is None:
                pending += 1
                continue
            if pending:
                log.write(b"[zdr-log-filter] %d line(s) without a log prefix redacted\r\n" % pending); pending = 0
            log.write(out); log.flush()
        except Exception as e:                         # never pass a line through on error
            try:
                log.write(b"[zdr-log-filter] line dropped (%s)\r\n" % type(e).__name__.encode()); log.flush()
            except OSError:
                pass
    if log:
        if pending:
            log.write(b"[zdr-log-filter] %d line(s) without a log prefix redacted\r\n" % pending)
        log.close()


def rewrite(paths, dry):
    total = 0
    for p in paths:
        data = open(p, "rb").read()
        out, changed, pending = [], 0, 0
        for raw in data.splitlines(keepends=True):
            line, ch = filter_line(raw)
            if line is None:
                pending += 1; changed += 1
                continue
            if pending:
                out.append(b"[zdr-log-filter] %d line(s) without a log prefix redacted\r\n" % pending); pending = 0
            out.append(line); changed += ch
        if pending:
            out.append(b"[zdr-log-filter] %d line(s) without a log prefix redacted\r\n" % pending)
        if not changed:
            continue
        total += changed
        print("%s: %d line(s) %s" % (os.path.basename(p), changed, "would change" if dry else "redacted"))
        if not dry:
            tmp = p + ".zdrtmp"
            with open(tmp, "wb") as f:
                f.write(b"".join(out)); f.flush(); os.fsync(f.fileno())
            os.replace(tmp, p)
    print("total lines %s: %d" % ("to change" if dry else "redacted", total))


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--rewrite":
        dry = "--dry-run" in a
        rewrite([x for x in a[1:] if x != "--dry-run"], dry)
    elif len(a) == 1:
        stream(a[0])
    else:
        sys.exit(__doc__)
