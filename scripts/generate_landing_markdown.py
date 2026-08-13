#!/usr/bin/env python3
"""Exporta la vista narrativa de la landing a Markdown (estructura vertical)."""

from __future__ import annotations

import argparse
import base64
import json
import re
import shutil
import sys
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import psycopg2
import rasterio
from PIL import Image
from rasterio.enums import Resampling

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.raster_geo import render_raster_preview_png

FRONTEND = REPO_ROOT / "frontend" / "src" / "landing"
STORAGE_DEFAULT = REPO_ROOT / "data" / "storage"

BLOCK_TITLES = {
    "ps": "Alta resolución",
    "s1": "Sentinel 1 - Radar (SAR - Radar de Apertura Sintética) **OBSERVANDO TU FINCA A TRAVÉS DE LAS NUBES**",
    "s2": "Sentinel 2",
}
SENSOR_ORDER = ["ps", "s1", "s2"]
INDEX_DIRS = {"ps": "indecesPS", "s2": "indices", "s1": "s1indices"}
CLUSTER_DIRS = {"ps": "ClusterPS", "s2": "cluster_gmm", "s1": "cluster_s1_gmm"}
RECORTE_DIRS = {"ps": "recortesPS", "s2": "recortes"}
CLUSTER_COLORS = [
    (228, 26, 28),
    (55, 126, 184),
    (77, 175, 74),
    (152, 78, 163),
    (255, 127, 0),
    (255, 255, 51),
    (166, 86, 40),
    (247, 129, 191),
]

# Mosaicos legibles: cada miniatura se escala a TILE (aunque su raster nativo sea pequeño),
# pocas columnas + tile grande para aprovechar el presupuesto ≤ 4.9 MB por .md.
MOSAIC_TILE_MAX_DIM = 800
MOSAIC_MAX_TILES_PER_PAGE = 8
MOSAIC_COLUMNS = 2
MARKDOWN_IMAGE_WIDTH = 1680
MOSAIC_JPEG_QUALITY = 88

INTERACTIVE_SUBTITLE_DEFAULT = (
    "Compare índice y RGB, explore el timelapse y las series de clima."
)
INTERACTIVE_SUBTITLE_S1 = (
    "El análisis de la agricultura con radar (especialmente tecnología SAR - Radar de Apertura Sintética) "
    "utiliza microondas activas para medir la estructura física, biomasa y humedad del suelo y las plantas. "
    "A diferencia de las imágenes ópticas, los datos de radar penetran la nubosidad, la lluvia y la oscuridad, "
    "operando eficazmente las 24 horas. Algo importante en países ubicados en el trópico, como Colombia."
)

LANDING_INDEX_GROUPS = [
    {
        "id": "vigor",
        "title": "Vigor",
        "keys_optical": ["NDVI", "EVI", "KNDVI", "MSAVI2", "MTVI2"],
        "keys_sar": ["RVI", "RFDI"],
        "meaning": "Indican qué tan activa y productiva está la vegetación. Valores altos suelen corresponder a buen vigor.",
    },
    {
        "id": "nutricion",
        "title": "Nutrición",
        "keys_optical": ["CIre", "MCARI", "NDRE", "TGI"],
        "keys_sar": ["VV_VH", "VH_VV"],
        "meaning": "Reflejan clorofila y posibles deficiencias nutricionales. Caídas sostenidas sugieren nutrición limitada.",
    },
    {
        "id": "agua",
        "title": "Agua",
        "keys_optical": ["NDWI"],
        "keys_sar": ["NRPB"],
        "meaning": "Contenido hídrico foliar y estrés por sequía o riego insuficiente.",
    },
    {
        "id": "estructura",
        "title": "Estructura",
        "keys_optical": ["VARI", "GIYI", "RSTRUCTURE"],
        "keys_sar": [],
        "meaning": "Uniformidad del dosel: huecos, plantas faltantes o copas desbalanceadas.",
    },
]

SUBSECTION_DEFS_BASE = [
    ("interactive", "Vista interactiva temporal", INTERACTIVE_SUBTITLE_DEFAULT),
    ("rgb", "Vista temporal visible", "Galería de escenas en color natural (RGB) a lo largo del tiempo."),
    ("indices", "Índices de vegetación", "Índices agrupados por función agronómica."),
    ("clusters", "Clusters generales", "Segmentación GMM por índice y multibanda."),
]
SUBSECTION_DEFS_PS_EXTRA = [
    ("smart-clusters", "Clusters inteligentes", "Clusters espacio-temporales Smart (PlanetScope)."),
    ("agrogeofisica", "Agrogeofísica", "Análisis Soil Plus (Mat) guardado."),
    ("ia", "Informe inteligente", "Texto narrativo del equipo (sin panel IA automático en este proyecto)."),
]


def _js_string_value(raw: str) -> str:
    return (
        raw.strip()
        .removeprefix('"')
        .removesuffix('"')
        .replace("\\n", "\n")
        .replace('\\"', '"')
    )


def load_index_farmer_copy() -> dict[str, dict]:
    """Extrae INDEX_FARMER_COPY desde interpretations.js (sin ejecutar Node)."""
    src = (FRONTEND / "interpretations.js").read_text(encoding="utf-8")
    m = re.search(r"export const INDEX_FARMER_COPY = \{([\s\S]*?)\n\};", src)
    if not m:
        raise RuntimeError("No se encontró INDEX_FARMER_COPY en interpretations.js")
    body = m.group(1)
    out: dict[str, dict] = {}
    for block in re.finditer(
        r"\n\s*([A-Za-z][A-Za-z0-9_]*):\s*\{([\s\S]*?)\n\s*\},",
        body,
    ):
        key = block.group(1)
        inner = block.group(2)
        entry: dict[str, str] = {}
        for field in ("title", "howToRead", "interpretation", "theory", "legendLow", "legendHigh"):
            fm = re.search(rf'{field}:\s*"((?:\\.|[^"\\])*)"', inner)
            if fm:
                entry[field] = _js_string_value(f'"{fm.group(1)}"')
        out[key] = entry
    if not out:
        raise RuntimeError("INDEX_FARMER_COPY vacío tras parseo")
    return out


# CIre es Sentinel-2 (B8/B5); no forma parte de PlanetScope.
OPTICAL_KEYS_BY_SENSOR = {
    "ps": {
        "NDVI",
        "EVI",
        "NDWI",
        "MSAVI2",
        "MTVI2",
        "VARI",
        "TGI",
        "KNDVI",
        "GIYI",
        "MCARI",
        "NDRE",
        "RSTRUCTURE",
    },
    "s2": {"NDVI", "EVI", "NDWI", "CIre", "MCARI"},
}


def index_keys_for_group(group_id: str, sensor_key: str) -> list[str]:
    g = next(x for x in LANDING_INDEX_GROUPS if x["id"] == group_id)
    if sensor_key == "s1":
        return list(g["keys_sar"])
    allow = OPTICAL_KEYS_BY_SENSOR.get(sensor_key) or OPTICAL_KEYS_BY_SENSOR["s2"]
    return [k for k in g["keys_optical"] if k in allow or k.upper() in {x.upper() for x in allow}]


