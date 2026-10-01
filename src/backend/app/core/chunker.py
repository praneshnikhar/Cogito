"""Document chunking — recursive character splitting with overlap, plus
lightweight per-type extraction (text / PDF / URL) and content hashing."""

from __future__ import annotations

import hashlib
import io
import logging

from langchain_text_splitters import RecursiveCharacterTextSplitter

log = logging.getLogger("cogito.chunker")

DEFAULT_CHUNK_SIZE = 800
DEFAULT_OVERLAP = 120

_SEPARATORS = ["\n\n", "\n", ". ", "! ", "? ", "; ", " ", ""]

# Marker used by the PDF extractor to delimit page boundaries inside text.
PAGE_MARKER = "\n\n[PAGE]\n\n"


def content_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def split_by_type(text: str, doc_type: str = "text") -> tuple[list[str], list[int]]:
    """Split text into chunks; pages are best-effort line numbers (1-based)."""
    chunk_size = 500 if doc_type == "contract" else DEFAULT_CHUNK_SIZE
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=DEFAULT_OVERLAP,
        separators=_SEPARATORS,
        length_function=len,
    )
    texts = splitter.split_text(text)
    pages = [1] * len(texts)
    return texts, pages


async def extract_text(filename: str, raw: bytes) -> tuple[str, str]:
    """Return (text, mime_type). Supports .txt, .md, .json, .csv, .pdf,
    .html, .docx, and images (OCR, when tesseract is installed)."""
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(raw))
            pages = [page.extract_text() or "" for page in reader.pages]
            text = PAGE_MARKER.join(pages)
            return text, "application/pdf"
        except Exception as e:  # noqa: BLE001
            log.warning(f"pdf parse failed: {e}")
            return raw.decode("utf-8", errors="ignore"), "application/pdf"
    if name.endswith((".csv",)):
        return raw.decode("utf-8", errors="ignore"), "text/csv"
    if name.endswith((".json",)):
        return raw.decode("utf-8", errors="ignore"), "application/json"
    if name.endswith((".md",)):
        return raw.decode("utf-8", errors="ignore"), "text/markdown"
    if name.endswith((".html", ".htm")):
        from html.parser import HTMLParser

        class _Strip(HTMLParser):
            def __init__(self):
                super().__init__()
                self.parts: list[str] = []

            def handle_data(self, data):  # noqa: D102
                if data.strip():
                    self.parts.append(data.strip())

        p = _Strip()
        p.feed(raw.decode("utf-8", errors="ignore"))
        return "\n".join(p.parts), "text/html"
    if name.endswith(".docx"):
        try:
            import zipfile
            from xml.etree import ElementTree

            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                xml = z.read("word/document.xml")
            ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            paras = [
                "".join(t.text or "" for t in el.iter(f"{ns}t"))
                for el in ElementTree.fromstring(xml).iter(f"{ns}p")
            ]
            return "\n\n".join(p for p in paras if p.strip()), (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
        except Exception as e:  # noqa: BLE001
            log.warning(f"docx parse failed: {e}")
    if name.endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff")):
        text = _ocr_image(raw)
        if text:
            return text, "image/" + name.rsplit(".", 1)[-1]
        return "", "image/" + name.rsplit(".", 1)[-1]
    text = raw.decode("utf-8", errors="ignore")
    return text, "text/plain"


def _ocr_image(raw: bytes) -> str:
    """OCR an image via pytesseract when tesseract is installed; else no-op."""
    try:
        from PIL import Image

        import pytesseract

        img = Image.open(io.BytesIO(raw))
        return pytesseract.image_to_string(img).strip()
    except Exception as e:  # noqa: BLE001
        log.warning(
            f"image OCR unavailable (install tesseract + pytesseract + pillow): {e}"
        )
        return ""


def _page_segments(text: str) -> list[tuple[int, str]]:
    """Split text into (page_number, page_text) using PAGE_MARKER boundaries.

    Non-PDF text has no markers and collapses to a single page-1 segment.
    """
    if PAGE_MARKER in text:
        segments = []
        for i, seg in enumerate(text.split(PAGE_MARKER)):
            if seg.strip():
                segments.append((i + 1, seg))
        return segments
    return [(1, text)]


def chunks_for_document(
    filename: str, text: str, doc_type: str
) -> list[dict]:
    """Build chunk docs ready to persist (embedding filled in by the caller).

    Page-aware: PDF pages are preserved as `page` numbers on each chunk so
    citations can point at the exact source page.
    """
    chunks = []
    order = 0
    for page, page_text in _page_segments(text):
        texts, _ = split_by_type(page_text, doc_type)
        for t in texts:
            if not t.strip():
                continue
            chunks.append(
                {
                    "text": t.strip(),
                    "page": page,
                    "order": order,
                    "token_count": len(t.split()),
                }
            )
            order += 1
    return chunks