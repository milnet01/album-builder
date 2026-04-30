"""Approval report rendering (Spec 09).

Single-template, two-output pipeline: Jinja2 renders one HTML string in
memory; that string is written verbatim to `<name> - YYYY-MM-DD.html` and
fed to WeasyPrint to produce `<name> - YYYY-MM-DD.pdf`. Atomic-pair
writes per Spec 10 — both `.tmp` files complete before either rename.

Public API:
- `render_report(album, library, *, reports_dir, today)` — drives the
  full pipeline; returns `(html_path, pdf_path)`.
- `version_string()` — render-time version source with `ImportError`
  fallback to `"unknown"`.
"""

from __future__ import annotations

import base64
import io
import logging
import os
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from album_builder.persistence.atomic_io import _fsync_dir, _unique_tmp_path
from album_builder.services.export import sanitise_title

logger = logging.getLogger(__name__)

LYRICS_BODY_CAP_BYTES = 32 * 1024
COVER_FILESIZE_THRESHOLD_BYTES = 10 * 1024 * 1024
COVER_DIM_MAX = 800
TEMPLATE_DIR = Path(__file__).parent / "templates"
TEMPLATE_NAME = "report.html.j2"


def version_string() -> str:
    """Read `__version__` at render time (Spec 09 §Technology + TC-09-02).

    On `ImportError` (frozen app, broken venv, test-isolation context) or
    `AttributeError` (partially-initialised module, typo'd constant),
    return `"unknown"` and log a warning; never abort the render.
    """
    try:
        from album_builder.version import __version__
        return __version__
    except (ImportError, AttributeError) as exc:
        logger.warning("version_string(): lookup failed (%s); using 'unknown'", exc)
        return "unknown"


def _format_duration(seconds: int) -> str:
    """`MM:SS` for tracks under an hour, `H:MM:SS` for longer."""
    if seconds < 0:
        seconds = 0
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _truncate_lyrics(lyrics: str | None) -> tuple[str, bool]:
    """Cap lyrics body at 32 KB UTF-8; append truncation marker (TC-09-09b)."""
    if not lyrics:
        return "", False
    raw = lyrics.encode("utf-8")
    if len(raw) <= LYRICS_BODY_CAP_BYTES:
        return lyrics, False
    truncated = raw[:LYRICS_BODY_CAP_BYTES].decode("utf-8", errors="ignore")
    return truncated + "\n(... truncated)", True


def _normalise_cover(image_bytes: bytes | None) -> bytes | None:
    """Pillow-resize the cover when needed (Spec 09 §Errors + TC-09-08).

    Threshold is `OR`: source-file > 10 MB OR dimensions > 800x800 -> resize
    to 800x800. Smaller-and-within-dimensions pass through unchanged. On
    any decode failure (corrupt bytes, unsupported format, Pillow missing)
    return None so the caller falls through to the placeholder gradient
    rather than passing broken bytes downstream to WeasyPrint.

    Pillow is a hard runtime dependency of this module - if it cannot be
    imported, we return None on EVERY call (the placeholder gradient is
    used). Earlier drafts returned the raw bytes when Pillow was missing,
    which let corrupt JPEG bytes flow through to WeasyPrint and abort the
    render.
    """
    if not image_bytes:
        return None
    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow not installed; falling through to cover placeholder")
        return None
    needs_resize = len(image_bytes) > COVER_FILESIZE_THRESHOLD_BYTES
    try:
        with Image.open(io.BytesIO(image_bytes)) as im:
            w, h = im.size
            if w > COVER_DIM_MAX or h > COVER_DIM_MAX:
                needs_resize = True
            if not needs_resize:
                # Verify decode succeeds (catches truncated JPEG / wrong magic
                # bytes that Image.open accepts lazily) before returning raw.
                im.verify()
                return image_bytes
            # Re-open after verify - PIL closes the image on verify().
            with Image.open(io.BytesIO(image_bytes)) as im2:
                im2 = im2.convert("RGB")
                im2.thumbnail((COVER_DIM_MAX, COVER_DIM_MAX))
                buf = io.BytesIO()
                im2.save(buf, format="JPEG", quality=85)
                return buf.getvalue()
    except Exception as exc:
        logger.warning("cover normalise failed: %s; falling through to placeholder", exc)
        return None


