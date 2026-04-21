"""Data drift check — compare a reference distribution to a current window.

Keeps the scope deliberately small for the student project: load two
parquet chunks (defaults: training set = reference, validation set =
current), subsample rows to stay fast, run Evidently's ``DataDriftPreset``
over the raw vital-sign columns, and write an HTML report to disk.

Usage::

    python mlops/drift/check.py
    python mlops/drift/check.py --reference data/processed/train.parquet \\
                                --current   data/processed/val.parquet
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

# Columns the streaming consumer actually emits; drift on these is the
# most actionable signal for ICU data.
VITAL_COLUMNS = ["HR", "O2Sat", "Temp", "SBP", "MAP", "DBP", "Resp", "EtCO2"]
DEFAULT_SAMPLE_SIZE = 10_000
REPORT_DIR = Path(__file__).resolve().parent / "reports"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _load(path: Path, sample: int, seed: int) -> pd.DataFrame:
    df = pd.read_parquet(path)
    keep = [c for c in VITAL_COLUMNS if c in df.columns]
    if not keep:
        raise ValueError(f"{path} has none of {VITAL_COLUMNS}")
    df = df[keep]
    if sample and len(df) > sample:
        df = df.sample(n=sample, random_state=seed).reset_index(drop=True)
    logger.info("Loaded %s — %d rows × %d cols", path.name, len(df), len(keep))
    return df


def _post_slack(webhook: str, text: str) -> None:
    """Best-effort POST to a Slack Incoming Webhook. Never raises."""
    try:
        req = urllib.request.Request(
            webhook,
            data=json.dumps({"text": text}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            logger.info("Slack webhook returned %s", resp.status)
    except Exception as exc:
        # Deliberately swallow — the drift report is the primary output and
        # we don't want a Slack outage to fail the scheduled job.
        logger.warning("Slack webhook failed: %s", exc)


def run(
    reference_path: Path,
    current_path: Path,
    sample: int,
    seed: int,
    slack_webhook: str | None = None,
    share_threshold: float = 0.3,
) -> Path:
    try:
        from evidently.metric_preset import DataDriftPreset
        from evidently.report import Report
    except ImportError as exc:
        raise SystemExit(
            "evidently not installed — add `evidently>=0.4` to ml/requirements.txt"
        ) from exc

    reference = _load(reference_path, sample, seed)
    current = _load(current_path, sample, seed)

    report = Report(metrics=[DataDriftPreset()])
    report.run(reference_data=reference, current_data=current)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = REPORT_DIR / f"drift_{stamp}.html"
    report.save_html(str(out))

    # Summary line — `as_dict()` is stable across 0.4.x.
    summary = report.as_dict()
    metrics = summary.get("metrics", [])
    drift = metrics[0].get("result", {}) if metrics else {}
    n_drifted = drift.get("number_of_drifted_columns", 0)
    share = drift.get("share_of_drifted_columns", 0.0)
    dataset_drift = drift.get("dataset_drift", False)

    logger.info(
        "Drift summary: dataset_drift=%s, %d drifted cols (share=%.2f)",
        dataset_drift,
        n_drifted,
        share,
    )
    logger.info("HTML report saved to %s", out)

    if slack_webhook and (dataset_drift or share >= share_threshold):
        _post_slack(
            slack_webhook,
            (
                f":warning: Data drift detected on sepsis pipeline "
                f"(share={share:.2f}, {n_drifted} columns).\n"
                f"Reference: `{reference_path.name}`, "
                f"Current: `{current_path.name}`.\n"
                f"Report: `{out.name}` — see CI artifact."
            ),
        )

    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reference",
        type=Path,
        default=Path("data/processed/train.parquet"),
        help="Reference parquet (training distribution).",
    )
    parser.add_argument(
        "--current",
        type=Path,
        default=Path("data/processed/val.parquet"),
        help="Current parquet (production / newer window).",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=DEFAULT_SAMPLE_SIZE,
        help="Max rows per side (0 = full).",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--slack-webhook",
        type=str,
        default=os.getenv("SLACK_WEBHOOK_URL"),
        help="Slack incoming webhook URL (fallback: $SLACK_WEBHOOK_URL).",
    )
    parser.add_argument(
        "--share-threshold",
        type=float,
        default=0.3,
        help="Notify Slack when share of drifted columns >= this (0..1).",
    )
    args = parser.parse_args()

    for p in (args.reference, args.current):
        if not p.exists():
            logger.error("Missing %s — run `python ml/src/preprocess.py` first.", p)
            return 1

    run(
        args.reference,
        args.current,
        args.sample,
        args.seed,
        slack_webhook=args.slack_webhook,
        share_threshold=args.share_threshold,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
