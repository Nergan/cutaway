import os
from pathlib import Path

import pytest

from formular.core.graph import find_shortest_path


def _pdf_tools():
    """PyMuPDF is a formular dependency. The hub test env installs it for these checks."""
    fitz = pytest.importorskip("fitz")
    pytest.importorskip("PIL")
    from PIL import Image

    from formular.core.pdf_markdown import render_pdf_markdown

    return fitz, Image, render_pdf_markdown


def _noise(image_module, path: Path) -> None:
    image = image_module.frombytes("RGB", (96, 96), os.urandom(96 * 96 * 3))
    image.save(path, format="PNG")


def _flat(image_module, path: Path) -> None:
    image_module.new("RGB", (400, 400), (232, 220, 190)).save(path, format="PNG")


def _frame(image_module, path: Path) -> None:
    image = image_module.new("RGB", (220, 140), (48, 36, 18))
    image.paste(image_module.new("RGB", (196, 116), (245, 236, 196)), (12, 12))
    image.save(path, format="PNG")


def _sample_pdf(folder: Path, fitz, image_module) -> Path:
    noise = folder / "noise.png"
    flat = folder / "flat.png"
    frame = folder / "frame.png"
    _noise(image_module, noise)
    _flat(image_module, flat)
    _frame(image_module, frame)
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_image(page.rect, filename=str(flat))
    page.insert_text((40, 80), "LEFTWORD stands in the first column.", fontsize=12, fontname="helv")
    page.insert_text((40, 100), "It continues down the left side.", fontsize=12, fontname="helv")
    page.insert_text((330, 80), "RIGHTWORD stands in the second column.", fontsize=12, fontname="helv")
    page.insert_text((48, 220), "Introduction........................", fontsize=14, fontname="helv")
    page.insert_text((520, 220), "4", fontsize=14, fontname="helv")
    page.insert_text((48, 280), "A short title", fontsize=28, fontname="hebo")
    page.insert_image(fitz.Rect(40, 420, 220, 600), filename=str(noise))
    page.insert_image(fitz.Rect(340, 420, 540, 560), filename=str(frame))
    page.insert_text((48, 640), "Caption under the picture.", fontsize=12, fontname="helv")
    target = folder / "layout.pdf"
    document.save(target)
    document.close()
    return target


def test_a_designed_page_becomes_linear_markdown(tmp_path: Path):
    fitz, image_module, render_pdf_markdown = _pdf_tools()
    uploaded: list[str] = []

    def upload(data: bytes, suffix: str) -> str:
        uploaded.append(suffix)
        return "https://tmpfiles.org/dl/1.abc/sample/picture.jpg"

    markdown = render_pdf_markdown(str(_sample_pdf(tmp_path, fitz, image_module)), upload)
    assert markdown.index("LEFTWORD") < markdown.index("RIGHTWORD")
    assert "...." not in markdown
    assert "- Introduction — 4" in markdown
    assert "## A short title" in markdown
    assert "https://tmpfiles.org/dl/1.abc/sample/picture.jpg" in markdown
    assert uploaded == ["jpg"]


def test_aligned_cells_become_a_markdown_table(tmp_path: Path):
    fitz, _image_module, render_pdf_markdown = _pdf_tools()
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_text((40, 80), "Balance notes stay above the grid.", fontsize=12, fontname="helv")
    rows = (
        ("1", "2", "3", "4"),
        ("alpha", "beta", "gamma", "delta"),
        ("one", "two", "three", "four"),
        ("red", "green", "blue", "gold"),
        ("cat", "dog", "fox", "owl"),
        ("oak", "elm", "ash", "yew"),
    )
    for row_index, row in enumerate(rows):
        for column_index, word in enumerate(row):
            x = 40 + column_index * 120
            y = 140 + row_index * 40
            page.draw_rect(fitz.Rect(x - 2, y - 18, x + 108, y + 6), width=0.4)
            page.insert_text((x, y), word, fontsize=12, fontname="helv")
    target = tmp_path / "grid.pdf"
    document.save(target)
    document.close()
    markdown = render_pdf_markdown(str(target), lambda data, suffix: None)
    assert "Balance notes stay above the grid." in markdown
    assert "| 1 | 2 | 3 | 4 |" in markdown
    assert "| alpha | beta | gamma | delta |" in markdown
    assert "alpha beta gamma" not in markdown


def test_a_refused_upload_keeps_the_picture_in_the_file(tmp_path: Path):
    fitz, image_module, render_pdf_markdown = _pdf_tools()
    noise = tmp_path / "scan.png"
    image_module.frombytes("RGB", (200, 280), os.urandom(200 * 280 * 3)).save(noise, format="PNG")
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_image(page.rect, filename=str(noise))
    target = tmp_path / "scan.pdf"
    document.save(target)
    document.close()
    markdown = render_pdf_markdown(str(target), lambda data, suffix: None)
    assert "data:image/jpeg;base64," in markdown


def test_pdf_markdown_is_a_direct_step():
    assert find_shortest_path("pdf", "md") == ["pdf", "md"]
    assert find_shortest_path("pdf", "html") == ["pdf", "html"]


def test_words_on_top_of_a_frame_stay_text(tmp_path: Path):
    fitz, image_module, render_pdf_markdown = _pdf_tools()
    noise = tmp_path / "card.png"
    _noise(image_module, noise)
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_image(fitz.Rect(40, 80, 280, 360), filename=str(noise))
    page.insert_text((50, 120), "Armor Class 17 and a long note that sits on the frame itself.", fontsize=11)
    page.insert_text((50, 140), "Hit Points 21 stay readable without the frame.", fontsize=11)
    target = tmp_path / "card.pdf"
    document.save(target)
    document.close()

    def upload(data: bytes, suffix: str) -> str:
        raise AssertionError("a frame behind the words is not a picture")

    markdown = render_pdf_markdown(str(target), upload)
    assert "Armor Class 17" in markdown
    assert "![](" not in markdown


def test_a_scanned_page_keeps_its_picture(tmp_path: Path):
    fitz, image_module, render_pdf_markdown = _pdf_tools()
    noise = tmp_path / "scan.png"
    image_module.frombytes("RGB", (200, 280), os.urandom(200 * 280 * 3)).save(noise, format="PNG")
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_image(page.rect, filename=str(noise))
    target = tmp_path / "scan.pdf"
    document.save(target)
    document.close()
    calls = []

    def upload(data: bytes, suffix: str) -> str:
        calls.append(suffix)
        return "https://tmpfiles.org/dl/9.def/scan/picture.jpg"

    markdown = render_pdf_markdown(str(target), upload)
    assert calls == ["jpg"]
    assert "https://tmpfiles.org/dl/9.def/scan/picture.jpg" in markdown


def test_convert_document_writes_the_markdown(tmp_path: Path, monkeypatch):
    fitz, image_module, _render = _pdf_tools()
    pytest.importorskip("pypandoc")
    from formular.core import converter

    monkeypatch.setattr(
        "formular.core.pdf_markdown.upload_image",
        lambda data, suffix: "https://tmpfiles.org/dl/2.ghi/out/picture.jpg",
    )
    source = _sample_pdf(tmp_path, fitz, image_module)
    output = tmp_path / "out.md"
    import asyncio

    asyncio.run(converter.convert_document(str(source), str(output), "pdf", "md"))
    text = output.read_text(encoding="utf-8")
    assert "LEFTWORD" in text
    assert "...." not in text