def _b64_data_uri(image_bytes: bytes | None, *, mime: str = "image/jpeg") -> str | None:
    if not image_bytes:
        return None
    return f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"


def _resolve_columns(tracks: list[dict[str, Any]]) -> dict[str, Any]:
    """Three-state composer + artist column rule (TC-09-06).

    Returns `{"show_composer": bool, "all_composer": str | None,
    "show_artist": bool, "all_artist": str | None}`.

    Logic for each column:
      - all share a non-empty value → drop the column, set `all_*` line
      - some have / some don't → keep the column, missing = em-dash
      - none have → drop the column, no above-table line
    """
    def column_state(values: list[str | None]) -> tuple[bool, str | None]:
        non_empty = [v for v in values if v]
        if not non_empty:
            return False, None
        if len(non_empty) == len(values) and len(set(non_empty)) == 1:
            return False, non_empty[0]
        return True, None

    composers = [t.get("composer") for t in tracks]
    artists = [t.get("artist") for t in tracks]
    show_composer, all_composer = column_state(composers)
    show_artist, all_artist = column_state(artists)
    return {
        "show_composer": show_composer,
        "all_composer": all_composer,
        "show_artist": show_artist,
        "all_artist": all_artist,
    }


def _build_track_context(track_path: Path, track: Any, position: int) -> dict[str, Any]:
    duration_seconds = round(float(getattr(track, "duration_seconds", 0) or 0))
    # Track domain type publishes `lyrics_text`; older fixtures may use `lyrics`.
    raw_lyrics = getattr(track, "lyrics_text", None) or getattr(track, "lyrics", None)
    lyrics_text, lyrics_truncated = _truncate_lyrics(raw_lyrics)
    cover_bytes = _normalise_cover(getattr(track, "cover_data", None))
    cover_mime = getattr(track, "cover_mime", "image/jpeg") or "image/jpeg"
    if cover_bytes and not cover_mime.startswith("image/"):
        cover_mime = "image/jpeg"
    return {
        "position": position,
        "title": getattr(track, "title", None) or track_path.stem,
        "artist": getattr(track, "artist", None) or None,
        "composer": getattr(track, "composer", None) or None,
        "duration_seconds": duration_seconds,
        "duration": _format_duration(duration_seconds),
        "comment": getattr(track, "comment", None) or None,
        "lyrics": lyrics_text,
        "lyrics_truncated": lyrics_truncated,
        "cover_uri": _b64_data_uri(cover_bytes, mime=cover_mime),
    }


def _build_album_context(album: Any, library: Any) -> dict[str, Any]:
    tracks_ctx: list[dict[str, Any]] = []
    total_seconds = 0
    for i, track_path_str in enumerate(album.track_paths, start=1):
        track_path = Path(track_path_str)
        track = library.find(track_path)
        if track is None:
            continue
        ctx = _build_track_context(track_path, track, i)
        tracks_ctx.append(ctx)
        total_seconds += ctx["duration_seconds"]
    columns = _resolve_columns(tracks_ctx)

    cover_uri: str | None = None
    cover_override = getattr(album, "cover_override", None)
    if cover_override:
        try:
            data = Path(cover_override).read_bytes()
            cover_uri = _b64_data_uri(_normalise_cover(data))
        except OSError as exc:
            logger.warning("cover_override read failed: %s", exc)
    if cover_uri is None and tracks_ctx:
        cover_uri = tracks_ctx[0]["cover_uri"]
    return {
        "name": getattr(album, "name", "") or "",
        "artist": columns["all_artist"],
        "tracks": tracks_ctx,
        "track_count": len(tracks_ctx),
        "target_count": getattr(album, "target_count", len(tracks_ctx)),
        "total_seconds": total_seconds,
        "total_duration": _format_duration(total_seconds),
        "cover_uri": cover_uri,
        **columns,
    }


def _jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        keep_trailing_newline=True,
    )


def render_html(album: Any, library: Any, *, today: date | None = None) -> str:
    """Render the template once → one HTML string (Spec 09 §Technology)."""
    env = _jinja_env()
    template = env.get_template(TEMPLATE_NAME)
    today = today or date.today()
    ctx = _build_album_context(album, library)
    ctx.update({
        "version": version_string(),
        "approved_date": today.isoformat(),
        "approved_date_human": today.strftime("%d %B %Y"),
    })
    return template.render(**ctx)


