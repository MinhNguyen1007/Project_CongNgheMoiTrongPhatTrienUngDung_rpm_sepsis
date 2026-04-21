"""Consumer: poll Kinesis, validate, compute features, write to DynamoDB + S3.

Usage:
    python data-pipeline/consumer/handler.py
"""

import json
import logging
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3
import httpx
import redis as sync_redis

# Add data-pipeline/ to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (
    AWS_ACCESS_KEY_ID,
    AWS_ENDPOINT_URL,
    AWS_REGION,
    AWS_SECRET_ACCESS_KEY,
    BACKEND_PREDICT_ENABLED,
    BACKEND_PREDICT_TIMEOUT,
    BACKEND_URL,
    DYNAMODB_FEATURES_TABLE,
    KINESIS_STREAM_NAME,
    REDIS_URL,
    S3_RAW_BUCKET,
)
from consumer.feature_engineer import FeatureEngineer
from consumer.validator import validate_record

DEMOGRAPHIC_MODEL_INPUTS = ("Age", "Gender", "HospAdmTime")
VITAL_KEYS_FOR_STORAGE = ("HR", "O2Sat", "Temp", "SBP", "MAP", "DBP", "Resp")
VITALS_HISTORY_MAX = 168  # keep up to 7 days of hourly vitals

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def _coerce_numeric(value) -> float | None:
    """Convert DynamoDB/JSON-safe value to a finite float, else None."""
    if value is None:
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(num) or math.isinf(num):
        return None
    return num


def _aws_client(service: str):
    return boto3.client(
        service,
        endpoint_url=AWS_ENDPOINT_URL,
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )


def _aws_resource(service: str):
    return boto3.resource(
        service,
        endpoint_url=AWS_ENDPOINT_URL,
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )


