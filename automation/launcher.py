"""
Cross-platform one-command launcher for Shortlistr (pure stdlib — no bash).

    python -m automation.cli start   # install deps + seed + run stack + open browser
    python -m automation.cli dev     # run stack only (API auto-reload), no install/browser

Replaces scripts/start-local.sh + dev-local.sh so Windows, macOS and Linux behave
identically. Spawns three children (API, dashboard, scheduler) and shuts them all down
cleanly on Ctrl+C, including grandchildren (npm -> node, uvicorn reloader).
"""

from __future__ import annotations

import atexit
import hashlib
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD = os.path.join(ROOT, "dashboard")
IS_WIN = os.name == "nt"

API_HOST = "127.0.0.1"
API_PORT = 8787
DASH_PORT = 3000
API_BASE = f"http://{API_HOST}:{API_PORT}"
API_HEALTH = f"{API_BASE}/health"
DASH_URL = f"http://localhost:{DASH_PORT}"
ONBOARDING_URL = f"{DASH_URL}/onboarding"

MIN_PYTHON = (3, 10)
MIN_NODE = 18

_procs: list[subprocess.Popen] = []


def _log(msg: str = "") -> None:
    print(msg, flush=True)


def _npm_argv(*args: str) -> list[str]:
    """npm is a .cmd shim on Windows and can't be run directly via CreateProcess;
    go through cmd.exe there. On POSIX call the resolved binary."""
    if IS_WIN:
        return ["cmd", "/c", "npm", *args]
    return [shutil.which("npm") or "npm", *args]


# ── prerequisites ──────────────────────────────────────────────────────────────

def check_prereqs(*, auto_install_node: bool = True) -> bool:
    """Verify Python; auto-install Node/npm when missing so ``start`` is one command."""
    from bootstrap.ensure_runtime import ensure_node, ensure_python

    ok = ensure_python()
    if not ensure_node(auto_install=auto_install_node):
        ok = False
    return ok


# ── networking helpers ─────────────────────────────────────────────────────────

def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def _http_ok(url: str, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return 200 <= r.status < 500  # Next '/' may 404 before routes compile
    except Exception:
        return False


def _wait_for(url: str, label: str, tries: int = 60) -> bool:
    for _ in range(tries):
        if _http_ok(url):
            _log(f"  [ok] {label} ready")
            return True
        time.sleep(1)
    _log(f"  [!] {label} did not respond in {tries}s — open it manually.")
    return False


# ── process management ─────────────────────────────────────────────────────────

def _popen(cmd: list[str], *, cwd: str | None = None, env: dict | None = None) -> subprocess.Popen:
    kwargs: dict = {"cwd": cwd, "env": env}
    if IS_WIN:
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    p = subprocess.Popen(cmd, **kwargs)
    _procs.append(p)
    return p


def _shutdown(*_args) -> None:
    # 1) ask nicely
    for p in _procs:
        if p.poll() is None:
            try:
                if IS_WIN:
                    p.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    p.terminate()
            except Exception:
                pass
    # 2) give them a moment
    deadline = time.time() + 6
    for p in _procs:
        try:
            p.wait(timeout=max(0.0, deadline - time.time()))
        except Exception:
            pass
    # 3) force-kill survivors, whole tree (npm -> node, reloader children)
    for p in _procs:
        if p.poll() is None:
            try:
                if IS_WIN:
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)],
                                   capture_output=True)
                else:
                    p.kill()
            except Exception:
                pass


# ── install / seed ─────────────────────────────────────────────────────────────

def _install() -> None:
    """Install Python, Playwright Chromium, and dashboard deps.

    Failures used to be swallowed (`check=False`), so `make start` could print
    "[ok] dependencies installed" and open onboarding with a broken pip tree.
    Pip and npm must succeed; Playwright Chromium is best-effort because the
    HTML résumé path and most discovery still work without a browser binary.
    """
    _log("Installing dependencies (first run can take a few minutes)…")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "-r",
         os.path.join(ROOT, "automation", "requirements.txt")],
        check=True,
    )
    pw = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=False,
    )
    if pw.returncode != 0:
        _log("  [!] Playwright Chromium install failed — apply-assist and some "
             "scrapers will be unavailable until you run: "
             "python3 -m playwright install chromium")
    _install_dashboard_deps()
    _log("  [ok] dependencies installed")


