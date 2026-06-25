from sentence_transformers import SentenceTransformer

from .. import settings
from ..db.schema import get_connection

_model = None


def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(settings.EMBEDDING_MODEL)
    return _model


def chunk_text(text: str, page: int | None = None, chunk_size: int | None = None, overlap: int | None = None) -> list[dict]:
    chunk_size = chunk_size or settings.CHUNK_SIZE
    paragraphs = text.split("\n\n")
    chunks = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) < chunk_size:
            current += "\n\n" + para if current else para
        else:
            if current:
                chunks.append({"text": current.strip(), "page": page})
            current = para
    if current:
        chunks.append({"text": current.strip(), "page": page})
    return chunks


def embed_all():
    model = get_model()
    conn = get_connection()

    rows = conn.execute(
        "SELECT id, raw_text FROM documents ORDER BY id"
    ).fetchall()

    for row in rows:
        doc_id = row["id"]
        raw_text = row["raw_text"]

        existing = conn.execute(
            "SELECT COUNT(*) FROM document_chunks WHERE document_id = ?", (doc_id,)
        ).fetchone()[0]
        if existing > 0:
            continue

        chunks = chunk_text(raw_text)
        if not chunks:
            continue

        texts = [c["text"] for c in chunks]
        embeddings = model.encode(texts, show_progress_bar=False)

        for i, chunk in enumerate(chunks):
            conn.execute(
                "INSERT INTO document_chunks (document_id, chunk_index, text, page) VALUES (?, ?, ?, ?)",
                (doc_id, i, chunk["text"], chunk.get("page")),
            )

    conn.commit()
    conn.close()
    return True
