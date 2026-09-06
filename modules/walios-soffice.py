"""soffice for walios -- office documents to PDF, headless, from the shell.

walios has no LibreOffice binary: soffice.wasm does not exist, and LibreOffice needs
pthreads this kernel does not expose to guests. What sandpie DOES have is ZetaOffice
(allotropia's LibreOffice-WASM) already booted on the page for the office-file viewer.
This command hands the document out to it and lands the PDF back in the workspace.

Speaks the sandpie frame protocol over fd 1 / fd 0 (the same wire as walios-repl.py):

  guest -> host   \x02 <base64 json> \x03 \n     {"t":"call","id":N,"op":"office","args":{..}}
  host  -> guest  <base64 json> \n                {"t":"reply","id":N, ...}

The walios shell tool strips the frame from the visible output and answers on stdin.
stdin has usually ALREADY hit EOF by then (the tool sends stdin-eof at boot, so a plain
`cat` cannot hang), and the wali worker delivers chunks pushed after EOF ahead of the
EOF -- so the reader below retries an empty read instead of treating it as the end.

Only the LibreOffice command-line shape people actually type is supported:

  soffice [--headless] --convert-to pdf [--outdir DIR] FILE...

Conversion targets other than pdf are refused honestly: the page engine only carries
the *_pdf_Export filters.
"""

import base64
import json
import os
import shutil
import sys
import time

EXTS = ("docx", "doc", "odt", "rtf", "txt", "xlsx", "xls", "ods", "csv",
        "pptx", "ppt", "odp", "odg")
WORKSPACE = "/root"
TMPDIR = "/root/.soffice-tmp"


def _send(obj):
    os.write(1, b"\x02" + base64.b64encode(json.dumps(obj).encode("utf-8")) + b"\x03\n")


def _read_reply(cid, timeout=600.0):
    """Wait for the host's reply line on fd 0. An empty read is EOF-already-seen, not
    the end of the conversation: sleep and read again (the host's chunk lands later)."""
    buf = b""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            chunk = os.read(0, 65536)
        except OSError:
            chunk = b""
        if chunk:
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    m = json.loads(base64.b64decode(line))
                except Exception:
                    continue
                if m.get("t") == "reply" and m.get("id") == cid:
                    return m
            continue
        time.sleep(0.05)
    return {"ok_call": False, "error": "no reply from the host within %ds" % int(timeout)}


def _under_workspace(p):
    p = os.path.abspath(p)
    return p == WORKSPACE or p.startswith(WORKSPACE + "/")


def convert_one(src, outdir, cid):
    src = os.path.abspath(src)
    if not os.path.isfile(src):
        return 1, "Error: source file could not be loaded: %s (no such file)" % src
    ext = os.path.splitext(src)[1].lstrip(".").lower()
    if ext not in EXTS:
        return 1, "Error: %s: .%s is not a document type the PDF export handles (%s)" % (
            src, ext or "?", ", ".join(EXTS))
    staged = None
    if not _under_workspace(src):
        # The host reads the input out of OPFS, which is /root. Anything else (RAM /tmp,
        # the rootfs) has to be staged there first.
        os.makedirs(TMPDIR, exist_ok=True)
        staged = os.path.join(TMPDIR, "in-%d-%s" % (os.getpid(), os.path.basename(src)))
        shutil.copyfile(src, staged)
    out = os.path.join(outdir, os.path.splitext(os.path.basename(src))[0] + ".pdf")
    try:
        _send({"t": "call", "id": cid, "op": "office",
               "args": {"src": staged or src, "out": out}})
        r = _read_reply(cid)
    finally:
        if staged:
            try:
                os.remove(staged)
            except Exception:
                pass
    if not r.get("ok_call"):
        return 1, "Error: %s -> pdf failed: %s" % (src, r.get("error") or "unknown error")
    return 0, "convert %s -> %s using filter : %s" % (src, r.get("out") or out, r.get("filter") or "pdf_Export")


def main(argv):
    files, outdir, target, headless = [], None, None, False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--headless", "--invisible", "--norestore", "--nologo", "--nodefault", "--nolockcheck", "--nofirststartwizard"):
            headless = True
        elif a == "--convert-to":
            i += 1
            target = argv[i] if i < len(argv) else None
        elif a.startswith("--convert-to="):
            target = a.split("=", 1)[1]
        elif a == "--outdir":
            i += 1
            outdir = argv[i] if i < len(argv) else None
        elif a.startswith("--outdir="):
            outdir = a.split("=", 1)[1]
        elif a in ("-h", "--help"):
            sys.stdout.write(__doc__.split("\n\n")[0] + "\n\nUsage: soffice --headless --convert-to pdf [--outdir DIR] FILE...\n")
            return 0
        elif a.startswith("-"):
            sys.stderr.write("soffice: option %s is not supported here (only --convert-to pdf / --outdir)\n" % a)
            return 2
        else:
            files.append(a)
        i += 1
    if not target:
        sys.stderr.write("soffice: this walios build has no GUI. Use: soffice --headless --convert-to pdf [--outdir DIR] FILE...\n")
        return 2
    fmt = target.split(":", 1)[0].lower()
    if fmt != "pdf":
        sys.stderr.write("soffice: only --convert-to pdf is available (the page-side LibreOffice carries the PDF export filters only, not %s)\n" % target)
        return 2
    if not files:
        sys.stderr.write("soffice: no input files\n")
        return 2
    outdir = os.path.abspath(outdir or os.getcwd())
    if not _under_workspace(outdir):
        sys.stderr.write("soffice: --outdir must be under %s (the workspace); %s is RAM-only and the host cannot write there\n" % (WORKSPACE, outdir))
        return 2
    os.makedirs(outdir, exist_ok=True)
    rc = 0
    for n, f in enumerate(files, 1):
        code, msg = convert_one(f, outdir, n)
        (sys.stdout if code == 0 else sys.stderr).write(msg + "\n")
        rc = rc or code
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
