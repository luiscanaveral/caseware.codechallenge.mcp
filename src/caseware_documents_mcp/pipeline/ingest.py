import os
from pathlib import Path

import fitz
from PIL import Image
import pytesseract

from .. import settings
from ..models import Document
from ..db.schema import get_connection


def extract_text_from_pdf(path: str) -> tuple[str, int, bool]:
    doc = fitz.open(path)
    text_parts = []
    for page in doc:
        text_parts.append(page.get_text())
    full_text = "\n".join(text_parts)
    return full_text, len(doc), False


def extract_text_from_image(path: str) -> tuple[str, int, bool]:
    img = Image.open(path)
    text = pytesseract.image_to_string(img)
    return text, 1, True


def extract_text(path: str) -> tuple[str, int, bool]:
    ext = Path(path).suffix.lower()
    if ext in settings.OCR_EXTENSIONS:
        return extract_text_from_image(path)
    else:
        return extract_text_from_pdf(path)


def ingest_all() -> list[Document]:
    conn = get_connection()
    documents = []
    data_dir = Path(settings.DATA_DIR)

    for subdir, doc_type in settings.DOCUMENT_TYPE_MAP.items():
        dir_path = data_dir / subdir
        if not dir_path.exists():
            continue

        for file_path in sorted(dir_path.iterdir()):
            if file_path.name.startswith(".") or file_path.suffix.lower() not in settings.ALLOWED_EXTENSIONS:
                continue

            text, page_count, ocr_used = extract_text(str(file_path))

            if not text.strip():
                continue

            doc = Document(
                filename=file_path.name,
                document_type=doc_type,
                raw_text=text,
                ocr_used=ocr_used,
                page_count=page_count,
            )

            conn.execute(
                "INSERT OR IGNORE INTO documents (filename, document_type, raw_text, ocr_used, page_count) VALUES (?, ?, ?, ?, ?)",
                (doc.filename, doc.document_type, doc.raw_text, int(doc.ocr_used), doc.page_count),
            )
            row = conn.execute("SELECT id FROM documents WHERE filename = ?", (doc.filename,)).fetchone()
            doc.id = row["id"]
            documents.append(doc)

    conn.commit()
    conn.close()
    return documents
