"""Pytest root config — expose `data-pipeline/` as an importable path.

The directory name contains a hyphen so it cannot be imported as a
Python package directly; we prepend it to ``sys.path`` so test modules
can do ``from consumer.feature_engineer import FeatureEngineer``.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_PIPELINE = ROOT / "data-pipeline"

if str(DATA_PIPELINE) not in sys.path:
    sys.path.insert(0, str(DATA_PIPELINE))
