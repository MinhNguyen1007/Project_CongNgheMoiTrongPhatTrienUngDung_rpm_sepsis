"""Unit test cho backend/app/scheduler/jobs.py.

Mock toàn bộ I/O: subprocess, AsyncSessionLocal, crud, reload_model. Test
isolate logic phân nhánh:
- drift_share vs threshold → trigger retrain hay không
- promoted vs not promoted → demote + reload hay không
- subprocess rc != 0 → raise RuntimeError
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_session_cm(session_mock: AsyncMock) -> MagicMock:
    """Build async-context-manager mock cho `async with AsyncSessionLocal() as s`.

    Usage:
        session = AsyncMock()
        mock_session_local.return_value = _make_session_cm(session)
    """
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session_mock)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


@patch("backend.app.scheduler.jobs.crud")
@patch("backend.app.scheduler.jobs.AsyncSessionLocal")
@patch("backend.app.scheduler.jobs._run_subprocess")
async def test_drift_check_below_threshold_no_retrain(
    mock_subprocess: AsyncMock,
    mock_session_local: MagicMock,
    mock_crud: MagicMock,
) -> None:
    """drift_share < threshold → save report, KHÔNG spawn retrain."""
    from backend.app.scheduler import jobs

    mock_subprocess.return_value = (
        0,
        json.dumps({
            "drift_share": 0.1,
            "n_features": 30,
            "n_drifted": 3,
            "target_period": {"start": "2026-05-12T00:00:00+00:00",
                              "end": "2026-05-12T01:00:00+00:00"},
        }),
        "",
    )
    session = AsyncMock()
    mock_session_local.return_value = _make_session_cm(session)
    mock_crud.create_drift_report = AsyncMock()

    with patch("backend.app.scheduler.jobs.asyncio.create_task") as mock_task:
        result = await jobs.run_drift_check(reason="manual")

    assert result["drift_share"] == 0.1
    mock_crud.create_drift_report.assert_awaited_once()
    # Drift dưới threshold → tuyệt đối không spawn retrain.
    mock_task.assert_not_called()


@patch("backend.app.scheduler.jobs.crud")
@patch("backend.app.scheduler.jobs.AsyncSessionLocal")
@patch("backend.app.scheduler.jobs._run_subprocess")
async def test_drift_check_above_threshold_triggers_retrain(
    mock_subprocess: AsyncMock,
    mock_session_local: MagicMock,
    mock_crud: MagicMock,
) -> None:
    """drift_share >= threshold → spawn retrain task."""
    from backend.app.scheduler import jobs

    mock_subprocess.return_value = (
        0,
        json.dumps({
            "drift_share": 0.5,
            "n_features": 30,
            "n_drifted": 15,
            "target_period": {"start": "2026-05-12T00:00:00+00:00",
                              "end": "2026-05-12T01:00:00+00:00"},
        }),
        "",
    )
    session = AsyncMock()
    mock_session_local.return_value = _make_session_cm(session)
    mock_crud.create_drift_report = AsyncMock()

    with patch("backend.app.scheduler.jobs.asyncio.create_task") as mock_task:
        await jobs.run_drift_check(reason="daily")

    # 1 task spawn = retrain coroutine. Không inspect coroutine để tránh
    # "coroutine never awaited" warning.
    assert mock_task.call_count == 1
    # Close coroutine để tránh warning unawaited.
    spawned_coro = mock_task.call_args[0][0]
    spawned_coro.close()


@patch("backend.app.scheduler.jobs._run_subprocess")
async def test_drift_check_subprocess_failure_raises(
    mock_subprocess: AsyncMock,
) -> None:
    """Subprocess exit rc != 0 → RuntimeError."""
    from backend.app.scheduler import jobs

    mock_subprocess.return_value = (1, "", "Traceback ... ValueError: bad data")

    with pytest.raises(RuntimeError, match="drift_detect exited 1"):
        await jobs.run_drift_check(reason="manual")


@patch("backend.app.scheduler.jobs.reload_model")
@patch("backend.app.scheduler.jobs.crud")
@patch("backend.app.scheduler.jobs.AsyncSessionLocal")
@patch("backend.app.scheduler.jobs._run_subprocess")
async def test_retrain_promoted_demotes_and_reloads(
    mock_subprocess: AsyncMock,
    mock_session_local: MagicMock,
    mock_crud: MagicMock,
    mock_reload: MagicMock,
) -> None:
    """promoted=True → demote production cũ + upsert status=production + reload."""
    from backend.app.scheduler import jobs

    mock_subprocess.return_value = (
        0,
        json.dumps({
            "reason": "manual",
            "new_version": "4",
            "new_run_id": "run123",
            "new_auroc": 0.88,
            "new_auprc": 0.15,
            "new_utility": 0.85,
            "new_threshold": 0.7,
            "production_auroc_before": 0.84,
            "promoted": True,
            "n_db_rows_added": 1000,
        }),
        "",
    )
    session = AsyncMock()
    mock_session_local.return_value = _make_session_cm(session)
    mock_crud.demote_production_models = AsyncMock()
    mock_crud.upsert_model_version = AsyncMock()

    result = await jobs.run_retrain(reason="manual")

    assert result["promoted"] is True
    mock_crud.demote_production_models.assert_awaited_once_with(session)
    mock_crud.upsert_model_version.assert_awaited_once()
    upsert_kwargs = mock_crud.upsert_model_version.call_args.kwargs
    assert upsert_kwargs["status"] == "production"
    assert upsert_kwargs["version"] == "4"
    assert upsert_kwargs["auroc"] == 0.88
    mock_reload.assert_called_once()


@patch("backend.app.scheduler.jobs.reload_model")
@patch("backend.app.scheduler.jobs.crud")
@patch("backend.app.scheduler.jobs.AsyncSessionLocal")
@patch("backend.app.scheduler.jobs._run_subprocess")
async def test_retrain_not_promoted_skips_demote_and_reload(
    mock_subprocess: AsyncMock,
    mock_session_local: MagicMock,
    mock_crud: MagicMock,
    mock_reload: MagicMock,
) -> None:
    """promoted=False → status=staging, KHÔNG demote, KHÔNG reload."""
    from backend.app.scheduler import jobs

    mock_subprocess.return_value = (
        0,
        json.dumps({
            "reason": "drift",
            "new_version": "5",
            "new_run_id": "run456",
            "new_auroc": 0.80,
            "new_auprc": 0.10,
            "new_utility": 0.75,
            "new_threshold": 0.7,
            "production_auroc_before": 0.84,
            "promoted": False,
            "n_db_rows_added": 50,
        }),
        "",
    )
    session = AsyncMock()
    mock_session_local.return_value = _make_session_cm(session)
    mock_crud.demote_production_models = AsyncMock()
    mock_crud.upsert_model_version = AsyncMock()

    result = await jobs.run_retrain(reason="drift")

    assert result["promoted"] is False
    mock_crud.demote_production_models.assert_not_called()
    mock_crud.upsert_model_version.assert_awaited_once()
    upsert_kwargs = mock_crud.upsert_model_version.call_args.kwargs
    assert upsert_kwargs["status"] == "staging"
    mock_reload.assert_not_called()


@patch("backend.app.scheduler.jobs._run_subprocess")
async def test_retrain_subprocess_failure_raises(
    mock_subprocess: AsyncMock,
) -> None:
    from backend.app.scheduler import jobs

    mock_subprocess.return_value = (2, "", "MemoryError")
    with pytest.raises(RuntimeError, match="retrain exited 2"):
        await jobs.run_retrain(reason="manual")


def test_create_scheduler_has_two_jobs() -> None:
    """Verify scheduler config: daily drift + weekly retrain."""
    from backend.app.scheduler.jobs import create_scheduler

    scheduler = create_scheduler()
    try:
        job_ids = {j.id for j in scheduler.get_jobs()}
        assert job_ids == {"daily_drift_check", "weekly_retrain"}
    finally:
        # Scheduler chưa start nên không cần shutdown, nhưng gọi cho an toàn.
        if scheduler.running:
            scheduler.shutdown(wait=False)
