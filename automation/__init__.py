"""shortlistr Python automation package."""

from __future__ import annotations

import os
import sys

# So `python3 -m automation.*` resolves top-level automation modules (config, paths, …).
_BASE = os.path.dirname(os.path.abspath(__file__))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)
