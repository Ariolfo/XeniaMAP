"""Adapter: RasterStoragePort sobre storage_paths."""

from __future__ import annotations

from pathlib import Path

from app.core.storage_paths import _tenant_storage, project_root_path


class DiskRasterStorage:
    def tenant_kind_dir(self, tenant_id: int, project_id: int, kind: str) -> Path:
        return _tenant_storage(tenant_id, project_id, kind)

    def project_root(self, tenant_id: int, project_id: int) -> Path:
        return project_root_path(tenant_id, project_id)
