"""F10: validación de imágenes de upload (magic bytes / decode, no solo extensión)."""

from __future__ import annotations

from io import BytesIO

from PIL import Image, UnidentifiedImageError

# Formatos raster permitidos en landing media (sin SVG).
_FMT_TO_EXT = {
    "PNG": ".png",
    "JPEG": ".jpg",
    "WEBP": ".webp",
    "GIF": ".gif",
}
_FMT_TO_MIME = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
    "GIF": "image/gif",
}
_EXT_ALIASES = {
    ".png": "PNG",
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".webp": "WEBP",
    ".gif": "GIF",
}


class InvalidImageUpload(ValueError):
    """Contenido no es una imagen raster válida / no coincide con la extensión."""


def _looks_like_markup(content: bytes) -> bool:
    head = content[:512].lstrip().lower()
    return (
        head.startswith(b"<")
        or b"<svg" in head
        or b"<!doctype" in head
        or b"<html" in head
        or b"<?xml" in head
    )


def validate_raster_image_bytes(
    content: bytes,
    *,
    claimed_ext: str | None = None,
) -> tuple[str, str]:
    """
    Verifica que ``content`` sea PNG/JPEG/WEBP/GIF decodable.

    Returns:
        (canonical_ext, media_type) p.ej. (".png", "image/png").
    """
    if not content:
        raise InvalidImageUpload("Archivo vacío")
    if _looks_like_markup(content):
        raise InvalidImageUpload("El archivo no es una imagen raster válida")

    try:
        with Image.open(BytesIO(content)) as img:
            img.verify()
        # verify() deja el parser en estado inválido; reabrir y cargar píxeles.
        with Image.open(BytesIO(content)) as img:
            fmt = (img.format or "").upper()
            img.load()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise InvalidImageUpload("El archivo no es una imagen válida") from exc

    if fmt not in _FMT_TO_EXT:
        raise InvalidImageUpload(f"Formato no soportado ({fmt or 'desconocido'})")

    claimed = (claimed_ext or "").strip().lower()
    if claimed:
        expected_fmt = _EXT_ALIASES.get(claimed)
        if expected_fmt is None:
            raise InvalidImageUpload(f"Extensión no permitida ({claimed})")
        if expected_fmt != fmt:
            raise InvalidImageUpload(
                "La extensión no coincide con el contenido de la imagen"
            )

    return _FMT_TO_EXT[fmt], _FMT_TO_MIME[fmt]


def mime_for_image_path(path_suffix: str) -> str:
    fmt = _EXT_ALIASES.get((path_suffix or "").lower())
    if not fmt:
        return "application/octet-stream"
    return _FMT_TO_MIME[fmt]
