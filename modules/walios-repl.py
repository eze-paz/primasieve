"""sandpie walios REPL server — the WARM interpreter behind the walios Python backend.

Runs as the root process inside the walios wasm-OS and stays alive across tool calls,
so module imports (numpy ~2s, pandas ~4s+) and user globals are paid ONCE per session
instead of once per call. Without this, every call re-boots CPython and re-imports.

Wire protocol (both directions, one frame per line, base64'd JSON so no payload can
contain a delimiter):

  guest -> host   \\x02 <base64 json> \\x03 \\n     (written straight to fd 1)
  host  -> guest  <base64 json> \\n                (read from stdin)

Guest frames:  {"t":"ready"}                                   once, at boot
               {"t":"done","id":N,"out":..,"err":..,"ok":bool}  one per run
               {"t":"call","id":M,"op":..,"args":{..}}          host RPC (see below)
Host frames:   {"t":"run","id":N,"code":..,"cwd":..,"timeout":s}
               {"t":"reply","id":M, ...}                        answer to a call

Host RPC exists because the guest must not depend on in-guest TLS: the browser side
already has fetch() plus the /proxy/ route, so pyodide.http.pyfetch and micropip both
call OUT to the host for network instead of opening sockets here.
"""

import ast
import base64
import builtins
import io
import json
import os
import sys
import traceback
import types

_FD = 1
_stdin = sys.stdin.buffer
_real_stdout, _real_stderr = sys.stdout, sys.stderr


def _send(obj):
    os.write(_FD, b"\x02" + base64.b64encode(json.dumps(obj).encode("utf-8")) + b"\x03\n")


def _recv():
    """Read one host frame. Blocks. Returns None on a blank line, raises on EOF."""
    while True:
        line = _stdin.readline()
        if not line:
            raise EOFError("stdin closed")
        line = line.strip()
        if line:
            return json.loads(base64.b64decode(line))


_call_seq = 0


def _hostcall(op, **args):
    """Ask the browser host to do something (network, mostly) and wait for its reply."""
    global _call_seq
    _call_seq += 1
    cid = _call_seq
    _send({"t": "call", "id": cid, "op": op, "args": args})
    while True:
        m = _recv()
        if m.get("t") == "reply" and m.get("id") == cid:
            return m


# ---------------------------------------------------------------- pyodide shim
# Scripts written for the Pyodide backend use pyodide.http.pyfetch for HTTP (there
# are no sockets there). Provide the same surface so those scripts run unchanged.

class _Immediate:
    """Awaitable that produces its value WITHOUT ever suspending.

    Our shims block on a host round-trip inside `_hostcall`, so they never actually
    yield to an event loop — modelling them as coroutines only forced one to exist.
    That mattered: asyncio needs epoll, which needs JSPI, so `await pyfetch(...)` worked
    in the browser but hung forever on the node host. With this, `await` on a shim works
    under any driver, including the trivial one in `_maybe_await`."""

    __slots__ = ("_fn",)

    def __init__(self, fn):
        self._fn = fn

    def __await__(self):
        return self._run()

    def _run(self):
        if False:      # makes this a generator without ever yielding
            yield
        return self._fn()


class _FetchResponse:
    def __init__(self, r):
        self._r = r
        self.status = r.get("status", 0)
        self.url = r.get("url", "")
        self.headers = r.get("headers", {}) or {}

    @property
    def ok(self):
        return 200 <= self.status < 300

    def _body(self):
        return base64.b64decode(self._r.get("body", "") or "")

    def bytes(self):
        return _Immediate(lambda: self._body())

    def text(self):
        return _Immediate(lambda: self._body().decode("utf-8", "replace"))

    def string(self):
        return _Immediate(lambda: self._body().decode("utf-8", "replace"))

    def json(self, **kw):
        return _Immediate(lambda: json.loads(self._body().decode("utf-8", "replace")))

    def memoryview(self):
        return _Immediate(lambda: memoryview(self._body()))

    def raise_for_status(self):
        if not self.ok:
            raise OSError("HTTP %s for %s" % (self.status, self.url))

    def unpack_archive(self, extract_dir=".", format=None):
        return _Immediate(lambda: self._unpack(extract_dir, format))

    def _unpack(self, extract_dir, format):
        import shutil, tempfile
        suffix = ".zip" if (format in (None, "zip")) else "." + str(format)
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fh:
            fh.write(self._body())
            tmp = fh.name
        shutil.unpack_archive(tmp, extract_dir)
        os.unlink(tmp)


