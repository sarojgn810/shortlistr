#!/usr/bin/env python3
"""Normalize data/pipeline.md section headers to English."""

from __future__ import annotations

import os
import re
import sys

from config import PIPELINE_PATH


def main() -> int:
    if not os.path.exists(PIPELINE_PATH):
        print("No data/pipeline.md found — nothing to normalize.")
        return 0

    text = open(PIPELINE_PATH, encoding="utf-8").read()
    before = text
    text = re.sub(r"^## Pendientes\s*$", "## Pending", text, flags=re.MULTILINE)
    text = re.sub(r"^## Procesadas\s*$", "## Processed", text, flags=re.MULTILINE)

    if text == before:
        print("pipeline.md already uses ## Pending / ## Processed.")
        return 0

    with open(PIPELINE_PATH, "w", encoding="utf-8") as f:
        f.write(text)
    print("Normalized pipeline.md: Pendientes→Pending, Procesadas→Processed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
