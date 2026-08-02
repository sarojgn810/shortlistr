"""Export/import .shortlistr bundle (db + profile + cv + reports)."""

from __future__ import annotations

import argparse
import os
import shutil
import zipfile
from datetime import datetime

from config import SHORTLISTR_ROOT, DATA_DIR, CV_MD_PATH, PROFILE_PATH
from store import db as store

BUNDLE_EXT = ".shortlistr"


def export_bundle(out_path: str | None = None) -> str:
    store.init_db()
    ts = datetime.now().strftime("%Y%m%d")
    out_path = out_path or os.path.join(SHORTLISTR_ROOT, f"shortlistr-backup-{ts}{BUNDLE_EXT}")
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        db_file = os.path.join(DATA_DIR, "shortlistr.db")
        if os.path.exists(db_file):
            zf.write(db_file, "data/shortlistr.db")
        for rel in ("config/profile.yml", "cv.md", "portals.yml"):
            path = os.path.join(SHORTLISTR_ROOT, rel)
            if os.path.exists(path):
                zf.write(path, rel)
        reports = os.path.join(SHORTLISTR_ROOT, "reports")
        if os.path.isdir(reports):
            for root, _, files in os.walk(reports):
                for f in files:
                    full = os.path.join(root, f)
                    arc = os.path.relpath(full, SHORTLISTR_ROOT)
                    zf.write(full, arc)
    return out_path


def import_bundle(path: str) -> None:
    tmp = os.path.join(DATA_DIR, "_bundle_import")
    if os.path.exists(tmp):
        shutil.rmtree(tmp)
    os.makedirs(tmp, exist_ok=True)
    with zipfile.ZipFile(path, "r") as zf:
        zf.extractall(tmp)
    db_src = os.path.join(tmp, "data", "shortlistr.db")
    if os.path.exists(db_src):
        os.makedirs(DATA_DIR, exist_ok=True)
        shutil.copy2(db_src, os.path.join(DATA_DIR, "shortlistr.db"))
    for rel in ("config/profile.yml", "cv.md", "portals.yml"):
        src = os.path.join(tmp, rel)
        if os.path.exists(src):
            dst = os.path.join(SHORTLISTR_ROOT, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["export", "import"])
    p.add_argument("--path", help="Bundle file path")
    args = p.parse_args(argv)
    if args.action == "export":
        out = export_bundle(args.path)
        print(f"Exported bundle: {out}")
    else:
        if not args.path:
            print("import requires --path", file=__import__("sys").stderr)
            return 1
        import_bundle(args.path)
        print(f"Imported bundle from {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