def _dashboard_dep_stamp() -> tuple[str, str]:
    """(stamp file, expected hash) for the current dashboard dependency set.

    The stamp lives inside node_modules on purpose: deleting that directory has
    to mean "reinstall", and a stamp kept outside it would survive and claim the
    packages were still there.
    """
    for name in ("package-lock.json", "package.json"):
        path = os.path.join(DASHBOARD, name)
        if os.path.isfile(path):
            with open(path, "rb") as fh:
                digest = hashlib.sha256(fh.read()).hexdigest()
            break
    else:
        digest = ""
    stamp = os.path.join(DASHBOARD, "node_modules", ".shortlistr-deps")
    return stamp, digest


def _install_dashboard_deps() -> None:
    """npm install when the dependency set has changed, not only when missing.

    This used to run only if node_modules was absent. Python packages reinstall
    on every `start`, so pulling a commit that adds a Python dependency picks it
    up — pulling one that adds a *dashboard* dependency did not, and the app
    would start against a tree missing the new package. That asymmetry is the
    same shape as a `ModuleNotFoundError` on first boot, just harder to read.

    Hashing the lockfile rather than always running npm keeps a normal start
    fast: npm install is a no-op when the tree is current, but not a free one.
    """
    stamp, digest = _dashboard_dep_stamp()
    if os.path.isdir(os.path.dirname(stamp)) and digest:
        try:
            with open(stamp, encoding="utf-8") as fh:
                if fh.read().strip() == digest:
                    return
        except OSError:
            pass

    _log("Installing dashboard packages…")
    subprocess.run(_npm_argv("install"), cwd=DASHBOARD, check=True)

    if digest:
        try:
            os.makedirs(os.path.dirname(stamp), exist_ok=True)
            with open(stamp, "w", encoding="utf-8") as fh:
                fh.write(digest)
        except OSError as exc:
            # A missing stamp only costs an extra npm install next time.
            _log(f"  [!] could not record dashboard dependency stamp: {exc}")


def _seed() -> None:
    try:
        from bootstrap.seed import main as seed_main
        seed_main()
    except Exception as e:  # never let seeding block a run
        _log(f"  [!] seed step skipped: {e}")


# ── main ───────────────────────────────────────────────────────────────────────

def run(install: bool) -> int:
    _log("Shortlistr launcher")
    _log("")
    _log("Checking prerequisites…")
    if not check_prereqs(auto_install_node=install):
        _log("\nFix the items marked [x] above and re-run.")
        return 1

    if install:
        try:
            _install()
        except subprocess.CalledProcessError as e:
            _log(f"\n  [x] Dependency install failed ({e.cmd[0] if e.cmd else 'command'}).")
            _log("  Fix the error above and re-run `make start`.")
            return 1
        _seed()

    # Refuse to start if either port is taken, so the dashboard never silently
    # drifts to :3001 and the URLs we print/open stay correct.
    for _port, _label in ((API_PORT, "API"), (DASH_PORT, "dashboard")):
        if _port_in_use(API_HOST, _port):
            _log(f"  [!] Port {_port} ({_label}) is already in use. "
                 f"Stop the previous run first, then retry.")
            return 1

    env = os.environ.copy()
    api_env = dict(env)
    if not install:  # dev = auto-reload; start = stable serving
        api_env["SHORTLISTR_API_RELOAD"] = "1"

    atexit.register(_shutdown)
    if not IS_WIN:
        signal.signal(signal.SIGTERM, lambda *a: (_shutdown(), sys.exit(0)))

    _log("")
    _log("Starting services:")
    _log(f"  API        {API_BASE}")
    _log(f"  Dashboard  {DASH_URL}")
    _log("  Press Ctrl+C to stop everything.")
    _log("")

    _popen([sys.executable, "-m", "automation.cli", "api"], cwd=ROOT, env=api_env)
    _popen(_npm_argv("run", "dev"), cwd=DASHBOARD, env=env)
    # The API process already runs the scan + worker loop on a daemon thread.
    # Spawning `cli scheduler` here used to double every due tick.

    try:
        _wait_for(API_HEALTH, "API", 45)
        _wait_for(DASH_URL, "Dashboard", 90)
        if install:
            try:
                webbrowser.open(ONBOARDING_URL)
            except Exception:
                pass
        _log("")
        _log(f"  -> Open {ONBOARDING_URL}")
        _log("  Running. Press Ctrl+C to stop.")
        while True:
            for p in _procs:
                if p.poll() is not None:
                    _log("  [!] A service exited — shutting the rest down.")
                    return 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        _log("\nStopping…")
        return 0
    finally:
        _shutdown()


def start(argv=None) -> int:
    """install + seed + run stack + open browser."""
    return run(install=True)


def dev(argv=None) -> int:
    """run stack only (API auto-reload), no install, no browser."""
    return run(install=False)
