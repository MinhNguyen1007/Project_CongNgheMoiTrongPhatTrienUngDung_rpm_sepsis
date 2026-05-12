"""Drift detection — Evidently AI report so sánh reference vs target.

Reference dataset: sample từ PhysioNet training_setA (đã dùng để train baseline).
Target dataset: vital + lab values trong DB N giờ gần nhất (data "live" từ Kafka stream).

CLI:
    python -m ml.src.drift_detect --mode daily
    python -m ml.src.drift_detect --reference-sample 5000 --hours-window 24

Output: JSON ra stdout (cho scheduler parse) + exit 0/1.
JSON schema:
{
  "drift_share": 0.42,            # tỷ lệ feature drifted [0,1]
  "n_features": 34,
  "n_drifted": 14,
  "ref_period": {"source": "training_setA", "n_rows": 5000},
  "target_period": {"start": "...", "end": "...", "n_rows": 1234},
  "feature_details": {"HR": {"drifted": true, "p_value": 0.001}, ...}
}
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import asyncpg
import pandas as pd

from backend.app.config import settings
from ml.src.preprocess import LAB_COLS, VITAL_COLS, load_psv_files

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Reference path mặc định — full training_setA. Lấy sample ngẫu nhiên trong code.
DEFAULT_REFERENCE_DIR = PROJECT_ROOT / "ml" / "data" / "training_setA"

# Drift chỉ xét cột raw (vitals + labs), KHÔNG xét engineered features. Lý do:
# - User dễ interpret ("HR distribution thay đổi") hơn so với "HR_roll_mean_6h drift".
# - Engineered drift là hệ quả của raw drift → cover bằng raw đủ.
DRIFT_COLUMNS: list[str] = VITAL_COLS + LAB_COLS


def _load_reference(reference_dir: Path, sample_size: int) -> pd.DataFrame:
    """Sample ngẫu nhiên N row từ training data làm reference."""
    if not reference_dir.exists():
        raise FileNotFoundError(f"Reference dir not found: {reference_dir}")

    # Lấy ~50 patient đầu → đủ rows cho sample (each patient ~40 rows = 2000 rows).
    # Sample N row cuối khi đã concat.
    raw = load_psv_files([reference_dir], max_patients=200)
    df = raw[DRIFT_COLUMNS].copy()
    # Drop fully-NaN rows (giờ đầu ICU thường toàn NaN, không informative cho drift).
    df = df.dropna(how="all")
    if len(df) > sample_size:
        df = df.sample(n=sample_size, random_state=42).reset_index(drop=True)
    logger.info("Reference loaded: %d rows", len(df))
    return df


async def _load_target_from_db(hours_window: int) -> tuple[pd.DataFrame, datetime, datetime]:
    """Query Postgres lấy vital trong N giờ qua. Flatten lab_values JSONB."""
    # asyncpg DSN không dùng `postgresql+asyncpg://`, strip dialect prefix.
    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn=dsn)
    try:
        cutoff = datetime.now(UTC) - timedelta(hours=hours_window)
        rows = await conn.fetch(
            """
            SELECT hr, o2sat, temp, sbp, map, dbp, resp, etco2, lab_values, created_at
            FROM vital
            WHERE created_at >= $1
            ORDER BY created_at
            """,
            cutoff,
        )
    finally:
        await conn.close()

    if not rows:
        return pd.DataFrame(columns=DRIFT_COLUMNS), cutoff, datetime.now(UTC)

    data: list[dict[str, Any]] = []
    for r in rows:
        d: dict[str, Any] = {
            "HR": r["hr"],
            "O2Sat": r["o2sat"],
            "Temp": r["temp"],
            "SBP": r["sbp"],
            "MAP": r["map"],
            "DBP": r["dbp"],
            "Resp": r["resp"],
            "EtCO2": r["etco2"],
        }
        # lab_values là JSONB → asyncpg trả về str (JSON). Parse khi cần.
        labs_raw = r["lab_values"]
        if isinstance(labs_raw, str):
            labs = json.loads(labs_raw)
        elif isinstance(labs_raw, dict):
            labs = labs_raw
        else:
            labs = {}
        for lab in LAB_COLS:
            d[lab] = labs.get(lab)
        data.append(d)

    df = pd.DataFrame(data)[DRIFT_COLUMNS]
    df = df.dropna(how="all")

    start = rows[0]["created_at"]
    end = rows[-1]["created_at"]
    logger.info("Target loaded: %d rows from %s to %s", len(df), start, end)
    return df, start, end


def _run_evidently(reference: pd.DataFrame, current: pd.DataFrame) -> dict[str, Any]:
    """Chạy Evidently DataDriftPreset, trả dict kết quả normalized."""
    # Import bên trong function để startup CLI nhanh hơn (Evidently nặng).
    from evidently.metric_preset import DataDriftPreset
    from evidently.report import Report

    report = Report(metrics=[DataDriftPreset()])
    report.run(reference_data=reference, current_data=current)
    result = report.as_dict()

    # Evidently nested: result["metrics"][0]["result"] cho overall summary,
    # tiếp theo có per-column trong "drift_by_columns".
    metric_result = result["metrics"][0]["result"]
    drift_share = float(metric_result.get("share_of_drifted_columns", 0.0))
    n_features = int(metric_result.get("number_of_columns", len(DRIFT_COLUMNS)))
    n_drifted = int(metric_result.get("number_of_drifted_columns", 0))

    # Per-column details: nằm ở metric[1] (ColumnDriftMetric) hoặc trong drift_by_columns.
    # Fallback an toàn nếu structure đổi version.
    feature_details: dict[str, dict[str, Any]] = {}
    try:
        col_drifts = result["metrics"][1]["result"]["drift_by_columns"]
        for col, info in col_drifts.items():
            feature_details[col] = {
                "drifted": bool(info.get("drift_detected", False)),
                "stat_test": info.get("stattest_name"),
                "score": info.get("drift_score"),
            }
    except (IndexError, KeyError, TypeError):
        pass

    return {
        "drift_share": drift_share,
        "n_features": n_features,
        "n_drifted": n_drifted,
        "feature_details": feature_details,
    }


async def run(reference_sample: int, hours_window: int, reference_dir: Path) -> dict[str, Any]:
    """Chạy full pipeline drift check. Return dict JSON-serializable."""
    reference_df = _load_reference(reference_dir, sample_size=reference_sample)

    target_df, target_start, target_end = await _load_target_from_db(hours_window)
    if target_df.empty:
        logger.warning("Target DB rỗng — không có vital trong %d giờ qua", hours_window)
        return {
            "drift_share": 0.0,
            "n_features": len(DRIFT_COLUMNS),
            "n_drifted": 0,
            "ref_period": {"source": str(reference_dir.name), "n_rows": len(reference_df)},
            "target_period": {"start": None, "end": None, "n_rows": 0},
            "feature_details": {},
            "skipped_reason": "empty_target",
        }

    # WHY filter: Evidently raise ValueError nếu một cột toàn NaN ở target
    # (hoặc reference). Lab values rất sparse (>90% NaN ở PhysioNet), với data
    # DB ít rows thì 1 lab có thể tình cờ toàn NaN. Bỏ cột đó khỏi drift check.
    valid_cols = [
        c for c in DRIFT_COLUMNS if target_df[c].notna().any() and reference_df[c].notna().any()
    ]
    dropped = [c for c in DRIFT_COLUMNS if c not in valid_cols]
    if dropped:
        logger.info("Skipping %d cols toàn NaN (ref hoặc target): %s", len(dropped), dropped)

    if not valid_cols:
        return {
            "drift_share": 0.0,
            "n_features": 0,
            "n_drifted": 0,
            "ref_period": {"source": str(reference_dir.name), "n_rows": len(reference_df)},
            "target_period": {
                "start": target_start.isoformat(),
                "end": target_end.isoformat(),
                "n_rows": len(target_df),
            },
            "feature_details": {},
            "skipped_reason": "all_columns_empty",
        }

    drift_result = _run_evidently(reference_df[valid_cols], target_df[valid_cols])
    return {
        **drift_result,
        "skipped_columns": dropped,
        "ref_period": {"source": str(reference_dir.name), "n_rows": len(reference_df)},
        "target_period": {
            "start": target_start.isoformat(),
            "end": target_end.isoformat(),
            "n_rows": len(target_df),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Sepsis drift detection")
    parser.add_argument(
        "--mode",
        choices=["daily", "manual"],
        default="manual",
        help="Chỉ là label trong log, không ảnh hưởng logic.",
    )
    parser.add_argument(
        "--reference-sample",
        type=int,
        default=5000,
        help="Số row sample từ training data làm reference.",
    )
    parser.add_argument(
        "--hours-window",
        type=int,
        default=24,
        help="Số giờ DB data làm target (cutoff = NOW - N hours).",
    )
    parser.add_argument("--reference-dir", type=Path, default=DEFAULT_REFERENCE_DIR)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,  # log ra stderr để stdout sạch JSON cho parser.
    )

    try:
        result = asyncio.run(
            run(
                reference_sample=args.reference_sample,
                hours_window=args.hours_window,
                reference_dir=args.reference_dir,
            )
        )
    except Exception:
        logger.exception("Drift check failed")
        sys.exit(1)

    # In JSON ra stdout (1 dòng) cho scheduler parse.
    print(json.dumps(result, default=str))
    logger.info("Done. drift_share=%.4f", result["drift_share"])


if __name__ == "__main__":
    main()
