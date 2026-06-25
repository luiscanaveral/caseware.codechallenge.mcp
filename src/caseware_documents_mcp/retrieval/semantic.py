import numpy as np
from sentence_transformers import SentenceTransformer

from .. import settings
from ..db.schema import get_connection
from ..db.queries import get_document_by_id

_model = None


def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(settings.EMBEDDING_MODEL)
    return _model


def semantic_search(query: str, doc_type: str | None = None, top_k: int | None = None) -> list[dict]:
    top_k = top_k or settings.SEMANTIC_TOP_K
    model = get_model()
    conn = get_connection()

    query_emb = model.encode([query], show_progress_bar=False)[0]

    chunks = conn.execute(
        "SELECT id, document_id, chunk_index, text, page FROM document_chunks"
    ).fetchall()

    if not chunks:
        conn.close()
        return []

    chunk_rows = [dict(c) for c in chunks]
    chunk_texts = [c["text"] for c in chunk_rows]

    chunk_embs = model.encode(chunk_texts, show_progress_bar=False)

    query_norm = query_emb / np.linalg.norm(query_emb)
    chunk_norms = chunk_embs / np.linalg.norm(chunk_embs, axis=1, keepdims=True)
    scores = chunk_norms @ query_norm

    top_indices = np.argsort(scores)[::-1][:top_k]

    results = []
    for idx in top_indices:
        if scores[idx] < settings.COSINE_THRESHOLD:
            continue
        chunk = chunk_rows[idx]
        doc = get_document_by_id(chunk["document_id"])
        if not doc:
            continue
        if doc_type and doc["document_type"] != doc_type:
            continue
        results.append({
            "chunk_id": chunk["id"],
            "text": chunk["text"][:settings.TEXT_TRUNCATE],
            "page": chunk.get("page"),
            "score": float(scores[idx]),
            "file": doc["filename"],
            "document_type": doc["document_type"],
        })

    conn.close()
    return results


def get_chunks_for_document(document_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, chunk_index, text, page FROM document_chunks WHERE document_id = ? ORDER BY chunk_index",
        (document_id,),
    ).fetchall()
    chunks = [dict(r) for r in rows]
    doc = get_document_by_id(document_id)
    conn.close()
    return [
        {
            "chunk_id": c["id"],
            "text": c["text"][:settings.TEXT_TRUNCATE],
            "page": c.get("page"),
            "file": doc["filename"] if doc else None,
        }
        for c in chunks
    ]
