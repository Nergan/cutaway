"""PDF pages as linear markdown.

A designed page can put words in columns, run them over a picture, or fill a
line with dots. Markdown has none of that, so the words are kept in reading
order and the layout is left behind. A picture that is itself the content is
uploaded and linked. A picture that only paints the page, a frame, or a rule
is not.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

import fitz
from PIL import Image, ImageStat

from formular.core.image_host import upload_image

_LEADER = re.compile(
    r"^(?P<title>\S.*?)\s*(?:[.\u00b7…]\s*){3,}\s*(?P<num>\d{1,4})?\s*$"
)
_MAX_PICTURES = 16
_MAX_EDGE = 1600


@dataclass
class _Item:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str = ""
    payload: bytes | None = None
    suffix: str = "jpg"

    @property
    def width(self) -> float:
        return self.x1 - self.x0


def write_pdf_markdown(input_path: str, output_path: str) -> None:
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(render_pdf_markdown(input_path))


def render_pdf_markdown(path: str, upload=None) -> str:
    if upload is None:
        upload = upload_image
    document = fitz.open(path)
    pages: list[str] = []
    seen: dict[int, str | None] = {}
    remaining = _MAX_PICTURES
    try:
        for page in document:
            text, remaining = _page_markdown(document, page, upload, seen, remaining)
            if text:
                pages.append(text)
    finally:
        document.close()
    body = "\n\n".join(pages).strip()
    return f"{body}\n" if body else "\n"


def _page_markdown(document, page, upload, seen: dict[int, str | None], remaining: int):
    width = float(page.rect.width)
    height = float(page.rect.height)
    raw_blocks = [
        block
        for block in page.get_text("dict").get("blocks", [])
        if block.get("type") == 0 and not _is_furniture(block, height)
    ]
    blocks = _attach_page_numbers(raw_blocks, width)
    text_items = []
    for block in blocks:
        rendered = _render_block(block)
        if rendered:
            x0, y0, x1, y1 = block["bbox"]
            text_items.append(_Item(x0, y0, x1, y1, text=rendered))

    pictures, promoted = _content_pictures(document, page, blocks)
    if not text_items and not pictures and promoted is not None:
        pictures = [promoted]

    items = list(text_items)
    for info, payload, suffix in pictures:
        if remaining <= 0:
            break
        xref = int(info.get("xref") or 0)
        url = seen.get(xref) if xref else None
        if xref and xref in seen and url is None:
            continue
        if url is None:
            url = upload(payload, suffix)
            remaining -= 1
            if xref:
                seen[xref] = url
        if not url:
            continue
        box = info["bbox"]
        items.append(_Item(box[0], box[1], box[2], box[3], text=f"![]({url})"))

    ordered = _reading_order(items, width)
    lines = [item.text for item in ordered if item.text]
    return "\n\n".join(lines), remaining


def _is_furniture(block: dict, height: float) -> bool:
    text = _plain(block).strip()
    if not text:
        return True
    y0, y1 = block["bbox"][1], block["bbox"][3]
    if (y1 < height * 0.045 or y0 > height * 0.9) and len(text) <= 48:
        return True
    if text.isdigit() and len(text) <= 3 and y0 > height * 0.82:
        return True
    return False


def _attach_page_numbers(blocks: list[dict], width: float) -> list[dict]:
    numbers = []
    body = []
    for block in blocks:
        text = _plain(block).strip()
        if text.isdigit() and len(text) <= 4 and block["bbox"][0] > width * 0.72:
            numbers.append(block)
        else:
            body.append(block)
    used: set[int] = set()
    for block in body:
        plain = re.sub(r"\s+", " ", _plain(block)).strip()
        if _LEADER.match(plain) is None:
            continue
        center = (block["bbox"][1] + block["bbox"][3]) / 2
        best = None
        best_distance = 10.0
        for index, number in enumerate(numbers):
            if index in used:
                continue
            other = (number["bbox"][1] + number["bbox"][3]) / 2
            distance = abs(other - center)
            if distance < best_distance:
                best = index
                best_distance = distance
        if best is not None:
            used.add(best)
            block["_page_number"] = _plain(numbers[best]).strip()
    return body


def _render_block(block: dict) -> str:
    rows = _rows(block)
    if not rows:
        return ""
    plain = re.sub(r"\s+", " ", " ".join(text for text, _style, _size in rows)).strip()
    if not plain:
        return ""
    lead = _LEADER.match(plain)
    if lead:
        title = lead.group("title").strip(" .\t")
        number = lead.group("num") or block.get("_page_number")
        label = _escape(title)
        if number:
            return f"- {label} — {number}"
        return f"- {label}"
    size = max(row[2] for row in rows)
    styles = {row[1] for row in rows}
    if size >= 18 and len(plain) <= 90:
        marks = "#" if size >= 36 else "##"
        return f"{marks} {_escape(plain)}"
    escaped = _escape(plain)
    style = styles.pop() if len(styles) == 1 else "mixed"
    if style == "bold":
        return f"**{escaped}**"
    if style == "italic":
        return f"*{escaped}*"
    if style == "both":
        return f"***{escaped}***"
    if style == "mixed":
        return _mixed(rows)
    return escaped


def _rows(block: dict) -> list[tuple[str, str, float]]:
    rows: list[tuple[str, str, float]] = []
    caps: list[str] = []
    for line in block.get("lines", []):
        spans = [span for span in line.get("spans", []) if span.get("text")]
        if not spans:
            continue
        text = "".join(span["text"] for span in spans).strip()
        if not text:
            continue
        size = max(float(span.get("size", 0)) for span in spans)
        styles = {_span_style(span) for span in spans if span["text"].strip()}
        style = styles.pop() if len(styles) == 1 else "mixed"
        if len(text) == 1 and text.isalpha() and size >= 18:
            caps.append(text)
            continue
        rows.append((text, style, size))
    if caps and rows:
        text, style, size = rows[0]
        prefix = "".join(caps)
        glued = prefix + text if text[:1].islower() else f"{prefix} {text}"
        rows[0] = (glued, style, size)
    elif caps and not rows:
        rows.append(("".join(caps), "plain", 18))
    merged: list[tuple[str, str, float]] = []
    for text, style, size in rows:
        previous = merged[-1][0] if merged else ""
        if (
            merged
            and previous.endswith("-")
            and len(previous) > 1
            and previous[-2].isalpha()
            and text[:1].islower()
            and merged[-1][1] == style
        ):
            merged[-1] = (previous[:-1] + text, style, merged[-1][2])
        else:
            merged.append((text, style, size))
    return merged


def _mixed(rows: list[tuple[str, str, float]]) -> str:
    groups: list[tuple[str, list[str]]] = []
    for text, style, _size in rows:
        if groups and groups[-1][0] == style:
            groups[-1][1].append(text)
        else:
            groups.append((style, [text]))
    parts = []
    for style, chunks in groups:
        escaped = _escape(" ".join(chunks))
        if style == "bold":
            parts.append(f"**{escaped}**")
        elif style == "italic":
            parts.append(f"*{escaped}*")
        elif style == "both":
            parts.append(f"***{escaped}***")
        else:
            parts.append(escaped)
    return " ".join(parts)


def _span_style(span: dict) -> str:
    font = str(span.get("font", "")).lower()
    flags = int(span.get("flags", 0))
    bold = bool(flags & 16) or "bold" in font
    italic = bool(flags & 2) or "italic" in font or "oblique" in font
    if bold and italic:
        return "both"
    if bold:
        return "bold"
    if italic:
        return "italic"
    return "plain"


def _plain(block: dict) -> str:
    return "".join(
        span.get("text", "")
        for line in block.get("lines", [])
        for span in line.get("spans", [])
    )


def _escape(text: str) -> str:
    text = text.replace("\\", "\\\\")
    return re.sub(r"([*_`\[\]])", r"\\\1", text)


def _content_pictures(document, page, blocks: list[dict]):
    kept = []
    largest = None
    largest_area = 0.0
    for info in page.get_image_info(xrefs=True):
        bbox = info.get("bbox")
        if not bbox:
            continue
        area = max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])
        payload = _picture_bytes(document, page, info)
        if payload is None:
            continue
        encoded = _encode_picture(payload[0])
        if encoded is None:
            continue
        data, suffix = encoded
        if area > largest_area:
            largest = (info, data, suffix)
            largest_area = area
        if _covers_page(bbox, page) or _thin(info) or _in_margin(bbox, page) or _covered_by_text(bbox, blocks):
            continue
        kept.append((info, data, suffix))
    return kept, largest


def _picture_bytes(document, page, info) -> tuple[bytes, str] | None:
    xref = int(info.get("xref") or 0)
    try:
        if xref:
            extracted = document.extract_image(xref)
            return extracted["image"], extracted.get("ext") or "png"
        clip = fitz.Rect(info["bbox"])
        pixmap = page.get_pixmap(clip=clip, dpi=110, alpha=False)
        return pixmap.tobytes("png"), "png"
    except Exception:
        return None


def _encode_picture(data: bytes) -> tuple[bytes, str] | None:
    try:
        with Image.open(io.BytesIO(data)) as image:
            if _flat(image):
                return None
            image = image.convert("RGBA") if "A" in image.getbands() else image.convert("RGB")
            if max(image.size) > _MAX_EDGE:
                image.thumbnail((_MAX_EDGE, _MAX_EDGE))
            handle = io.BytesIO()
            if image.mode == "RGBA" and _uses_alpha(image):
                image.save(handle, format="PNG", optimize=True)
                suffix = "png"
            else:
                image.convert("RGB").save(handle, format="JPEG", quality=82, optimize=True)
                suffix = "jpg"
    except Exception:
        return None
    payload = handle.getvalue()
    if len(payload) > 4 * 1024 * 1024:
        return None
    return payload, suffix


def _flat(image: Image.Image) -> bool:
    """A fill or a frame is decoration: its middle does not change."""
    rgba = image.convert("RGBA")
    composed = Image.new("RGB", rgba.size, (255, 255, 255))
    composed.paste(rgba, mask=rgba.getchannel("A"))
    width, height = composed.size
    if width < 2 or height < 2:
        return True
    center = composed.crop(
        (int(width * 0.3), int(height * 0.3), max(int(width * 0.7), 1), max(int(height * 0.7), 1))
    )
    if center.size[0] < 1 or center.size[1] < 1:
        center = composed
    return max(ImageStat.Stat(center).stddev) < 8


def _uses_alpha(image: Image.Image) -> bool:
    low, high = image.getchannel("A").getextrema()
    return low < 250


def _covers_page(bbox, page) -> bool:
    area = max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])
    page_area = float(page.rect.width) * float(page.rect.height)
    return page_area > 0 and area > 0.85 * page_area


def _thin(info: dict) -> bool:
    width = int(info.get("width") or 0)
    height = int(info.get("height") or 0)
    if width < 8 or height < 8 or (width < 48 and height < 48):
        return True
    short, long = sorted((width, height))
    return short <= 64 and long > 0 and short / long < 0.12


def _in_margin(bbox, page) -> bool:
    height = float(page.rect.height)
    return bbox[3] < height * 0.05 or bbox[1] > height * 0.9


def _covered_by_text(bbox, blocks: list[dict]) -> bool:
    rect = fitz.Rect(bbox)
    if rect.is_empty or rect.get_area() <= 0:
        return False
    covered = 0.0
    chars = 0
    for block in blocks:
        other = fitz.Rect(block["bbox"])
        shared = rect & other
        if shared.is_empty or shared.get_area() < 0.55 * other.get_area():
            continue
        covered += shared.get_area()
        chars += len(_plain(block).strip())
    if chars >= 80:
        return True
    return covered > 0.35 * rect.get_area() and chars >= 20


def _reading_order(items: list[_Item], page_width: float) -> list[_Item]:
    ordered: list[_Item] = []
    band: list[_Item] = []

    def flush() -> None:
        if not band:
            return
        for column in _columns(band):
            ordered.extend(sorted(column, key=lambda item: (item.y0, item.x0)))
        band.clear()

    for item in sorted(items, key=lambda item: (item.y0, item.x0)):
        if item.width > page_width * 0.58:
            flush()
            ordered.append(item)
        else:
            band.append(item)
    flush()
    return ordered


def _columns(items: list[_Item]) -> list[list[_Item]]:
    columns: list[list[_Item]] = []
    for item in sorted(items, key=lambda item: (item.x0, item.y0)):
        placed = False
        for column in columns:
            if _same_column(item, column):
                column.append(item)
                placed = True
                break
        if not placed:
            columns.append([item])
    columns.sort(key=lambda column: min(item.x0 for item in column))
    return columns


def _same_column(item: _Item, column: list[_Item]) -> bool:
    x0 = min(other.x0 for other in column)
    x1 = max(other.x1 for other in column)
    overlap = min(item.x1, x1) - max(item.x0, x0)
    if overlap <= 0:
        return False
    narrower = min(item.width, x1 - x0)
    return narrower > 0 and overlap >= 0.35 * narrower
