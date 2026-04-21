"""DynamoDB table schemas and feature name constants.

Used by:
- infra/localstack/init-aws.sh  (reference for table creation)
- consumer/handler.py           (table names)
- ml/src/                       (feature list for model input)
"""

# ── Table definitions (for programmatic creation if needed) ──

PATIENT_LATEST_FEATURES = {
    "TableName": "patient_latest_features",
    "KeySchema": [
        {"AttributeName": "patient_id", "KeyType": "HASH"},
    ],
    "AttributeDefinitions": [
        {"AttributeName": "patient_id", "AttributeType": "S"},
    ],
    "BillingMode": "PAY_PER_REQUEST",
}

PATIENT_RECENT_PREDICTIONS = {
    "TableName": "patient_recent_predictions",
    "KeySchema": [
        {"AttributeName": "patient_id", "KeyType": "HASH"},
        {"AttributeName": "timestamp", "KeyType": "RANGE"},
    ],
    "AttributeDefinitions": [
        {"AttributeName": "patient_id", "AttributeType": "S"},
        {"AttributeName": "timestamp", "AttributeType": "S"},
    ],
    "BillingMode": "PAY_PER_REQUEST",
}


# ── Feature names ────────────────────────────────────────────

VITAL_SIGNS = ["HR", "O2Sat", "Temp", "SBP", "MAP", "DBP", "Resp", "EtCO2"]
ROLLING_WINDOWS = [6, 12, 24]
ROLLING_STATS = ["mean", "std", "min", "max", "slope"]

# Build the full feature name list used by ML models
FEATURE_NAMES: list[str] = []

for vital in VITAL_SIGNS:
    for window in ROLLING_WINDOWS:
        for stat in ROLLING_STATS:
            FEATURE_NAMES.append(f"{stat}_{vital.lower()}_{window}h")
    FEATURE_NAMES.append(f"missing_{vital.lower()}")

FEATURE_NAMES.extend(["qsofa_score", "sirs_count", "iculos_hours"])

# Total: 8 vitals * 3 windows * 5 stats + 8 missing + 3 clinical = 131 features
EXPECTED_FEATURE_COUNT = len(FEATURE_NAMES)