def subsection_defs(sensor_key: str) -> list[tuple[str, str, str]]:
    defs = list(SUBSECTION_DEFS_BASE)
    if sensor_key == "s1":
        defs = [
            (
                suffix,
                title,
                INTERACTIVE_SUBTITLE_S1 if suffix == "interactive" else subtitle,
            )
            for suffix, title, subtitle in defs
        ]
        # Alinea con la landing: RGB S1 describe polarizaciones VV/VH.
        defs = [
            (
                suffix,
                (
                    "Vista temporal de datos de RADAR (Polarización VV y VH - sigma0 dB)"
                    if suffix == "rgb"
                    else title
                ),
                (
                    "Galerías temporales de retrodispersión sigma0 (dB) en polarizaciones VV y VH."
                    if suffix == "rgb"
                    else subtitle
                ),
            )
            for suffix, title, subtitle in defs
        ]
    if sensor_key == "ps":
        defs = defs + list(SUBSECTION_DEFS_PS_EXTRA)
    return defs


def db_connect(database_url: str | None):
    if database_url:
        return psycopg2.connect(database_url)
    return psycopg2.connect(
        host="localhost", port=5433, dbname="xeniamap", user="postgres", password="postgres"
    )


def fetch_project(conn, project_id: int) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, status, tenant_id FROM projects WHERE id = %s", (project_id,))
        row = cur.fetchone()
        if not row:
            raise SystemExit(f"Proyecto {project_id} no encontrado")
        return {"id": row[0], "name": row[1], "status": row[2], "tenant_id": row[3]}


