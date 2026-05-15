"""Sync PhysioNet data từ S3 về local nếu chưa có.

WHY: EC2 t3.micro không build image (OOM xgboost), không SCP 50MB data mỗi lần.
Upload data 1 lần lên S3 → retrain subprocess pull về local cache nếu trống.

Env vars:
- S3_DATA_BUCKET: tên bucket (vd: sepsis-monitoring-data). None → skip sync.
- S3_DATA_PREFIX: prefix object key (default: "physionet/"). Object key dạng
  "<prefix>training_setA/p000001.psv".
- AWS_REGION: default từ boto3 chain.

Local dev không set S3_DATA_BUCKET → no-op, dùng data đã copy sẵn.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def ensure_data_dirs(data_dirs: list[Path | str], max_files: int | None = 2000) -> None:
    """Đảm bảo các thư mục data có .psv. Nếu trống và có S3_DATA_BUCKET → download.

    Idempotent: chạy lại trên dir đã có data sẽ skip.

    WHY max_files=2000: EC2 t3.micro 1GB RAM — download full 20k files/set quá
    chậm và tốn bộ nhớ. 2000 patients đủ để retrain có ý nghĩa thống kê.
    """
    bucket = os.getenv("S3_DATA_BUCKET")
    if not bucket:
        logger.info("S3_DATA_BUCKET not set, skip S3 sync (assume local data exists)")
        return

    prefix = os.getenv("S3_DATA_PREFIX", "physionet/")

    # Lazy import boto3 — chỉ install trên prod, dev không cần.
    import boto3
    from botocore.exceptions import ClientError

    s3 = boto3.client("s3")

    for d in data_dirs:
        d = Path(d)
        d.mkdir(parents=True, exist_ok=True)
        existing = list(d.glob("p*.psv"))
        if existing:
            logger.info("Dir %s already has %d .psv files, skip", d, len(existing))
            continue

        # Object key prefix tương ứng folder cuối (training_setA hoặc training_setB).
        s3_prefix = f"{prefix}{d.name}/"
        logger.info("Downloading s3://%s/%s → %s (max_files=%s)", bucket, s3_prefix, d, max_files)

        try:
            paginator = s3.get_paginator("list_objects_v2")
            count = 0
            for page in paginator.paginate(Bucket=bucket, Prefix=s3_prefix):
                for obj in page.get("Contents", []):
                    if max_files is not None and count >= max_files:
                        break
                    key = obj["Key"]
                    fname = Path(key).name
                    if not fname.endswith(".psv"):
                        continue
                    s3.download_file(bucket, key, str(d / fname))
                    count += 1
                if max_files is not None and count >= max_files:
                    break
            logger.info("Downloaded %d files into %s", count, d)
            if count == 0:
                raise FileNotFoundError(f"No .psv objects under s3://{bucket}/{s3_prefix}")
        except ClientError as exc:
            logger.error("S3 sync failed for %s: %s", d, exc)
            raise