def render_pdf_from_html(html: str) -> bytes:
    """WeasyPrint render. Lazy-imported to keep test suites that mock the
    full pipeline cheap and to defer the system-deps cost."""
    from weasyprint import HTML
    return HTML(string=html).write_pdf()


def _filename_for(album: Any, today: date) -> tuple[str, str]:
    name = sanitise_title(getattr(album, "name", "") or "") or "album"
    stem = f"{name} - {today.isoformat()}"
    return f"{stem}.html", f"{stem}.pdf"


def render_report(
    album: Any,
    library: Any,
    *,
    reports_dir: Path,
    today: date | None = None,
) -> tuple[Path, Path]:
    """Spec 09 §canonical approve sequence step:render-* full pipeline.

    Steps:
      step:render-tmp        — render template + write both `.tmp` files.
      step:render-rename-html — atomic rename html.tmp → html.
      step:render-rename-pdf  — atomic rename pdf.tmp → pdf.

    On any failure during step:render-tmp, the in-flight `.tmp` files are
    removed. After step:render-rename-html, the load-time atomic-pair
    scan handles half-pair recovery on next launch.
    """
    today = today or date.today()
    reports_dir.mkdir(parents=True, exist_ok=True)
    html_name, pdf_name = _filename_for(album, today)
    html_final = reports_dir / html_name
    pdf_final = reports_dir / pdf_name
    html_tmp = _unique_tmp_path(html_final)
    pdf_tmp = _unique_tmp_path(pdf_final)

    html_str = render_html(album, library, today=today)
    pdf_bytes = render_pdf_from_html(html_str)

    # step:render-tmp - write BOTH tmps before any rename runs (Spec 10
    # §Atomic pair Phase 1). Each write goes through the standard
    # tmp-flush-fsync sequence; the parent directory is fsynced after
    # both tmps are durable so a power-cut between Phase 1 and Phase 2
    # cannot leave un-flushed dirent blocks.
    try:
        with open(html_tmp, "w", encoding="utf-8") as fh:
            fh.write(html_str)
            fh.flush()
            os.fsync(fh.fileno())
        with open(pdf_tmp, "wb") as fh:
            fh.write(pdf_bytes)
            fh.flush()
            os.fsync(fh.fileno())
        _fsync_dir(reports_dir)
    except Exception:
        for p in (html_tmp, pdf_tmp):
            if p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass
        raise

    # step:render-rename-html
    os.replace(html_tmp, html_final)
    # step:render-rename-pdf
    try:
        os.replace(pdf_tmp, pdf_final)
    except OSError:
        # Spec 10 §Atomic pair "Between rename-A and rename-B" recovery:
        # delete BOTH members. In-process matches the load-time scan
        # contract so a same-session retry lands in a clean directory.
        for orphan in (html_final, pdf_tmp):
            if orphan.exists():
                try:
                    orphan.unlink()
                except OSError as cleanup_exc:
                    logger.warning(
                        "render_report: orphan cleanup of %s failed: %s",
                        orphan, cleanup_exc,
                    )
        raise
    _fsync_dir(reports_dir)
    return html_final, pdf_final


def report_filenames_for(album: Any, today: date | None = None) -> tuple[str, str]:
    """Convenience accessor for callers that want the filenames without rendering.

    Returns `(html_filename, pdf_filename)` matching what `render_report`
    would produce.
    """
    return _filename_for(album, today or date.today())


def report_paths_for(album: Any, reports_dir: Path, today: date | None = None) -> tuple[Path, Path]:
    h, p = report_filenames_for(album, today)
    return reports_dir / h, reports_dir / p


def has_complete_report(album: Any, reports_dir: Path, today: date | None = None) -> bool:
    """Both finals present for the given date — used by smoke checks."""
    h, p = report_paths_for(album, reports_dir, today)
    return h.exists() and p.exists()


def list_warnings(album: Any, library: Any) -> Iterable[str]:
    """Pre-flight warnings shown in the approve dialog (Spec 09 §The approve flow)."""
    warnings: list[str] = []
    selected_count = len(album.track_paths)
    target = getattr(album, "target_count", selected_count)
    if selected_count != target:
        warnings.append(f"selected count {selected_count} != target {target}")
    for track_path_str in album.track_paths:
        track_path = Path(track_path_str)
        track = library.find(track_path)
        if track is None or getattr(track, "is_missing", False):
            warnings.append(f"missing source: {track_path}")
    return warnings