def fetch_landing_texts(conn, project_id: int) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT section_key, COALESCE(NULLIF(published_body, ''), draft_body, '')
            FROM project_landing_texts WHERE project_id = %s
            """,
            (project_id,),
        )
        return {k: v or "" for k, v in cur.fetchall()}


def scan_index_inventory(project_root: Path, sensor_key: str) -> dict[str, dict]:
    idx_root = project_root / INDEX_DIRS[sensor_key]
    out: dict[str, dict] = {}
    if not idx_root.is_dir():
        return out
    for p in sorted(idx_root.rglob("*.tif")):
        if "_cog" in p.name.lower():
            continue
        parts = p.relative_to(idx_root).parts
        if len(parts) < 2:
            continue
        key = parts[0]
        try:
            with rasterio.open(p) as src:
                jd = src.tags().get("BAND_DATES_JSON", "")
                dates = json.loads(jd) if jd else []
                bands = int(src.count)
        except Exception:
            continue
        out[parts[0]] = {
            "index_key": parts[0],
            "relative_path": str(p.relative_to(project_root)),
            "bands": bands,
            "band_dates": [str(d) for d in dates],
        }
    return out


def find_inventory_item(inv: dict[str, dict], index_key: str) -> dict | None:
    target = index_key.upper()
    for k, v in inv.items():
        if k.upper() == target:
            return v
    return None


def find_farmer_copy_key(farmer_copy: dict, index_key: str) -> str:
    target = index_key.upper()
    for k in farmer_copy:
        if k.upper() == target:
            return k
    return index_key


def list_cluster_files(project_root: Path, sensor_key: str) -> list[str]:
    d = project_root / CLUSTER_DIRS[sensor_key]
    if not d.is_dir():
        return []
    return sorted(f.name for f in d.glob("*.tif"))


def count_recortes(project_root: Path, sensor_key: str) -> int:
    rel = RECORTE_DIRS.get(sensor_key)
    if not rel:
        if sensor_key == "s1":
            d = project_root / "s1preproceso"
            if d.is_dir():
                return sum(1 for _ in d.glob("*.dim"))
        return 0
    d = project_root / rel
    if not d.is_dir():
        return 0
    return sum(1 for _ in d.rglob("*.tif"))


def safe_slug(value: str, fallback: str = "imagen") -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "")).strip("_")
    return slug[:140] or fallback


def image_markdown(label: str, relative_path: str, *, width: int = MARKDOWN_IMAGE_WIDTH) -> list[str]:
    """Imagen a ancho fijo grande para que mosaicos y charts se lean bien en el .md."""
    safe_alt = str(label or "").replace('"', "'")
    return [
        f'<img src="{relative_path}" alt="{safe_alt}" width="{width}" style="max-width:100%;height:auto;" />',
        "",
        f"_{label}_",
        "",
    ]


def format_caption_date(value: str, *, short: bool = False) -> str:
    """Convierte fechas a DD/MM/YYYY o DD/MM/YY (como en la galería del landing)."""
    text = str(value or "").strip()
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        y, mo, d = m.group(1), m.group(2), m.group(3)
        return f"{d}/{mo}/{y[2:]}" if short else f"{d}/{mo}/{y}"
    m = re.search(r"(\d{2})[-_/](\d{2})[-_/](\d{2,4})", text)
    if m:
        d, mo, y = m.group(1), m.group(2), m.group(3)
        if len(y) == 4:
            return f"{d}/{mo}/{y[2:]}" if short else f"{d}/{mo}/{y}"
        return f"{d}/{mo}/{y}"
    m = re.search(r"(\d{8})", text)
    if m:
        ymd = m.group(1)
        d, mo, y = ymd[6:8], ymd[4:6], ymd[0:4]
        return f"{d}/{mo}/{y[2:]}" if short else f"{d}/{mo}/{y}"
    return text or "—"


def sort_key_from_date_text(value: str) -> str:
    """Clave YYYYMMDD para ordenar fechas en captions o nombres de archivo."""
    text = str(value or "")
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        return f"{m.group(1)}{m.group(2)}{m.group(3)}"
    m = re.search(r"(\d{8})", text)
    if m:
        return m.group(1)
    m = re.search(r"(\d{2})[-_/](\d{2})[-_/](\d{2,4})", text)
    if m:
        d, mo, y = m.group(1), m.group(2), m.group(3)
        if len(y) == 2:
            y = f"20{y}"
        return f"{y}{mo}{d}"
    return text


def _data_uri(content: bytes, mime: str = "image/jpeg") -> str:
    return f"data:{mime};base64," + base64.b64encode(content).decode("ascii")


MAX_MD_MB_DEFAULT = 4.9
_DATA_URI_RE = re.compile(r"data:image/(?:png|jpeg);base64,([A-Za-z0-9+/=]+)")


def _recompress_data_uri_b64(b64: str, *, quality: int, scale: float) -> str | None:
    """Reencoda una imagen embebida a JPEG con menor calidad/tamaño. None si no reduce."""
    try:
        raw = base64.b64decode(b64)
        img = Image.open(BytesIO(raw)).convert("RGB")
    except Exception:
        return None
    if scale < 1.0:
        w, h = img.size
        img = img.resize(
            (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
            Image.Resampling.LANCZOS,
        )
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    out = buf.getvalue()
    if len(out) >= len(raw):
        return None
    return _data_uri(out, mime="image/jpeg")


def enforce_markdown_size_limit(md: str, max_bytes: int, *, label: str = "") -> str:
    """
    Garantiza que el Markdown (con imágenes base64) no supere ``max_bytes``.
    Prueba pasos de calidad/escala siempre sobre el original (sin degradar en cascada)
    y elige el más suave que quepa, para aprovechar el presupuesto de 4.9 MB.
    """
    size = len(md.encode("utf-8"))
    if size <= max_bytes:
        return md

    # Preferir calidad alta + resolución: el presupuesto de 4.9 MB se usa al máximo.
    steps = [
        (82, 1.0),
        (74, 1.0),
        (66, 1.0),
        (58, 1.0),
        (55, 0.92),
        (52, 0.88),
        (50, 0.85),
        (48, 0.82),
        (46, 0.80),
        (44, 0.78),
        (42, 0.75),
        (40, 0.72),
        (38, 0.68),
        (35, 0.64),
        (32, 0.58),
        (28, 0.52),
    ]
    original = md
    best = md
    best_size = size
    for quality, scale in steps:

        def _repl(m: re.Match) -> str:
            shrunk = _recompress_data_uri_b64(m.group(1), quality=quality, scale=scale)
            return shrunk if shrunk is not None else m.group(0)

        candidate = _DATA_URI_RE.sub(_repl, original)
        csize = len(candidate.encode("utf-8"))
        print(
            f"Compresión {label or 'md'}: quality={quality} scale={scale} → {csize / (1024 * 1024):.2f} MB"
        )
        if csize <= max_bytes:
            return candidate
        if csize < best_size:
            best, best_size = candidate, csize

    print(
        f"Aviso: {label or 'md'} sigue en {best_size / (1024 * 1024):.2f} MB tras compresión máxima "
        f"(límite {max_bytes / (1024 * 1024):.2f} MB)."
    )
    return best


def _emit_image(
    content: bytes,
    destination: Path,
    output_dir: Path,
    *,
    embed: bool,
    mime: str = "image/jpeg",
) -> str:
    """Devuelve la referencia para el Markdown.

    - ``embed=True``: data URI base64 (imagen dentro del propio .md).
    - ``embed=False``: escribe el archivo en ``assets/`` y devuelve la ruta relativa.
    """
    if embed:
        return _data_uri(content, mime=mime)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return destination.relative_to(output_dir).as_posix()


def _render_raster(
    source: Path,
    *,
    band: int | None = None,
    index_palette: bool = False,
    metadata: dict | None = None,
    max_dim: int = MOSAIC_TILE_MAX_DIM,
) -> Image.Image:
    rgb_bands = (band, band, band) if band is not None else None
    png = render_raster_preview_png(
        source,
        max_dim=max_dim,
        rgb_bands_1based=rgb_bands,
        layer_metadata=metadata,
        index_palette_request=index_palette,
    )
    return Image.open(BytesIO(png)).convert("RGB")


def render_cluster_map_image(source: Path, max_dim: int = MOSAIC_TILE_MAX_DIM) -> Image.Image:
    with rasterio.open(source) as src:
        scale = min(1.0, float(max_dim) / max(src.height, src.width))
        height = max(1, int(round(src.height * scale)))
        width = max(1, int(round(src.width * scale)))
        labels = src.read(1, out_shape=(height, width), resampling=Resampling.nearest)
        nodata = src.nodata
    valid = np.isfinite(labels)
    if nodata is not None:
        valid &= labels != nodata
    rgb = np.full((height, width, 3), 255, dtype=np.uint8)
    for value in np.unique(labels[valid]).tolist():
        cluster_id = int(value)
        if cluster_id < 0:
            continue
        rgb[valid & (labels == value)] = CLUSTER_COLORS[cluster_id % len(CLUSTER_COLORS)]
    return Image.fromarray(rgb, mode="RGB")


def _fit_tile(img: Image.Image | None, target_dim: int = MOSAIC_TILE_MAX_DIM) -> Image.Image | None:
    """Escala cada miniatura a un tamaño objetivo (amplía o reduce) para que se vea grande.

    Los stacks de índices S1/S2 son pequeños en píxeles nativos (p. ej. 168×180); sin
    reescalar quedarían diminutos dentro del mosaico. Aquí se llevan todos a ``target_dim``
    en su lado mayor, preservando la relación de aspecto.
    """
    if img is None:
        return None
    w, h = img.size
    if max(w, h) <= 0:
        return img
    scale = float(target_dim) / max(w, h)
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    if (new_w, new_h) == (w, h):
        return img
    return img.resize((new_w, new_h), Image.Resampling.LANCZOS)


def build_gallery_mosaic(
    tiles: list[tuple[Image.Image | None, str]],
    *,
    columns: int | None = None,
    gap: int = 28,
    caption_h: int = 48,
    quality: int = MOSAIC_JPEG_QUALITY,
) -> bytes:
    """Mosaico tipo galería: pocas columnas + tiles grandes + etiqueta bajo cada miniatura."""
    if not tiles:
        raise ValueError("No hay miniaturas para el mosaico")

    fitted = [(_fit_tile(img), label) for img, label in tiles]
    max_w = 1
    max_h = 1
    for img, _ in fitted:
        if img is None:
            continue
        max_w = max(max_w, img.width)
        max_h = max(max_h, img.height)

    n = len(fitted)
    cols = columns or min(MOSAIC_COLUMNS, max(1, n))
    rows = int(np.ceil(n / cols)) or 1
    min_cell_for_caption = 320
    cell_inner_w = max(max_w, min_cell_for_caption)
    cell_w = cell_inner_w + gap
    cell_h = max_h + caption_h + gap
    canvas = Image.new("RGB", (cols * cell_w + gap, rows * cell_h + gap), "#fafafa")

    try:
        from PIL import ImageDraw, ImageFont

        draw = ImageDraw.Draw(canvas)
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", 22)
        except OSError:
            try:
                font = ImageFont.truetype("DejaVuSans.ttf", 22)
            except OSError:
                font = ImageFont.load_default()
    except Exception:
        draw = None
        font = None

    for i, (img, label) in enumerate(fitted):
        col = i % cols
        row = i // cols
        iw = img.width if img is not None else 0
        ih = img.height if img is not None else 0
        cell_x = gap + col * cell_w
        x0 = cell_x + (cell_inner_w - iw) // 2
        y0 = gap + row * cell_h
        if img is not None:
            canvas.paste(img, (x0, y0))
        elif draw is not None:
            draw.rectangle([x0, y0, x0 + cell_inner_w, y0 + max_h], fill="#e8e8e8")
        if draw is not None:
            line = re.sub(r"\s+", " ", str(label or "—")).strip()
            short = f"{line[:36]}…" if len(line) > 38 else line
            tx = cell_x + cell_inner_w / 2
            ty = y0 + max_h + 12
            draw.text((tx, ty), short, fill="#222222", font=font, anchor="mt")

    buffer = BytesIO()
    canvas.save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()


def _store_mosaic_pages(
    tiles: list[tuple[Image.Image | None, str]],
    destination_stem: Path,
    output_dir: Path,
    *,
    embed: bool,
    label_base: str,
    columns: int | None = None,
    max_per_page: int = MOSAIC_MAX_TILES_PER_PAGE,
) -> list[dict]:
    """Parte series largas en páginas legibles (p. ej. 8 miniaturas = 4×2)."""
    if not tiles:
        return []
    pages: list[dict] = []
    total_pages = int(np.ceil(len(tiles) / max_per_page))
    for page_idx in range(total_pages):
        chunk = tiles[page_idx * max_per_page : (page_idx + 1) * max_per_page]
        cols = columns or min(MOSAIC_COLUMNS, max(1, len(chunk)))
        suffix = "" if total_pages == 1 else f"_p{page_idx + 1}"
        destination = destination_stem.with_name(f"{destination_stem.stem}{suffix}.jpg")
        jpeg = build_gallery_mosaic(chunk, columns=cols)
        ref = _emit_image(jpeg, destination, output_dir, embed=embed, mime="image/jpeg")
        label = label_base if total_pages == 1 else f"{label_base} (parte {page_idx + 1}/{total_pages})"
        pages.append({"label": label, "path": ref})
    return pages


def _soil_dem_height_image(source: Path, max_dim: int = MOSAIC_TILE_MAX_DIM) -> Image.Image:
    """Renderiza el DEM MAT con paleta de alturas y barra en metros."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    with rasterio.open(source) as src:
        arr = src.read(1).astype(np.float64)
        nodata = src.nodata
    valid = np.isfinite(arr)
    if nodata is not None:
        valid &= arr != nodata
    if not np.any(valid):
        raise ValueError(f"DEM sin píxeles válidos: {source}")

    data = np.ma.array(arr, mask=~valid)
    lo = float(np.nanmin(arr[valid]))
    hi = float(np.nanmax(arr[valid]))
    fig_w = max(6.4, max_dim / 100.0)
    fig_h = max(5.2, (max_dim * 0.82) / 100.0)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=120)
    im = ax.imshow(data, cmap="terrain", vmin=lo, vmax=hi, interpolation="nearest")
    ax.set_axis_off()
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Altura (m)", fontsize=12)
    cbar.ax.tick_params(labelsize=10)
    fig.tight_layout(pad=0.2)
    buf = BytesIO()
    fig.savefig(buf, format="PNG", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return Image.open(buf).convert("RGB")


def _soil_cluster_samples_image(source: Path, meta: dict) -> Image.Image:
    """Amplía el cluster MAT y dibuja los puntos de muestreo en su posición."""
    from PIL import ImageDraw

    base = Image.open(source).convert("RGB")
    source_w, source_h = base.size
    target_dim = MOSAIC_TILE_MAX_DIM
    scale = float(target_dim) / max(source_w, source_h, 1)
    out_w = max(1, int(round(source_w * scale)))
    out_h = max(1, int(round(source_h * scale)))
    base = base.resize((out_w, out_h), Image.Resampling.NEAREST)

    shape = meta.get("raster_shape") or {}
    grid_w = max(1, int(shape.get("width") or source_w))
    grid_h = max(1, int(shape.get("height") or source_h))
    sx = out_w / grid_w
    sy = out_h / grid_h
    radius = max(6, int(round(min(sx, sy) * 0.32)))
    draw = ImageDraw.Draw(base)
    for point in meta.get("sample_points") or []:
        try:
            x = (float(point["col"]) + 0.5) * sx
            y = (float(point["row"]) + 0.5) * sy
        except (KeyError, TypeError, ValueError):
            continue
        triangle = [(x, y - radius), (x - radius, y + radius * 0.7), (x + radius, y + radius * 0.7)]
        draw.polygon(triangle, fill="#fff176", outline="white", width=max(2, radius // 4))
    return base


def _centroid_from_project(project_root: Path, conn, project_id: int) -> tuple[float, float] | None:
    """Centroide del AOI desde GeoJSON en vectors/ o file_path de layers."""
    candidates: list[Path] = []
    vectors = project_root / "vectors"
    if vectors.is_dir():
        candidates.extend(sorted(vectors.glob("*.geojson")))
        candidates.extend(sorted(vectors.glob("*.json")))
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT file_path FROM layers WHERE project_id = %s ORDER BY id LIMIT 5",
                (project_id,),
            )
            for (fp,) in cur.fetchall():
                if not fp:
                    continue
                text_path = str(fp)
                p = Path(text_path)
                if text_path.startswith("/data/storage/"):
                    p = STORAGE_DEFAULT / text_path[len("/data/storage/") :]
                if p.is_file():
                    candidates.append(p)
    except Exception:
        pass

    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        coords: list[tuple[float, float]] = []

        def _walk(obj):
            if isinstance(obj, dict):
                t = obj.get("type")
                if t == "Point" and isinstance(obj.get("coordinates"), (list, tuple)):
                    c = obj["coordinates"]
                    if len(c) >= 2:
                        coords.append((float(c[0]), float(c[1])))
                elif t in ("Polygon", "MultiPolygon", "LineString", "MultiLineString"):
                    flat = []

                    def flatten(x):
                        if isinstance(x, (list, tuple)) and x and isinstance(x[0], (int, float)):
                            flat.append(x)
                        elif isinstance(x, (list, tuple)):
                            for y in x:
                                flatten(y)

                    flatten(obj.get("coordinates"))
                    for c in flat:
                        if len(c) >= 2:
                            coords.append((float(c[0]), float(c[1])))
                else:
                    for v in obj.values():
                        _walk(v)
            elif isinstance(obj, list):
                for v in obj:
                    _walk(v)

        _walk(data)
        if not coords:
            continue
        lon = sum(c[0] for c in coords) / len(coords)
        lat = sum(c[1] for c in coords) / len(coords)
        if -180 <= lon <= 180 and -90 <= lat <= 90:
            return lat, lon
    return None


def _open_meteo_monthly_means(lat: float, lon: float, start_date: str, end_date: str) -> dict[str, dict]:
    from urllib.parse import urlencode
    from urllib.request import urlopen

    params = {
        "latitude": f"{lat:.8f}",
        "longitude": f"{lon:.8f}",
        "start_date": start_date,
        "end_date": end_date,
        "timezone": "auto",
        "daily": "temperature_2m_mean,relative_humidity_2m_mean,precipitation_sum,shortwave_radiation_sum",
    }
    url = f"https://archive-api.open-meteo.com/v1/archive?{urlencode(params)}"
    with urlopen(url, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    daily = payload.get("daily") or {}
    times = daily.get("time") or []
    t2m = daily.get("temperature_2m_mean") or []
    rh = daily.get("relative_humidity_2m_mean") or []
    pr = daily.get("precipitation_sum") or []
    sw = daily.get("shortwave_radiation_sum") or []
    n = min(len(times), len(t2m), len(rh), len(pr), len(sw))
    buckets: dict[str, dict[str, list[float]]] = {}
    for i in range(n):
        d = str(times[i])[:10]
        month = d[:7]
        if len(month) != 7:
            continue
        b = buckets.setdefault(month, {"precip": [], "temp": [], "humidity": [], "radiation": []})
        for key, arr in (("temp", t2m), ("humidity", rh), ("precip", pr), ("radiation", sw)):
            v = arr[i] if i < len(arr) else None
            if v is None:
                continue
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            if np.isfinite(fv):
                b[key].append(fv)
    out: dict[str, dict] = {}
    for month, b in buckets.items():
        out[month] = {k: (float(np.mean(vals)) if vals else None) for k, vals in b.items()}
    return out


def build_climate_series_for_dates(scene_dates: list[str], monthly: dict[str, dict]) -> list[dict]:
    rows = []
    for d in scene_dates:
        nd = str(d)[:10]
        month = nd[:7]
        row = monthly.get(month) or {}
        rows.append(
            {
                "date": nd,
                "precip": row.get("precip"),
                "temp": row.get("temp"),
                "humidity": row.get("humidity"),
                "radiation": row.get("radiation"),
            }
        )
    return rows


def render_climate_chart_png(series: list[dict], *, width: int = 1600, height: int = 480) -> bytes:
    """Gráfico dual-eje (precipitación + temperatura), como en la vista interactiva PS."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    dates = [str(r.get("date") or "")[:10] for r in series]
    precip = [r.get("precip") for r in series]
    temp = [r.get("temp") for r in series]
    xs = np.arange(len(dates))

    fig, ax_left = plt.subplots(figsize=(width / 100, height / 100), dpi=100)
    ax_right = ax_left.twinx()
    fig.patch.set_facecolor("white")
    ax_left.set_facecolor("white")

    ax_left.plot(
        xs, precip, color="#1976d2", linewidth=2.2, label="Precipitación", marker="o", markersize=4
    )
    ax_right.plot(
        xs, temp, color="#e65100", linewidth=2.2, label="Temperatura", marker="o", markersize=4
    )

    ax_left.set_ylabel("Eje izq: Precipitación / Radiación", color="#6b7280", fontsize=10)
    ax_right.set_ylabel("Eje der: Temperatura / Humedad", color="#6b7280", fontsize=10)
    ax_left.tick_params(axis="y", labelsize=9, colors="#6b7280")
    ax_right.tick_params(axis="y", labelsize=9, colors="#6b7280")
    ax_left.grid(True, axis="y", color="#e5e7eb", linewidth=1)

    step = max(1, int(np.ceil(len(dates) / 8)))
    tick_idx = list(range(0, len(dates), step))
    if dates and (len(dates) - 1) not in tick_idx:
        tick_idx.append(len(dates) - 1)
    labels = []
    for i in tick_idx:
        d = dates[i]
        labels.append(f"{d[5:7]}/{d[2:4]}" if len(d) >= 7 else d)
    ax_left.set_xticks(tick_idx)
    ax_left.set_xticklabels(labels, fontsize=9, color="#4b5563")

    lines_l, labs_l = ax_left.get_legend_handles_labels()
    lines_r, labs_r = ax_right.get_legend_handles_labels()
    ax_left.legend(
        lines_l + lines_r, labs_l + labs_r, loc="lower center", ncol=2, fontsize=9, frameon=False
    )

    fig.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format="PNG", dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def export_landing_images(
    project_root: Path,
    output_dir: Path,
    inventories: dict[str, dict[str, dict]],
    *,
    embed: bool = True,
    climate_ps: list[dict] | None = None,
) -> tuple[dict, list[str]]:
    """Materializa mosaicos legibles (páginas de hasta 12) e imagen climática PS."""
    assets_root = output_dir / "assets"
    if assets_root.exists():
        shutil.rmtree(assets_root)
    if not embed:
        assets_root.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    exported: dict = {
        "rgb": {sk: [] for sk in SENSOR_ORDER},
        "indices": {sk: {} for sk in SENSOR_ORDER},
        "clusters": {sk: [] for sk in SENSOR_ORDER},
        "smart": [],
        "soil": [],
        "climate": {sk: [] for sk in SENSOR_ORDER},
    }

    for sensor_key, dirname in RECORTE_DIRS.items():
        root = project_root / dirname
        if not root.is_dir():
            continue
        sources: list[tuple[str, Path]] = []
        for source in root.rglob("*.tif"):
            if "udm" in source.name.lower() or "_cog" in source.name.lower():
                continue
            sources.append((sort_key_from_date_text(source.stem), source))
        sources.sort(key=lambda x: (x[0], x[1].name))
        tiles: list[tuple[Image.Image | None, str]] = []
        for _date_key, source in sources:
            date_label = format_caption_date(source.stem, short=True)
            caption = f"PS_{date_label}" if sensor_key == "ps" else f"{sensor_key.upper()}_{date_label}"
            try:
                metadata = {"planetscope_composite": True} if sensor_key == "ps" else None
                tiles.append((_render_raster(source, metadata=metadata), caption))
            except Exception as exc:
                warnings.append(f"RGB {source.name}: {exc}")
                tiles.append((None, caption))
        if tiles:
            destination = assets_root / sensor_key / "rgb" / f"{sensor_key}_rgb_mosaic.jpg"
            try:
                exported["rgb"][sensor_key] = _store_mosaic_pages(
                    tiles,
                    destination,
                    output_dir,
                    embed=embed,
                    label_base=f"Galería temporal RGB ({sensor_key.upper()})",
                )
            except Exception as exc:
                warnings.append(f"Mosaico RGB {sensor_key}: {exc}")

    s1_root = project_root / "s1preproceso"
    if s1_root.is_dir():
        tiles = []
        dated: list[tuple[str, Path]] = []
        for source in s1_root.rglob("Sigma0_VV_db.img"):
            date_match = re.search(r"_(\d{8})T\d{6}_", source.as_posix())
            raw = date_match.group(1) if date_match else source.parent.name
            dated.append((sort_key_from_date_text(raw), source))
        dated.sort(key=lambda x: (x[0], x[1].as_posix()))
        for _key, source in dated:
            date_match = re.search(r"_(\d{8})T\d{6}_", source.as_posix())
            raw = date_match.group(1) if date_match else source.parent.name
            caption = f"VV · {format_caption_date(raw)}"
            try:
                tiles.append(
                    (
                        _render_raster(
                            source,
                            index_palette=True,
                            metadata={
                                "preview_rgb_bands": [1, 1, 1],
                                "index_preview_cmap": "Spectral_r",
                            },
                        ),
                        caption,
                    )
                )
            except Exception as exc:
                warnings.append(f"S1 VV {source.parent.name}: {exc}")
                tiles.append((None, caption))
        if tiles:
            destination = assets_root / "s1" / "rgb" / "s1_vv_mosaic.jpg"
            try:
                exported["rgb"]["s1"] = _store_mosaic_pages(
                    tiles,
                    destination,
                    output_dir,
                    embed=embed,
                    label_base="Galería temporal Sigma0 VV",
                )
            except Exception as exc:
                warnings.append(f"Mosaico S1 VV: {exc}")

    for sensor_key, inventory in inventories.items():
        for index_key, item in sorted(inventory.items()):
            source = project_root / item["relative_path"]
            dates = item.get("band_dates") or []
            tiles = []
            for band in range(1, int(item.get("bands") or 0) + 1):
                raw = str(dates[band - 1]) if band <= len(dates) else f"banda-{band}"
                caption = f"{index_key} · {format_caption_date(raw)}"
                try:
                    tiles.append((_render_raster(source, band=band, index_palette=True), caption))
                except Exception as exc:
                    warnings.append(f"{sensor_key} {index_key} banda {band}: {exc}")
                    tiles.append((None, caption))
            if not tiles:
                continue
            destination = assets_root / sensor_key / "indices" / f"{safe_slug(index_key)}_mosaic.jpg"
            try:
                exported["indices"][sensor_key][index_key.upper()] = _store_mosaic_pages(
                    tiles,
                    destination,
                    output_dir,
                    embed=embed,
                    label_base=f"Galería temporal {index_key}",
                )
            except Exception as exc:
                warnings.append(f"Mosaico {sensor_key} {index_key}: {exc}")

    for sensor_key, dirname in CLUSTER_DIRS.items():
        root = project_root / dirname
        if not root.is_dir():
            continue
        tiles = []
        for source in sorted(root.glob("*.tif")):
            caption = source.stem.replace("_", " ")
            try:
                tiles.append((render_cluster_map_image(source), caption))
            except Exception as exc:
                warnings.append(f"Cluster {caption}: {exc}")
                tiles.append((None, caption))
        if tiles:
            destination = assets_root / sensor_key / "clusters" / f"{sensor_key}_gmm_mosaic.jpg"
            try:
                exported["clusters"][sensor_key] = _store_mosaic_pages(
                    tiles,
                    destination,
                    output_dir,
                    embed=embed,
                    label_base=f"Clusters GMM ({sensor_key.upper()})",
                )
            except Exception as exc:
                warnings.append(f"Mosaico clusters {sensor_key}: {exc}")

    smart_tiles: list[tuple[Image.Image | None, str]] = []
    for preset in ("smart1", "smart2", "smart3"):
        candidates = [
            project_root / "smart_cluster" / preset / "final_cluster_map.tif",
            project_root
            / ("ps_st_cluster" if preset == "smart1" else f"ps_st_cluster_{preset}")
            / "final_cluster_map.tif",
        ]
        source = next((p for p in candidates if p.is_file()), None)
        if source is None:
            continue
        try:
            smart_tiles.append((render_cluster_map_image(source), f"Cluster inteligente {preset}"))
        except Exception as exc:
            warnings.append(f"Cluster inteligente {preset}: {exc}")
            smart_tiles.append((None, f"Cluster inteligente {preset}"))
    if smart_tiles:
        destination = assets_root / "ps" / "smart" / "smart_clusters_mosaic.jpg"
        try:
            exported["smart"] = _store_mosaic_pages(
                smart_tiles,
                destination,
                output_dir,
                embed=embed,
                label_base="Clusters inteligentes (Smart 1–3)",
                columns=3,
                max_per_page=3,
            )
        except Exception as exc:
            warnings.append(f"Mosaico smart clusters: {exc}")

    # Agrogeofísica del Markdown: exclusivamente MAT y solo DEM altura, CV y cluster
    # con los puntos de muestreo. No incluir Fast, aspect, slope, barras ni curva Q.
    dem_root = project_root / "dem"
    mat_meta_path = dem_root / "soilplus_saved_matlab.json"
    if mat_meta_path.is_file():
        try:
            mat_meta = json.loads(mat_meta_path.read_text(encoding="utf-8"))
        except Exception as exc:
            mat_meta = {}
            warnings.append(f"Soil Plus MAT metadata: {exc}")

        soil_specs: list[tuple[str, Path, Image.Image | None]] = []
        dem_path_text = str(mat_meta.get("dem_input_image_path") or "")
        dem_source = Path(dem_path_text) if dem_path_text else None
        if dem_source is not None and not dem_source.is_file() and dem_path_text.startswith("/data/storage/"):
            # Ejecución local: traducir la ruta persistida por el contenedor al storage del proyecto.
            dem_source = project_root.parents[1] / dem_path_text[len("/data/storage/") :]
        if dem_source is None or not dem_source.is_file():
            dem_source = next(
                (
                    p
                    for p in sorted(dem_root.iterdir())
                    if p.is_file()
                    and p.suffix.lower() in {".tif", ".tiff", ".img"}
                    and not p.name.lower().startswith("soilplus_saved_")
                ),
                None,
            )

        if dem_source is not None:
            try:
                soil_specs.append(
                    (
                        "1. DEM MAT — alturas",
                        assets_root / "ps" / "soil" / "mat_dem_alturas.png",
                        _soil_dem_height_image(dem_source),
                    )
                )
            except Exception as exc:
                warnings.append(f"Soil Plus MAT DEM alturas: {exc}")
        else:
            warnings.append("Soil Plus MAT DEM alturas: no se encontró el DEM de entrada")

        cv_source = dem_root / "soilplus_saved_matlab_cv.png"
        if cv_source.is_file():
            try:
                soil_specs.append(
                    (
                        "2. CV MAT",
                        assets_root / "ps" / "soil" / "mat_cv.png",
                        _fit_tile(Image.open(cv_source).convert("RGB")),
                    )
                )
            except Exception as exc:
                warnings.append(f"Soil Plus MAT CV: {exc}")

        fcm_source = dem_root / "soilplus_saved_matlab_fcm.png"
        if fcm_source.is_file():
            try:
                soil_specs.append(
                    (
                        "3. Cluster MAT con ubicación de puntos",
                        assets_root / "ps" / "soil" / "mat_cluster_puntos.png",
                        _soil_cluster_samples_image(fcm_source, mat_meta),
                    )
                )
            except Exception as exc:
                warnings.append(f"Soil Plus MAT cluster con puntos: {exc}")

        for label, destination, image in soil_specs:
            if image is None:
                continue
            buf = BytesIO()
            image.save(buf, format="PNG", optimize=True)
            ref = _emit_image(buf.getvalue(), destination, output_dir, embed=embed, mime="image/png")
            exported["soil"].append({"label": label, "path": ref})

    if climate_ps:
        destination = assets_root / "ps" / "climate" / "ps_climate.png"
        try:
            png = render_climate_chart_png(climate_ps)
            ref = _emit_image(png, destination, output_dir, embed=embed, mime="image/png")
            exported["climate"]["ps"].append(
                {"label": "Serie agroclimática (Precipitación y Temperatura)", "path": ref}
            )
        except Exception as exc:
            warnings.append(f"Gráfico climático PS: {exc}")

    return exported, warnings


def load_soil_summary(project_root: Path) -> dict:
    out = {}
    for variant in ("fast", "matlab"):
        p = project_root / "dem" / f"soilplus_saved_{variant}.json"
        if p.is_file():
            out[variant] = json.loads(p.read_text(encoding="utf-8"))
    return out


def load_smart_cluster_meta(project_root: Path) -> dict[str, dict]:
    out = {}
    for preset in ("smart1", "smart2", "smart3"):
        p = project_root / "smart_cluster" / preset / "meta.json"
        if p.is_file():
            out[preset] = json.loads(p.read_text(encoding="utf-8"))
    return out


def format_date_range(dates: list[str]) -> str:
    clean = sorted({d[:10] for d in dates if d})
    if not clean:
        return "—"
    if len(clean) == 1:
        return clean[0]
    return f"{clean[0]} – {clean[-1]}"


def md_escape(text: str) -> str:
    return str(text or "").strip()


def render_index_block(
    index_key: str,
    copy: dict,
    inv: dict | None,
    images: list[dict] | None = None,
    admin_narrative: str = "",
) -> list[str]:
    c = copy.get(index_key) or copy.get(index_key.upper()) or {}
    title = c.get("title") or index_key
    lines = [f"##### {title}", ""]
    if inv:
        dates = inv.get("band_dates") or []
        lines.append(f"- **Escenas disponibles:** {inv.get('bands', 0)} fechas ({format_date_range(dates)})")
        if dates:
            lines.append(f"- **Fechas:** {', '.join(dates)}")
        lines.append(f"- **Archivo:** `{inv.get('relative_path', '—')}`")
        lines.append("")
    for image in images or []:
        lines += image_markdown(image["label"], image["path"])
    if c.get("howToRead"):
        lines += [f"**Cómo leerlo:** {c['howToRead']}", ""]
    if c.get("interpretation"):
        lines += [f"**Interpretación:** {c['interpretation']}", ""]
    if c.get("legendLow") or c.get("legendHigh"):
        lines += [
            f"**Bajo:** {c.get('legendLow', '—')} · **Alto:** {c.get('legendHigh', '—')}",
            "",
        ]
    theory = c.get("theory") or c.get("interpretation") or ""
    if theory:
        lines += [f"**{title} (Explicación teórica)**", "", theory, ""]
    lines += ["**Narrativa del administrador**", ""]
    body = md_escape(admin_narrative)
    lines += [body if body else "_Sin narrativa del administrador publicada para este índice._", ""]
    return lines


def render_narrative(texts: dict[str, str], section_key: str) -> list[str]:
    body = md_escape(texts.get(section_key, ""))
    if not body:
        return ["_Sin texto narrativo publicado para esta sección._", ""]
    return [body, ""]


def build_markdown(
    project: dict,
    sensor_key: str,
    texts: dict[str, str],
    inventories: dict[str, dict[str, dict]],
    clusters: dict[str, list[str]],
    recorte_counts: dict[str, int],
    soil: dict,
    smart: dict[str, dict],
    farmer_copy: dict,
    images: dict,
    image_warnings: list[str],
) -> str:
    pid = project["id"]
    name = project["name"]
    sensor_title = BLOCK_TITLES[sensor_key]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = [
        f"# {name} — {sensor_title}",
        "",
        f"Resultados de **{sensor_title}**, en el mismo orden y agrupación que la **landing narrativa** de XeniaMAP.",
        "",
        f"- **Proyecto ID:** {pid}",
        f"- **Estado:** {project.get('status', '—')}",
        f"- **Generado:** {now}",
        "",
        "---",
        "",
        "## Resumen",
        "",
        "| Indicador | Valor |",
        "|-----------|-------|",
    ]

    inv = inventories.get(sensor_key, {})
    max_dates = 0
    all_dates: list[str] = []
    for item in inv.values():
        ds = item.get("band_dates") or []
        max_dates = max(max_dates, len(ds))
        all_dates.extend(ds)
    scene_count = max(max_dates, recorte_counts.get(sensor_key, 0))
    date_range = format_date_range(all_dates)

    lines += [
        f"| Fuente | {sensor_title} |",
        f"| Escenas | {scene_count} |",
        f"| Periodo | {date_range} |",
        "",
        "---",
        "",
        "## Tabla de contenidos",
        "",
    ]

    for block_idx, current_sensor in enumerate([sensor_key], start=1):
        block_title = BLOCK_TITLES[current_sensor]
        lines.append(f"{block_idx}. [{block_title}](#{block_idx}-{current_sensor})")
        defs = subsection_defs(current_sensor)
        for sub_idx, (suffix, title, _) in enumerate(defs, start=1):
            num = f"{block_idx}.{sub_idx}"
            anchor = f"{block_idx}-{current_sensor}-{suffix}"
            lines.append(f"   - {num} [{title}](#{anchor})")
            if suffix == "indices":
                for gi, g in enumerate(LANDING_INDEX_GROUPS, start=1):
                    keys = index_keys_for_group(g["id"], current_sensor)
                    if not keys:
                        continue
                    g_anchor = f"{block_idx}-{current_sensor}-{g['id']}"
                    lines.append(f"      - {num}.{gi} [{g['title']}](#{g_anchor})")

    lines += ["", "---", ""]

    for block_idx, current_sensor in enumerate([sensor_key], start=1):
        block_title = BLOCK_TITLES[current_sensor]
        lines += [f"## {block_idx}. {block_title} {{#{block_idx}-{current_sensor}}}", ""]
        defs = subsection_defs(current_sensor)
        inv = inventories.get(current_sensor, {})

        for sub_idx, (suffix, title, subtitle) in enumerate(defs, start=1):
            num = f"{block_idx}.{sub_idx}"
            anchor = f"{block_idx}-{current_sensor}-{suffix}"
            section_key = f"landing-{current_sensor}-{suffix}"
            lines += [
                f"### {num} {title} {{#{anchor}}}",
                "",
                f"_{subtitle}_",
                "",
            ]

            if suffix == "interactive":
                lines += [
                    "**Contenido en la landing:** panel interactivo de timelapse, series de índices y clima.",
                    "",
                ]
                if inv:
                    sample = next(iter(inv.values()), {})
                    lines.append(
                        f"Índices con series temporales: {', '.join(sorted(inv.keys()))} "
                        f"({sample.get('bands', 0)} fechas por stack)."
                    )
                    lines.append("")
                if current_sensor == "ps":
                    climate_imgs = images.get("climate", {}).get("ps") or []
                    if climate_imgs:
                        lines += [
                            "**Serie agroclimática** (Open-Meteo, promedio mensual alineado a las fechas PS):",
                            "",
                        ]
                        for image in climate_imgs:
                            lines += image_markdown(image["label"], image["path"])
                    else:
                        lines += ["_Sin serie agroclimática disponible para PS._", ""]

            elif suffix == "rgb":
                rc = recorte_counts.get(current_sensor, 0)
                lines += [
                    f"**Escenas RGB en recortes:** {rc}",
                    "",
                    f"_Galería temporal consolidada (mosaico legible, máx. {MOSAIC_MAX_TILES_PER_PAGE} escenas por imagen)._",
                    "",
                ]
                for image in images["rgb"].get(current_sensor, []):
                    lines += image_markdown(image["label"], image["path"])

            elif suffix == "indices":
                for gi, group in enumerate(LANDING_INDEX_GROUPS, start=1):
                    keys = index_keys_for_group(group["id"], current_sensor)
                    if not keys:
                        continue
                    g_num = f"{num}.{gi}"
                    g_anchor = f"{block_idx}-{current_sensor}-{group['id']}"
                    lines += [
                        f"#### {g_num} {group['title']} {{#{g_anchor}}}",
                        "",
                        group["meaning"],
                        "",
                    ]
                    for ik in keys:
                        copy_key = find_farmer_copy_key(farmer_copy, ik)
                        inv_item = find_inventory_item(inv, ik)
                        index_images = images["indices"].get(current_sensor, {}).get(ik.upper(), [])
                        narrative_index = re.sub(r"[^A-Z0-9_]", "", str(ik).strip().upper()) or "INDEX"
                        narrative_key = f"landing-{current_sensor}-index-{narrative_index}"
                        lines += render_index_block(
                            copy_key,
                            farmer_copy,
                            inv_item,
                            index_images,
                            texts.get(narrative_key, ""),
                        )

            elif suffix == "clusters":
                files = clusters.get(current_sensor, [])
                if files:
                    lines.append("**Resultados GMM guardados:**")
                    lines.append("")
                    for f in files:
                        lines.append(f"- `{f}`")
                    lines.append("")
                    for image in images["clusters"].get(current_sensor, []):
                        lines += image_markdown(image["label"], image["path"])
                else:
                    lines += ["_No hay resultados GMM para este sensor._", ""]

            elif suffix == "smart-clusters":
                if smart:
                    for preset, meta in sorted(smart.items()):
                        lines += [
                            f"**{preset}**",
                            f"- Clusters: {meta.get('n_clusters', '—')}",
                            f"- Pasos temporales: {meta.get('n_time_steps', '—')}",
                            f"- Índices: {', '.join(meta.get('required_indices') or meta.get('feature_names') or [])}",
                            "",
                        ]
                    for image in images["smart"]:
                        lines += image_markdown(image["label"], image["path"])
                else:
                    lines += ["_Sin mapas smart guardados._", ""]

            elif suffix == "agrogeofisica":
                mat = soil.get("matlab")
                if mat:
                    lines += [
                        "**Soil Plus (Mat, guardado)**",
                        f"- Clusters: {mat.get('n_clusters', '—')}",
                        f"- Muestras totales: {mat.get('total_samples', '—')}",
                        f"- Píxeles por cluster: {mat.get('pixels_per_cluster', [])}",
                        "",
                        "_Imágenes MAT incluidas: DEM con barra de alturas, CV y cluster con ubicación de puntos._",
                        "",
                    ]
                    for image in images["soil"]:
                        lines += image_markdown(image["label"], image["path"])
                else:
                    lines += ["_No hay resultados Soil Plus guardados._", ""]

            elif suffix == "ia":
                if pid == 19:
                    lines += [
                        "_Este proyecto no muestra el panel de IA automático; solo el texto narrativo del administrador._",
                        "",
                    ]

            lines += ["**Narrativa del administrador**", ""]
            lines += render_narrative(texts, section_key)
            lines += ["---", ""]

    if image_warnings:
        lines += [
            "## Advertencias de exportación",
            "",
            "Algunas vistas no pudieron materializarse:",
            "",
            *[f"- {warning}" for warning in image_warnings],
            "",
        ]
    lines.append("_Documento generado automáticamente desde la estructura de la landing narrativa (XeniaMAP)._")
    return "\n".join(lines)


def generate_markdowns(
    project_id: int,
    *,
    storage: Path = STORAGE_DEFAULT,
    database_url: str | None = None,
    output_dir: Path | None = None,
    embed_images: bool = True,
    max_md_mb: float = MAX_MD_MB_DEFAULT,
) -> list[dict]:
    """
    Genera los tres Markdown (PS, S1, S2) de la landing narrativa.
    Retorna [{sensor, path, size_mb}]; cada .md embebido se comprime hasta ≤ max_md_mb.
    """
    farmer_copy = load_index_farmer_copy()
    conn = db_connect(database_url)
    try:
        project = fetch_project(conn, project_id)
        texts = fetch_landing_texts(conn, project_id)
        tenant_id = project["tenant_id"]
        project_root = storage / f"tenant_{tenant_id}" / f"project_{project_id}"
        inventories = {sk: scan_index_inventory(project_root, sk) for sk in SENSOR_ORDER}

        climate_ps: list[dict] = []
        ps_dates: list[str] = []
        for item in inventories.get("ps", {}).values():
            ps_dates.extend(str(d)[:10] for d in (item.get("band_dates") or []))
        ps_dates = sorted({d for d in ps_dates if len(d) >= 10})
        centroid = _centroid_from_project(project_root, conn, project_id)
        if centroid and ps_dates:
            try:
                lat, lon = centroid
                monthly = _open_meteo_monthly_means(lat, lon, ps_dates[0], ps_dates[-1])
                climate_ps = build_climate_series_for_dates(ps_dates, monthly)
            except Exception as exc:
                print(f"Aviso clima PS: {exc}")
    finally:
        conn.close()

    clusters = {sk: list_cluster_files(project_root, sk) for sk in SENSOR_ORDER}
    recorte_counts = {sk: count_recortes(project_root, sk) for sk in SENSOR_ORDER}
    soil = load_soil_summary(project_root)
    smart = load_smart_cluster_meta(project_root)
    out_dir = output_dir or (project_root / "markdown")
    out_dir.mkdir(parents=True, exist_ok=True)
    images, image_warnings = export_landing_images(
        project_root,
        out_dir,
        inventories,
        embed=embed_images,
        climate_ps=climate_ps,
    )

    modo = "imágenes embebidas (base64)" if embed_images else "imágenes en assets/"
    output_names = {
        "ps": "landing_narrativa_PS.md",
        "s1": "landing_narrativa_S1.md",
        "s2": "landing_narrativa_S2.md",
    }
    max_bytes = int(max_md_mb * 1024 * 1024)
    outputs: list[dict] = []
    for sensor_key in SENSOR_ORDER:
        md = build_markdown(
            project,
            sensor_key,
            texts,
            inventories,
            clusters,
            recorte_counts,
            soil,
            smart,
            farmer_copy,
            images,
            image_warnings,
        )
        if embed_images and max_bytes > 0:
            md = enforce_markdown_size_limit(md, max_bytes, label=output_names[sensor_key])
        out_path = out_dir / output_names[sensor_key]
        out_path.write_text(md, encoding="utf-8")
        size_mb = out_path.stat().st_size / (1024 * 1024)
        print(f"Escrito: {out_path} ({size_mb:.1f} MB, {modo})")
        outputs.append({"sensor": sensor_key, "path": str(out_path), "size_mb": round(size_mb, 2)})

    legacy_path = out_dir / "landing_narrativa.md"
    if legacy_path.exists():
        legacy_path.unlink()
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="Exportar landing narrativa a Markdown")
    parser.add_argument("--project-id", type=int, default=19)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Destino. Por defecto: <storage>/tenant_N/project_N/markdown",
    )
    parser.add_argument("--storage", type=Path, default=STORAGE_DEFAULT)
    parser.add_argument("--database-url", default=None)
    parser.add_argument(
        "--max-md-mb",
        type=float,
        default=MAX_MD_MB_DEFAULT,
        help="Tamaño máximo de cada .md embebido (MB); 0 desactiva el límite.",
    )
    embed_group = parser.add_mutually_exclusive_group()
    embed_group.add_argument(
        "--embed-images",
        dest="embed_images",
        action="store_true",
        help="Incrusta las imágenes en base64 dentro del .md (un solo archivo autocontenido). Por defecto.",
    )
    embed_group.add_argument(
        "--no-embed-images",
        dest="embed_images",
        action="store_false",
        help="Escribe las imágenes en assets/ y las referencia por ruta (.md ligero).",
    )
    parser.set_defaults(embed_images=True)
    args = parser.parse_args()

    generate_markdowns(
        args.project_id,
        storage=args.storage,
        database_url=args.database_url,
        output_dir=args.output_dir,
        embed_images=args.embed_images,
        max_md_mb=args.max_md_mb,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
