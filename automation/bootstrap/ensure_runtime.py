"""Ensure Python/Node runtimes for the one-command launcher.

``make start`` / ``python -m automation.cli start`` should work on a fresh
laptop. If Node.js is missing we try, in order:

1. Common install paths (Homebrew, etc.) that may not be on PATH yet
2. The OS package manager (brew / winget) when available and non-interactive
3. A portable Node LTS binary under ``.tools/`` (no admin rights)

Python itself is not auto-installed — the launcher is already running under it.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

MIN_NODE = 18
# Current Node 20 LTS — pinned so portable installs are reproducible.
NODE_LTS_VERSION = "20.19.4"

ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / ".tools"

_EXTRA_PATH_DIRS = (
    "/opt/homebrew/bin",
    "/usr/local/bin",
    str(Path.home() / ".local" / "bin"),
    str(Path.home() / "AppData" / "Roaming" / "npm"),  # Windows npm globals
)


def _log(msg: str = "") -> None:
    print(msg, flush=True)


def _is_windows() -> bool:
    return os.name == "nt"


def _prepend_path(*dirs: str | Path) -> None:
    parts: list[str] = []
    for d in dirs:
        s = str(d)
        if s and os.path.isdir(s) and s not in parts:
            parts.append(s)
    if not parts:
        return
    current = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join(parts + ([current] if current else []))


def _augment_path() -> None:
    """Add common Node install locations + any portable toolchain we already have."""
    extra = [d for d in _EXTRA_PATH_DIRS if os.path.isdir(d)]
    if TOOLS_DIR.is_dir():
        for child in sorted(TOOLS_DIR.iterdir()):
            bin_dir = child / "bin" if (child / "bin").is_dir() else child
            if (bin_dir / ("node.exe" if _is_windows() else "node")).exists():
                extra.append(str(bin_dir))
    _prepend_path(*extra)


def _node_major(node_bin: str) -> int | None:
    try:
        out = subprocess.run(
            [node_bin, "-v"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        ).stdout.strip()
        return int(out.lstrip("v").split(".")[0])
    except Exception:
        return None


def find_node_npm() -> tuple[str | None, str | None, int | None]:
    """Return (node_path, npm_path, major_version) after PATH augmentation."""
    _augment_path()
    node = shutil.which("node")
    if _is_windows() and not node:
        node = shutil.which("node.exe")
    npm = shutil.which("npm")
    if _is_windows() and not npm:
        npm = shutil.which("npm.cmd")
    major = _node_major(node) if node else None
    return node, npm, major


def _node_ok(node: str | None, npm: str | None, major: int | None) -> bool:
    return bool(node and npm and major is not None and major >= MIN_NODE)


def _dist_slug() -> tuple[str, str] | None:
    """Return (platform-arch slug, archive extension) for nodejs.org dist files."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        arch = "x64"
    elif machine in ("aarch64", "arm64"):
        arch = "arm64"
    elif machine in ("i386", "i686", "x86"):
        arch = "x86"
    else:
        return None

    if system == "darwin":
        return f"darwin-{arch}", "tar.gz"
    if system == "linux":
        return f"linux-{arch}", "tar.gz"
    if system == "windows":
        return f"win-{arch}", "zip"
    return None


def _try_package_manager() -> bool:
    """Best-effort brew / winget install. Returns True if node looks usable after."""
    if shutil.which("brew"):
        _log("  Installing Node.js via Homebrew (first time can take a few minutes)…")
        r = subprocess.run(
            ["brew", "install", "node"],
            check=False,
        )
        if r.returncode == 0:
            _augment_path()
            node, npm, major = find_node_npm()
            if _node_ok(node, npm, major):
                _log(f"  [ok] Node installed via Homebrew ({node})")
                return True
        _log("  [!] brew install node failed — trying portable binary…")
        return False

    if _is_windows() and shutil.which("winget"):
        _log("  Installing Node.js LTS via winget…")
        r = subprocess.run(
            [
                "winget",
                "install",
                "-e",
                "--id",
                "OpenJS.NodeJS.LTS",
                "--accept-package-agreements",
                "--accept-source-agreements",
            ],
            check=False,
        )
        if r.returncode == 0:
            # Winget often installs under Program Files — refresh PATH from registry-ish defaults.
            for candidate in (
                r"C:\Program Files\nodejs",
                os.path.expandvars(r"%ProgramFiles%\nodejs"),
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\node"),
            ):
                if os.path.isdir(candidate):
                    _prepend_path(candidate)
            _augment_path()
            node, npm, major = find_node_npm()
            if _node_ok(node, npm, major):
                _log(f"  [ok] Node installed via winget ({node})")
                return True
        _log("  [!] winget install failed — trying portable binary…")
        return False

    return False


