"""SoilPlus execute-save encolado (deuda fina post-H6)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.api.v1 import soilplus as soil_mod
from app.tasks.queue_routing import AGRO_TASK_NAMES, queue_for_task


def test_soilplus_task_routed_to_agro():
    assert "tasks.soilplus_execute_save" in AGRO_TASK_NAMES
    assert queue_for_task("tasks.soilplus_execute_save") == "agro"


def test_post_soilplus_execute_save_enqueues():
    jobs = MagicMock()
    jobs.enqueue.return_value = "soil-task-1"
    with patch("app.infrastructure.composition.default_job_queue", return_value=jobs):
        out = soil_mod.post_soilplus_execute_save(
            project_id=9,
            window_size=13,
            cv_engine="fast",
            n_clusters=4,
            fishnet_step=5,
            roi_polygon=None,
            total_samples=10,
            cmap="jet",
            m=2.0,
            db=MagicMock(),
            user=MagicMock(),
            tenant_id=1,
        )
    assert out == {"status": "queued", "task_id": "soil-task-1", "cv_engine": "fast"}
    assert jobs.enqueue.call_args.kwargs["task_name"] == "soilplus_execute_save"
