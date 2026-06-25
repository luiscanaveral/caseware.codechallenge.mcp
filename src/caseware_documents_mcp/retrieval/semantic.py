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


def _token_overlap(query: str, text: str) -> float:
    q_tokens = set(query.lower().split())
    d_tokens = set(text.lower().split())
    if not q_tokens or not d_tokens:
        return 0.0
    inter = len(q_tokens & d_tokens)
    return inter / (len(q_tokens) + len(d_tokens) - inter)


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
    cosine_scores = chunk_norms @ query_norm

    overlap_scores = np.array([_token_overlap(query, r["text"]) for r in chunk_rows])
    scores = settings.COSINE_WEIGHT * cosine_scores + (1 - settings.COSINE_WEIGHT) * overlap_scores

    all_indices = np.argsort(scores)[::-1]

    seen_docs = set()
    results = []
    for idx in all_indices:
        if scores[idx] < settings.COSINE_THRESHOLD:
            continue
        chunk = chunk_rows[idx]
        if chunk["document_id"] in seen_docs:
            continue
        doc = get_document_by_id(chunk["document_id"])
        if not doc:
            continue
        if doc_type and doc["document_type"] != doc_type:
            continue
        seen_docs.add(chunk["document_id"])
        results.append({
            "chunk_id": chunk["id"],
            "text": chunk["text"][:settings.TEXT_TRUNCATE],
            "page": chunk.get("page"),
            "score": float(scores[idx]),
            "file": doc["filename"],
            "document_type": doc["document_type"],
        })
        if len(results) >= top_k:
            break

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
