"""MVT / PostGIS para vectores publicados (ADR-001)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("SECRET_KEY", "ci-xeniamap-test-secret-key-do-not-use-in-prod")
os.environ.setdefault("OTP_SIMULATE", "1")

from app.application.agro.layer_mvt import (
    MVT_SOURCE_LAYER,
    RenderLayerMvtTile,
    SyncLayerGeom,
    geometry_geojson_for_postgis,
    layer_geom_meta,
)


def test_geometry_geojson_for_postgis_polygon():
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-74.1, 4.5],
                            [-74.0, 4.5],
                            [-74.0, 4.6],
                            [-74.1, 4.6],
                            [-74.1, 4.5],
                        ]
                    ],
                },
            }
        ],
    }
    raw = geometry_geojson_for_postgis(fc)
    assert raw is not None
    g = json.loads(raw)
    assert g["type"] == "Polygon"


def test_geometry_geojson_for_postgis_multi_features():
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-74.0, 4.5]},
                "properties": {},
            },
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-74.1, 4.6]},
                "properties": {},
            },
        ],
    }
    raw = geometry_geojson_for_postgis(fc)
    assert raw is not None
    assert json.loads(raw)["type"] == "GeometryCollection"


def test_geometry_geojson_empty():
    assert geometry_geojson_for_postgis({"type": "FeatureCollection", "features": []}) is None


def test_sync_layer_geom_no_file(tmp_path: Path):
    layer = MagicMock()
    layer.id = 1
    layer.tenant_id = 1
    layer.project_id = 2
    layer.file_path = str(tmp_path / "missing.geojson")
    layers = MagicMock()
    out = SyncLayerGeom().execute(layers, layer=layer)
    assert out["ok"] is False
    assert out["mvt_ready"] is False
    layers.upsert_geom_geojson.assert_not_called()


def test_sync_layer_geom_writes_postgis(tmp_path: Path):
    gj = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[-74.1, 4.5], [-74.0, 4.5], [-74.0, 4.6], [-74.1, 4.6], [-74.1, 4.5]]
                    ],
                },
            }
        ],
    }
    path = tmp_path / "lote.geojson"
    path.write_text(json.dumps(gj), encoding="utf-8")
    layer = MagicMock()
    layer.id = 9
    layer.tenant_id = 1
    layer.project_id = 2
    layer.file_path = str(path)
    layers = MagicMock()
    layers.geom_meta.return_value = {9: {"mvt_ready": True, "bbox": [-74.1, 4.5, -74.0, 4.6]}}
    out = SyncLayerGeom().execute(layers, layer=layer)
    assert out["ok"] is True
    assert out["mvt_ready"] is True
    assert out["bbox"] == [-74.1, 4.5, -74.0, 4.6]
    layers.upsert_geom_geojson.assert_called_once()


def test_render_mvt_rejects_bad_tile():
    layers = MagicMock()
    layer = MagicMock(id=1, tenant_id=1, project_id=1)
    with pytest.raises(ValueError, match="z fuera"):
        RenderLayerMvtTile().execute(layers, layer=layer, z=99, x=0, y=0)


def test_render_mvt_missing_geom():
    layers = MagicMock()
    layers.geom_meta.return_value = {1: {"mvt_ready": False}}
    layer = MagicMock(id=1, tenant_id=1, project_id=1, file_path="/nope.geojson")
    with patch.object(SyncLayerGeom, "execute", return_value={"ok": False, "mvt_ready": False}):
        with pytest.raises(LookupError, match="layer_geom_missing"):
            RenderLayerMvtTile().execute(layers, layer=layer, z=5, x=10, y=12)


def test_render_mvt_returns_bytes():
    layers = MagicMock()
    layers.geom_meta.return_value = {1: {"mvt_ready": True, "bbox": [-74, 4, -73, 5]}}
    layers.persistence_handle.return_value = object()
    layer = MagicMock(id=1, tenant_id=1, project_id=1)
    tiles = MagicMock()
    tiles.render_layer_mvt_tile.return_value = b"\x1a\x00"
    out = RenderLayerMvtTile(tiles=tiles).execute(
        layers, layer=layer, z=5, x=10, y=12, sync_if_missing=False
    )
    assert out == b"\x1a\x00"
    assert MVT_SOURCE_LAYER == "published"


def test_layer_geom_meta_empty():
    layers = MagicMock()
    layers.geom_meta.return_value = {}
    assert layer_geom_meta(layers, layer_ids=[]) == {}
    layers.geom_meta.assert_called_once_with([])


def test_postgis_st_asmvt_roundtrip():
    """Requiere PostGIS (CI / compose). Inserta geom y genera un tile no vacío en z=0."""
    from sqlalchemy import text

    from app.db.session import SessionLocal
    from app.models.models import Layer, Project, Tenant, User

    db = SessionLocal()
    try:
        db.execute(text("SELECT PostGIS_Version()"))
    except Exception as exc:
        db.close()
        pytest.skip(f"PostGIS no disponible: {exc}")

    suffix = os.getpid()
    try:
        tenant = Tenant(name=f"mvt-test-tenant-{suffix}")
        db.add(tenant)
        db.flush()
        user = User(
            email=f"mvt-{suffix}@example.com",
            hashed_password="x",
            full_name="MVT",
            role="admin",
            tenant_id=tenant.id,
        )
        db.add(user)
        db.flush()
        project = Project(name=f"mvt-{suffix}", tenant_id=tenant.id, owner_user_id=user.id)
        db.add(project)
        db.flush()
        layer = Layer(
            project_id=project.id,
            tenant_id=tenant.id,
            name="poly.geojson",
            file_path="/tmp/mvt-test.geojson",
            geom_type="Vector",
            layer_metadata={},
        )
        db.add(layer)
        db.commit()
        db.refresh(layer)

        gj = {
            "type": "Polygon",
            "coordinates": [
                [[-74.1, 4.5], [-74.0, 4.5], [-74.0, 4.6], [-74.1, 4.6], [-74.1, 4.5]]
            ],
        }
        db.execute(
            text(
                """
                UPDATE layers
                SET geom = ST_SetSRID(ST_MakeValid(ST_GeomFromGeoJSON(:gj)), 4326)
                WHERE id = :id
                """
            ),
            {"gj": json.dumps(gj), "id": layer.id},
        )
        db.commit()

        from app.infrastructure.persistence.sqlalchemy_layer_repository import (
            SqlAlchemyLayerRepository,
        )

        layers = SqlAlchemyLayerRepository(db)
        meta = layer_geom_meta(layers, layer_ids=[layer.id])
        assert meta[layer.id]["mvt_ready"] is True
        assert meta[layer.id]["bbox"] is not None

        tile = RenderLayerMvtTile().execute(
            layers, layer=layer, z=0, x=0, y=0, sync_if_missing=False
        )
        assert isinstance(tile, bytes)
        assert len(tile) > 0
    finally:
        try:
            db.execute(text("DELETE FROM layers WHERE tenant_id IN (SELECT id FROM tenants WHERE name LIKE 'mvt-test-tenant-%')"))
            db.execute(text("DELETE FROM projects WHERE name LIKE 'mvt-%'"))
            db.execute(text("DELETE FROM users WHERE email LIKE 'mvt-%@example.com'"))
            db.execute(text("DELETE FROM tenants WHERE name LIKE 'mvt-test-tenant-%'"))
            db.commit()
        except Exception:
            db.rollback()
        db.close()