def pyfetch(url, **kw):
    """pyodide.http.pyfetch equivalent, served by the host's fetch()."""
    return _Immediate(lambda: _pyfetch_now(url, **kw))


def _pyfetch_now(url, **kw):
    body = kw.get("body")
    if isinstance(body, (bytes, bytearray)):
        body = base64.b64encode(bytes(body)).decode("ascii")
        body_is_b64 = True
    else:
        body_is_b64 = False
    r = _hostcall(
        "fetch",
        url=url,
        method=kw.get("method", "GET"),
        headers=kw.get("headers") or {},
        body=body,
        body_is_b64=body_is_b64,
    )
    if not r.get("ok_call"):
        raise OSError("pyfetch failed for %s: %s" % (url, r.get("error", "unknown error")))
    return _FetchResponse(r)


def _install_pyodide_shim():
    pkg = types.ModuleType("pyodide")
    pkg.__path__ = []
    http = types.ModuleType("pyodide.http")
    http.pyfetch = pyfetch
    http.FetchResponse = _FetchResponse
    pkg.http = http
    ffi = types.ModuleType("pyodide.ffi")

    def _to_py(x, **kw):
        return x

    ffi.to_js = lambda x, **kw: x
    ffi.to_py = _to_py
    pkg.ffi = ffi
    sys.modules["pyodide"] = pkg
    sys.modules["pyodide.http"] = http
    sys.modules["pyodide.ffi"] = ffi


# --------------------------------------------------------------- micropip shim
# Pure-Python wheels only. A C-extension wheel is x86 ELF or emscripten-ABI and
# could never load here, so say so loudly instead of failing deep in an import.

_PIP_DIR = "/tmp/sandpie-pip"


def _pip_dir():
    if _PIP_DIR not in sys.path:
        os.makedirs(_PIP_DIR, exist_ok=True)
        sys.path.insert(0, _PIP_DIR)
    return _PIP_DIR


def _micropip_install(requirements, **kw):
    return _Immediate(lambda: _micropip_install_now(requirements, **kw))


def _micropip_install_now(requirements, **kw):
    import importlib
    import zipfile

    if isinstance(requirements, str):
        requirements = [requirements]
    done = []
    for req in requirements:
        r = _hostcall("pip", name=str(req))
        if not r.get("ok_call"):
            raise ValueError("micropip: %s" % r.get("error", "could not resolve " + str(req)))
        data = base64.b64decode(r.get("body", ""))
        target = _pip_dir()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            bad = [n for n in z.namelist() if n.endswith(".so") or n.endswith(".pyd")]
            if bad:
                raise ValueError(
                    "micropip: %s ships compiled extensions (%s) — those cannot be loaded here. "
                    "walios C extensions must be cross-compiled to wasm ahead of time; only "
                    "pure-Python wheels install at runtime." % (r.get("name", req), bad[0])
                )
            z.extractall(target)
        done.append("%s==%s" % (r.get("name", req), r.get("version", "?")))
    importlib.invalidate_caches()
    return done


def _install_micropip_shim():
    m = types.ModuleType("micropip")
    m.install = _micropip_install

    def _list():
        return _Immediate(lambda: sorted(
            n for n in os.listdir(_PIP_DIR) if not n.endswith(".dist-info")
        ) if os.path.isdir(_PIP_DIR) else [])

    m.list = _list
    m.add_mock_package = lambda *a, **k: None
    sys.modules["micropip"] = m


# ------------------------------------------------------------------- execution

_G = {"__name__": "__main__", "__builtins__": builtins}


def _set_timeout(seconds):
    """Best-effort in-guest deadline. If the OS lacks setitimer the host still has
    its own kill-the-worker timer; this one is nicer because a timeout that fires
    here raises inside Python and KEEPS the warm interpreter alive."""
    try:
        import signal

        def _fire(_sig, _frm):
            raise KeyboardInterrupt("run exceeded %ss" % seconds)

        signal.signal(signal.SIGALRM, _fire)
        signal.setitimer(signal.ITIMER_REAL, float(seconds))
        return True
    except Exception:
        return False


