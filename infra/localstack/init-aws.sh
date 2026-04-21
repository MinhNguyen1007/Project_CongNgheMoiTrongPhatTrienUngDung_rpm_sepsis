#!/bin/bash
set -euo pipefail

echo "=== Initializing LocalStack AWS resources ==="

# ── Kinesis ────────────────────────────────────────────
awslocal kinesis create-stream \
  --stream-name vital-signs-stream \
  --shard-count 1
echo "[OK] Kinesis stream 'vital-signs-stream'"

# ── DynamoDB ───────────────────────────────────────────
awslocal dynamodb create-table \
  --table-name patient_latest_features \
  --attribute-definitions AttributeName=patient_id,AttributeType=S \
  --key-schema AttributeName=patient_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST
echo "[OK] DynamoDB table 'patient_latest_features'"

awslocal dynamodb create-table \
  --table-name patient_recent_predictions \
  --attribute-definitions \
    AttributeName=patient_id,AttributeType=S \
    AttributeName=timestamp,AttributeType=S \
  --key-schema \
    AttributeName=patient_id,KeyType=HASH \
    AttributeName=timestamp,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST
echo "[OK] DynamoDB table 'patient_recent_predictions'"

# ── S3 ─────────────────────────────────────────────────
awslocal s3 mb s3://raw-data
awslocal s3 mb s3://parquet-data
echo "[OK] S3 buckets 'raw-data', 'parquet-data'"

echo "=== LocalStack initialization complete ==="