def _install_portable_node() -> bool:
    """Download official Node LTS into ``.tools/`` (no admin / sudo)."""
    slug = _dist_slug()
    if not slug:
        _log(f"  [x] No portable Node build for {platform.system()} / {platform.machine()}.")
        return False
    plat_arch, ext = slug
    version = NODE_LTS_VERSION
    name = f"node-v{version}-{plat_arch}"
    url = f"https://nodejs.org/dist/v{version}/{name}.{ext}"
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    archive = TOOLS_DIR / f"{name}.{ext}"
    dest = TOOLS_DIR / name

    if dest.exists() and (
        (dest / "bin" / "node").exists()
        or (dest / "node.exe").exists()
        or (dest / "node").exists()
    ):
        bin_dir = dest / "bin" if (dest / "bin").is_dir() else dest
        _prepend_path(bin_dir)
        node, npm, major = find_node_npm()
        if _node_ok(node, npm, major):
            _log(f"  [ok] Using existing portable Node at {bin_dir}")
            return True

    _log(f"  Downloading Node {version} ({plat_arch})…")
    _log(f"  {url}")
    try:
        urllib.request.urlretrieve(url, archive)  # noqa: S310 — pinned official dist URL
    except Exception as exc:
        _log(f"  [x] Download failed: {exc}")
        return False

    _log("  Extracting…")
    try:
        if ext == "zip":
            with zipfile.ZipFile(archive, "r") as zf:
                zf.extractall(TOOLS_DIR)
        else:
            with tarfile.open(archive, "r:gz") as tf:
                tf.extractall(TOOLS_DIR)
    except Exception as exc:
        _log(f"  [x] Extract failed: {exc}")
        return False
    finally:
        try:
            archive.unlink(missing_ok=True)
        except Exception:
            pass

    if not dest.exists():
        _log(f"  [x] Expected folder missing after extract: {dest}")
        return False

    bin_dir = dest / "bin" if (dest / "bin").is_dir() else dest
    # Ensure node/npm are executable on POSIX.
    if not _is_windows():
        for exe in ("node", "npm", "npx"):
            p = bin_dir / exe
            if p.exists():
                try:
                    p.chmod(p.stat().st_mode | 0o111)
                except Exception:
                    pass

    _prepend_path(bin_dir)
    node, npm, major = find_node_npm()
    if _node_ok(node, npm, major):
        _log(f"  [ok] Portable Node ready ({node})")
        return True
    _log("  [x] Portable Node extracted but node/npm still not usable on PATH.")
    return False


def ensure_node(*, auto_install: bool = True) -> bool:
    """Make sure Node.js {MIN_NODE}+ and npm are available. Returns True on success."""
    node, npm, major = find_node_npm()
    if _node_ok(node, npm, major):
        _log(f"  [ok] Node {subprocess.run([node, '-v'], capture_output=True, text=True, timeout=10).stdout.strip()}")
        return True

    if node and major is not None and major < MIN_NODE:
        _log(f"  [!] Node {major} is too old (need {MIN_NODE}+). Upgrading…")
    elif not node:
        _log("  [!] Node.js not found — installing automatically…")
    elif not npm:
        _log("  [!] npm not found — reinstalling Node.js…")

    if not auto_install:
        return False

    if _try_package_manager():
        return True
    if _install_portable_node():
        return True

    _log("")
    _log("  [x] Could not install Node.js automatically.")
    _log("  Install Node 18+ manually, then re-run:")
    if platform.system() == "Darwin":
        _log("    brew install node")
    elif _is_windows():
        _log("    winget install OpenJS.NodeJS.LTS")
        _log("    or download from https://nodejs.org")
    else:
        _log("    https://nodejs.org  (or: sudo apt install nodejs npm)")
    return False


def ensure_python() -> bool:
    if sys.version_info < (3, 10):
        _log(
            f"  [x] Python 3.10+ required "
            f"(found {sys.version_info.major}.{sys.version_info.minor}). "
            "Get it from https://python.org"
        )
        return False
    _log(f"  [ok] Python {sys.version_info.major}.{sys.version_info.minor}")
    return True
