"""Registro Celery task_id ↔ tenant para autorizar task-status."""
from __future__ import annotations

from app.core import celery_task_registry as reg


def test_register_and_get_owner_memory_fallback(monkeypatch):
    monkeypatch.setattr(reg, "_redis", lambda: None)
    reg._mem.clear()
    reg.register_celery_task("task-abc", tenant_id=7, project_id=3)
    owner = reg.get_celery_task_owner("task-abc")
    assert owner == {"tenant_id": 7, "project_id": 3}


def test_unknown_task_returns_none(monkeypatch):
    monkeypatch.setattr(reg, "_redis", lambda: None)
    reg._mem.clear()
    assert reg.get_celery_task_owner("missing") is None


def test_expired_memory_entry(monkeypatch):
    monkeypatch.setattr(reg, "_redis", lambda: None)
    reg._mem.clear()
    reg.register_celery_task("old", tenant_id=1, project_id=2, ttl_sec=1)
    # force expire
    tid = "old"
    payload, _ = reg._mem[tid]
    reg._mem[tid] = (payload, 0)
    assert reg.get_celery_task_owner("old") is None