def _clear_timeout():
    try:
        import signal

        signal.setitimer(signal.ITIMER_REAL, 0.0)
    except Exception:
        pass


def _get_loop():
    import asyncio

    loop = _G.get("__sandpie_loop__")
    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        _G["__sandpie_loop__"] = loop
    return loop


def _loop_usable():
    """Can asyncio actually run here? The HOST says so; the guest must not try to find out.

    asyncio needs epoll, which needs JSPI. The browser worker has it, the node host does
    not — and where it is missing the loop BLOCKS rather than failing, so a probe cannot
    be bounded (SIGALRM does not interrupt it). So the host that knows its own capability
    sets SANDPIE_ASYNCIO=1, and everything else falls back to driving coroutines directly.
    """
    return os.environ.get("SANDPIE_ASYNCIO") == "1"


def _drive(coro):
    """Run a coroutine that never suspends, without any event loop."""
    try:
        coro.send(None)
    except StopIteration as stop:
        return stop.value
    coro.close()
    raise RuntimeError(
        "this code needs a running event loop, which is unavailable on this host "
        "(await on our own shims — pyfetch, micropip — works everywhere)"
    )


def _maybe_await(value):
    import inspect

    if not inspect.iscoroutine(value):
        return value
    # Prefer real asyncio wherever it works, so user code keeps full async semantics.
    # Where it does not, fall back to driving the coroutine directly: top-level code that
    # only awaits our shims never suspends, so `await pyfetch(...)` still works there.
    if _loop_usable():
        return _get_loop().run_until_complete(value)
    return _drive(value)


def _execute(src):
    """Run one chunk with Pyodide-ish semantics: top-level await allowed, and a
    trailing expression echoes its repr the way a REPL does."""
    tree = ast.parse(src)
    tail = None
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        tail = ast.Expression(body=tree.body[-1].value)
        ast.copy_location(tail, tree.body[-1])
        tree.body = tree.body[:-1]
    flags = ast.PyCF_ALLOW_TOP_LEVEL_AWAIT
    if tree.body:
        _maybe_await(eval(compile(tree, "<sandpie>", "exec", flags=flags), _G))
    if tail is not None:
        value = _maybe_await(eval(compile(tail, "<sandpie>", "eval", flags=flags), _G))
        if value is not None:
            print(repr(value))


def _run(msg):
    cwd = msg.get("cwd") or "/root"
    try:
        os.makedirs(cwd, exist_ok=True)
        os.chdir(cwd)
    except Exception:
        pass
    out, err = io.StringIO(), io.StringIO()
    sys.stdout, sys.stderr = out, err
    ok = True
    armed = _set_timeout(msg.get("timeout") or 120)
    try:
        _execute(msg.get("code") or "")
    except SystemExit as e:
        if e.code not in (0, None):
            ok = False
            err.write("SystemExit: %s\n" % e.code)
    except KeyboardInterrupt as e:
        ok = False
        err.write("Timed out: %s\nThe interpreter is still warm — imports and globals survived.\n" % e)
    except BaseException:
        ok = False
        traceback.print_exc(file=err)
    finally:
        if armed:
            _clear_timeout()
        sys.stdout, sys.stderr = _real_stdout, _real_stderr
    _send({"t": "done", "id": msg.get("id"), "out": out.getvalue(), "err": err.getvalue(), "ok": ok})


def main():
    _install_pyodide_shim()
    _install_micropip_shim()
    try:
        os.makedirs("/root", exist_ok=True)
        os.chdir("/root")
    except Exception:
        pass
    _send({"t": "ready", "python": sys.version.split()[0]})
    while True:
        try:
            msg = _recv()
        except EOFError:
            return 0
        except Exception as e:
            _send({"t": "done", "id": None, "out": "", "err": "bad frame: %s" % e, "ok": False})
            continue
        if msg.get("t") == "run":
            _run(msg)
        elif msg.get("t") == "shutdown":
            return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
