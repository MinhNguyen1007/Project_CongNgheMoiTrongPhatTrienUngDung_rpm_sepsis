"""Alarm decision logic — shared with training.

Mirrors `ml/src/utility_score._first_consecutive_alarm` so serving and
offline tuning produce identical decisions. Per-patient history is kept
in Redis as a fixed-size deque of recent probas.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import redis.asyncio as redis

HISTORY_KEY = "patient:{pid}:proba_history"
HISTORY_MAX = 48  # keep last 48 hours
META_KEY = "patient:{pid}:meta"  # iculos_hours at first admission


@dataclass
class AlarmDecision:
    alarm: bool
    proba: float
    threshold: float
    consecutive_above: int
    warmup_muted: bool


async def append_proba(r: redis.Redis, patient_id: str, proba: float) -> list[float]:
    """Append proba to rolling history (FIFO, capped). Returns full history."""
    key = HISTORY_KEY.format(pid=patient_id)
    pipe = r.pipeline()
    pipe.rpush(key, str(proba))
    pipe.ltrim(key, -HISTORY_MAX, -1)
    pipe.lrange(key, 0, -1)
    _, _, raw = await pipe.execute()
    return [float(x) for x in raw]


def decide(
    history: list[float],
    iculos_hours: int,
    threshold: float,
    min_consecutive: int,
    warmup_hours: int,
) -> AlarmDecision:
    """Fire alarm iff last `min_consecutive` probas ≥ threshold and past warmup."""
    proba = history[-1] if history else 0.0
    above = [int(p >= threshold) for p in history]
    # count tail consecutive 1s
    streak = 0
    for v in reversed(above):
        if v == 1:
            streak += 1
        else:
            break

    warmup_muted = iculos_hours < warmup_hours
    alarm = not warmup_muted and streak >= min_consecutive and len(history) >= min_consecutive
    return AlarmDecision(
        alarm=alarm,
        proba=proba,
        threshold=threshold,
        consecutive_above=streak,
        warmup_muted=warmup_muted,
    )


async def record_prediction(
    r: redis.Redis,
    patient_id: str,
    timestamp: str,
    decision: AlarmDecision,
) -> None:
    """Append decision to patient's prediction log (last 24 entries)."""
    key = f"patient:{patient_id}:predictions"
    entry = json.dumps(
        {
            "timestamp": timestamp,
            "proba": decision.proba,
            "alarm": decision.alarm,
            "streak": decision.consecutive_above,
        }
    )
    pipe = r.pipeline()
    pipe.rpush(key, entry)
    pipe.ltrim(key, -24, -1)
    await pipe.execute()


async def store_patient_meta(
    r: redis.Redis,
    patient_id: str,
    iculos_hours: int,
) -> None:
    """Update lightweight patient metadata in a Redis hash."""
    key = META_KEY.format(pid=patient_id)
    await r.hset(
        key,
        mapping={
            "patient_id": patient_id,
            "iculos_hours": str(iculos_hours),
        },
    )


async def get_active_patients(r: redis.Redis) -> list[dict]:
    """Scan Redis for all patients with proba history and return summaries."""
    patients: list[dict] = []
    cursor = 0
    while True:
        cursor, keys = await r.scan(cursor, match="patient:*:proba_history", count=100)
        for key in keys:
            pid = key.split(":")[1]
            # Get latest proba
            last_proba_raw = await r.lindex(f"patient:{pid}:proba_history", -1)
            if last_proba_raw is None:
                continue
            latest_proba = float(last_proba_raw)

            # Get latest prediction log entry
            last_pred_raw = await r.lindex(f"patient:{pid}:predictions", -1)
            last_update = ""
            latest_alarm = False
            if last_pred_raw:
                pred = json.loads(last_pred_raw)
                last_update = pred.get("timestamp", "")
                latest_alarm = pred.get("alarm", False)

            # Get iculos from meta
            iculos_hours = 0
            meta = await r.hgetall(META_KEY.format(pid=pid))
            if meta:
                iculos_hours = int(float(meta.get("iculos_hours", "0")))

            patients.append(
                {
                    "patient_id": pid,
                    "latest_proba": latest_proba,
                    "latest_alarm": latest_alarm,
                    "last_update": last_update,
                    "iculos_hours": iculos_hours,
                }
            )

        if cursor == 0:
            break

    # Sort by latest_proba descending
    patients.sort(key=lambda p: p["latest_proba"], reverse=True)
    return patients


async def get_proba_history(r: redis.Redis, patient_id: str) -> list[dict]:
    """Return timestamped proba history for a patient."""
    preds_raw = await r.lrange(f"patient:{patient_id}:predictions", 0, -1)
    result: list[dict] = []
    for raw in preds_raw:
        entry = json.loads(raw)
        result.append(
            {
                "timestamp": entry.get("timestamp", ""),
                "proba": float(entry.get("proba", 0.0)),
                "alarm": entry.get("alarm", False),
                "streak": int(entry.get("streak", 0)),
            }
        )
    return result


async def get_vitals_history(
    r: redis.Redis,
    patient_id: str,
    hours: int = 72,
) -> list[dict]:
    """Return stored vitals for a patient (up to `hours` entries)."""
    key = f"patient:{patient_id}:vitals"
    raw_list = await r.lrange(key, -hours, -1)
    result: list[dict] = []
    for raw in raw_list:
        entry = json.loads(raw)
        result.append(entry)
    return result