class KinesisConsumer:
    """Long-running consumer that polls Kinesis and writes features to DynamoDB."""

    def __init__(self) -> None:
        self.kinesis = _aws_client("kinesis")
        self.s3 = _aws_client("s3")
        dynamodb = _aws_resource("dynamodb")
        self.features_table = dynamodb.Table(DYNAMODB_FEATURES_TABLE)
        self.feature_engineer = FeatureEngineer()

        # Redis client for storing vitals history (sync — consumer is sync)
        self._redis = sync_redis.from_url(REDIS_URL, decode_responses=True)
        logger.info("Redis connected at %s", REDIS_URL)

        self._raw_buffer: list[dict] = []
        self._buffer_flush_size = 100
        self._stats = {
            "processed": 0,
            "invalid": 0,
            "errors": 0,
            "predicted": 0,
            "alarms": 0,
            "predict_errors": 0,
        }

        self._http = (
            httpx.Client(base_url=BACKEND_URL, timeout=BACKEND_PREDICT_TIMEOUT)
            if BACKEND_PREDICT_ENABLED
            else None
        )

    # ── Public ─────────────────────────────────────────

    def run(self) -> None:
        """Poll Kinesis forever, processing records as they arrive."""
        logger.info("Consumer started — stream='%s'", KINESIS_STREAM_NAME)
        shard_iterator = self._get_shard_iterator()

        while True:
            try:
                resp = self.kinesis.get_records(
                    ShardIterator=shard_iterator, Limit=100
                )
                records = resp["Records"]

                if records:
                    for rec in records:
                        self._process_record(rec["Data"])
                    logger.info(
                        "Batch: %d records | processed=%d invalid=%d "
                        "predicted=%d alarms=%d predict_errors=%d",
                        len(records),
                        self._stats["processed"],
                        self._stats["invalid"],
                        self._stats["predicted"],
                        self._stats["alarms"],
                        self._stats["predict_errors"],
                    )

                shard_iterator = resp["NextShardIterator"]
                time.sleep(0.5 if records else 2.0)

            except KeyboardInterrupt:
                logger.info("Shutting down — flushing buffer...")
                self._flush_raw_buffer()
                if self._http is not None:
                    self._http.close()
                self._redis.close()
                break
            except Exception:
                logger.exception("Error in consumer loop")
                self._stats["errors"] += 1
                time.sleep(5)

    # ── Private ────────────────────────────────────────

    def _get_shard_iterator(self) -> str:
        desc = self.kinesis.describe_stream(StreamName=KINESIS_STREAM_NAME)
        shard_id = desc["StreamDescription"]["Shards"][0]["ShardId"]
        resp = self.kinesis.get_shard_iterator(
            StreamName=KINESIS_STREAM_NAME,
            ShardId=shard_id,
            ShardIteratorType="LATEST",
        )
        return resp["ShardIterator"]

    def _process_record(self, raw_data: bytes) -> None:
        record = json.loads(raw_data)
        patient_id = record.get("patient_id")
        if not patient_id:
            logger.warning("Record missing patient_id — skipping")
            self._stats["invalid"] += 1
            return

        is_valid, reason = validate_record(record)
        if not is_valid:
            logger.warning("Invalid record %s: %s", patient_id, reason)
            self._stats["invalid"] += 1
            return

        # Compute rolling features
        features = self.feature_engineer.update(patient_id, record)

        # Persist
        self._write_features(patient_id, features)
        self._store_vitals_redis(patient_id, record)
        self._buffer_raw(record)
        self._stats["processed"] += 1

        logger.debug(
            "OK %s ICULOS=%s qSOFA=%s SIRS=%s",
            patient_id,
            record.get("ICULOS"),
            features.get("qsofa_score"),
            features.get("sirs_count"),
        )

        self._post_prediction(patient_id, record, features)

    def _write_features(self, patient_id: str, features: dict) -> None:
        """Upsert latest features into DynamoDB."""
        item: dict = {
            "patient_id": patient_id,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        for k, v in features.items():
            if v is None:
                continue
            # DynamoDB doesn't support float directly via resource API in
            # all cases — convert to str for Decimal-safe storage
            item[k] = str(v) if isinstance(v, float) else v
        self.features_table.put_item(Item=item)

    def _store_vitals_redis(self, patient_id: str, record: dict) -> None:
        """Push raw vitals into Redis list for backend GET /patients/{id}/vitals."""
        iculos_raw = record.get("ICULOS")
        iculos = 0
        if iculos_raw is not None:
            try:
                iculos = max(0, int(float(iculos_raw)))
            except (TypeError, ValueError):
                pass

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "iculos_hours": iculos,
        }
        for vk in VITAL_KEYS_FOR_STORAGE:
            val = _coerce_numeric(record.get(vk))
            entry[vk.lower()] = val  # hr, o2sat, temp, sbp, map, dbp, resp

        key = f"patient:{patient_id}:vitals"
        pipe = self._redis.pipeline()
        pipe.rpush(key, json.dumps(entry))
        pipe.ltrim(key, -VITALS_HISTORY_MAX, -1)
        pipe.execute()

    def _buffer_raw(self, record: dict) -> None:
        self._raw_buffer.append(record)
        if len(self._raw_buffer) >= self._buffer_flush_size:
            self._flush_raw_buffer()

    def _post_prediction(
        self, patient_id: str, record: dict, features: dict
    ) -> None:
        """POST features to backend /predict. Failures are logged but non-fatal."""
        if self._http is None:
            return

        iculos_raw = record.get("ICULOS")
        if iculos_raw is None:
            return
        try:
            iculos = max(0, int(float(iculos_raw)))
        except (TypeError, ValueError):
            return

        payload_features: dict[str, float] = {}
        for key, value in features.items():
            num = _coerce_numeric(value)
            if num is not None:
                payload_features[key] = num
        for key in DEMOGRAPHIC_MODEL_INPUTS:
            num = _coerce_numeric(record.get(key))
            if num is not None:
                payload_features[key] = num

        try:
            resp = self._http.post(
                "/predict",
                json={
                    "patient_id": patient_id,
                    "iculos_hours": iculos,
                    "features": payload_features,
                },
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            self._stats["predict_errors"] += 1
            logger.warning("predict call failed for %s: %s", patient_id, exc)
            return

        body = resp.json()
        self._stats["predicted"] += 1
        if body.get("alarm"):
            self._stats["alarms"] += 1
            logger.info(
                "ALARM %s proba=%.3f ICULOS=%dh streak=%d",
                patient_id,
                body.get("proba", 0.0),
                iculos,
                body.get("consecutive_above", 0),
            )

    def _flush_raw_buffer(self) -> None:
        if not self._raw_buffer:
            return
        now = datetime.now(timezone.utc)
        key = (
            f"vitals/year={now.year}/month={now.month:02d}/day={now.day:02d}/"
            f"{now.strftime('%H%M%S')}_{len(self._raw_buffer)}.json"
        )
        self.s3.put_object(
            Bucket=S3_RAW_BUCKET,
            Key=key,
            Body=json.dumps(self._raw_buffer).encode("utf-8"),
            ContentType="application/json",
        )
        logger.info(
            "Flushed %d records -> s3://%s/%s",
            len(self._raw_buffer), S3_RAW_BUCKET, key,
        )
        self._raw_buffer.clear()


def main() -> None:
    consumer = KinesisConsumer()
    consumer.run()


if __name__ == "__main__":
    main()
