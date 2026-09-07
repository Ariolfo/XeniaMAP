"""Validación del use case de descarga S2 (sin Celery ni DB)."""

from app.application.agro.download import StartSentinel2ProjectDownload


def _expect_error(exc_type: type, match: str, **kwargs) -> None:
    uc = StartSentinel2ProjectDownload()
    try:
        uc.execute(**kwargs)
        raise AssertionError(f"expected {exc_type.__name__}")
    except exc_type as exc:
        assert match.lower() in str(exc).lower(), str(exc)


def test_sentinel2_download_requires_dates() -> None:
    _expect_error(
        ValueError,
        "start_date",
        db=None,
        tenant_id=1,
        project_id=1,
        start_date=None,
        end_date=None,
        download_subpath="ext:foo",
        wkt="POLYGON((0 0,1 0,1 1,0 1,0 0))",
        copernicus_configured=True,
        database_url="postgresql://x",
    )


def test_sentinel2_download_requires_credentials() -> None:
    _expect_error(
        RuntimeError,
        "Copernicus",
        db=None,
        tenant_id=1,
        project_id=1,
        start_date="2024-01-01",
        end_date="2024-01-31",
        download_subpath="ext:foo",
        wkt="POLYGON((0 0,1 0,1 1,0 1,0 0))",
        copernicus_configured=False,
        database_url="postgresql://x",
    )


def test_sentinel2_download_requires_ext_subpath() -> None:
    _expect_error(
        ValueError,
        "disco externo",
        db=None,
        tenant_id=1,
        project_id=1,
        start_date="2024-01-01",
        end_date="2024-01-31",
        download_subpath="local/foo",
        wkt="POLYGON((0 0,1 0,1 1,0 1,0 0))",
        copernicus_configured=True,
        database_url="postgresql://x",
    )
