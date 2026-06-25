"""FastMCP wrapper for `mcp dev` compatibility."""

from caseware_documents_mcp import settings
from caseware_documents_mcp.db.queries import search_structured, get_document_by_id, get_related_to_po
from caseware_documents_mcp.retrieval.classifier import classify_question
from caseware_documents_mcp.retrieval.structured import answer_structured
from caseware_documents_mcp.retrieval.semantic import semantic_search, get_chunks_for_document

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(settings.SERVER_NAME, log_level=settings.LOG_LEVEL.upper())


def _build_citation(chunk: dict) -> str:
    parts = []
    if chunk.get("file"):
        parts.append(chunk["file"])
    if chunk.get("page"):
        parts.append(f"page {chunk['page']}")
    if chunk.get("chunk_id"):
        parts.append(f"chunk {chunk['chunk_id']}")
    return " - ".join(parts)


def _format_sources(sources: list[dict]) -> str:
    if not sources:
        return ""
    lines = ["\n\nSources:"]
    seen = set()
    for s in sources:
        key = f"{s.get('file', '')}:{s.get('page', '')}"
        if key not in seen:
            seen.add(key)
            page = f" page {s['page']}" if s.get("page") else ""
            lines.append(f"- {s['file']}{page}")
    return "\n".join(lines)


@mcp.tool(
    name="search_documents",
    description="Search documents by keyword or phrase. Optionally filter by document type.",
)
def search_documents(query: str, document_type: str | None = None) -> str:
    structured = search_structured(query, document_type, limit=5)
    semantic = semantic_search(query, document_type, top_k=5)
    lines = [f"Search results for: {query}"]
    if document_type:
        lines[0] += f" (filtered by: {document_type})"
    if structured:
        lines.append("\n### Structured Matches")
        for r in structured[:5]:
            label = r.get("invoice_number") or r.get("po_number") or r.get("vendor") or f"ID {r['id']}"
            lines.append(f"- **{label}** ({r['filename']})")
    if semantic:
        lines.append("\n### Semantic Matches")
        for r in semantic[:5]:
            lines.append(f"- {r['text'][:200]}...")
            lines.append(f"  *Source: {_build_citation(r)} (score: {r['score']:.2f})*")
    if not structured and not semantic:
        lines.append("\nNo results found.")
    return "\n".join(lines)


@mcp.tool(
    name="get_related_documents",
    description="Find all documents related to a given document ID.",
)
def get_related_documents(document_id: int) -> str:
    doc = get_document_by_id(document_id)
    if not doc:
        return f"Document with ID {document_id} not found."
    lines = [f"Related documents for: {doc['filename']} (type: {doc['document_type']})"]

    from caseware_documents_mcp.db.schema import get_connection
    conn = get_connection()

    if doc["document_type"] == "invoice":
        inv = conn.execute("SELECT id, po_number FROM invoices WHERE document_id = ?", (document_id,)).fetchone()
        if inv and inv["po_number"]:
            po = conn.execute("SELECT id FROM purchase_orders WHERE po_number = ?", (inv["po_number"],)).fetchone()
            if po:
                related = get_related_to_po(po["id"])
                for inv_rel in related.get("invoices", []):
                    if inv_rel.get("filename") != doc["filename"]:
                        lines.append(f"- Invoice: {inv_rel.get('invoice_number', 'N/A')} ({inv_rel['filename']})")
                for ship in related.get("shipments", []):
                    lines.append(f"- Shipment: {ship.get('shipment_number', 'N/A')} ({ship['filename']})")
        chunks = get_chunks_for_document(document_id)
        if chunks:
            lines.append(f"\nDocument has {len(chunks)} indexed chunk(s).")

    elif doc["document_type"] == "purchase_order":
        po = conn.execute("SELECT id, po_number FROM purchase_orders WHERE document_id = ?", (document_id,)).fetchone()
        if po:
            related = get_related_to_po(po["id"])
            for inv in related.get("invoices", []):
                lines.append(f"- Invoice: {inv.get('invoice_number', 'N/A')} ({inv['filename']})")
            for ship in related.get("shipments", []):
                lines.append(f"- Shipment: {ship.get('shipment_number', 'N/A')} ({ship['filename']})")

    elif doc["document_type"] == "shipping_order":
        ship = conn.execute("SELECT po_number FROM shipping_orders WHERE document_id = ?", (document_id,)).fetchone()
        if ship and ship["po_number"]:
            po = conn.execute("SELECT id FROM purchase_orders WHERE po_number = ?", (ship["po_number"],)).fetchone()
            if po:
                related = get_related_to_po(po["id"])
                po_data = related.get("purchase_order")
                if po_data:
                    lines.append(f"- Purchase Order: {po_data.get('po_number', 'N/A')} ({po_data['filename']})")
                for inv in related.get("invoices", []):
                    lines.append(f"- Invoice: {inv.get('invoice_number', 'N/A')} ({inv['filename']})")

    conn.close()

    if len(lines) == 1:
        lines.append("No related documents found.")
    return "\n".join(lines)


@mcp.tool(
    name="find_order_evidence",
    description="Trace an order number across invoices, POs, and shipments.",
)
def find_order_evidence(order_number: str) -> str:
    lines = [f"## Evidence chain for order: {order_number}"]

    from caseware_documents_mcp.db.schema import get_connection
    conn = get_connection()

    po_row = conn.execute(
        "SELECT p.*, d.filename FROM purchase_orders p JOIN documents d ON d.id = p.document_id WHERE p.po_number = ?",
        (order_number,),
    ).fetchone()
    po = dict(po_row) if po_row else None

    if po:
        lines.append(f"\n### Purchase Order: {po.get('po_number', 'N/A')}")
        lines.append(f"- File: {po.get('filename', 'N/A')}")
        lines.append(f"- Vendor: {po.get('vendor', 'N/A')}")
        lines.append(f"- Amount: ${po.get('amount', 'N/A')}")

    inv_row = conn.execute(
        "SELECT i.*, d.filename FROM invoices i JOIN documents d ON d.id = i.document_id WHERE i.po_number = ?",
        (order_number,),
    ).fetchone()
    inv = dict(inv_row) if inv_row else None

    if inv:
        lines.append(f"\n### Invoice: {inv.get('invoice_number', 'N/A')}")
        lines.append(f"- File: {inv.get('filename', 'N/A')}")
        lines.append(f"- Amount: ${inv.get('amount', 'N/A')}")

    ship_rows = conn.execute(
        "SELECT s.*, d.filename FROM shipping_orders s JOIN documents d ON d.id = s.document_id WHERE s.po_number = ?",
        (order_number,),
    ).fetchall()
    for ship in [dict(r) for r in ship_rows]:
        lines.append(f"\n### Shipment: {ship.get('shipment_number', 'N/A')}")
        lines.append(f"- File: {ship.get('filename', 'N/A')}")

    conn.close()
    if len(lines) == 1:
        lines.append(f"\nNo documents found for order {order_number}.")
    return "\n".join(lines)


def _generate_llm_answer(question: str, context: str) -> str:
    try:
        import ollama
        prompt = f"""You are a procurement document analyst. Answer the question based ONLY on the provided context. If the context doesn't contain enough information, say so.

Context:
{context}

Question: {question}

Provide a concise, factual answer with specific numbers and references where possible."""
        response = ollama.chat(
            model=settings.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": settings.LLM_TEMPERATURE, "num_predict": settings.LLM_NUM_PREDICT},
        )
        return response["message"]["content"].strip()
    except Exception as e:
        import logging
        logging.getLogger("caseware-mcp").warning(f"Ollama call failed: {e}")
        return "Could not generate an answer (Ollama unavailable)."


@mcp.tool(
    name="answer_question",
    description="Answer a question about the documents. Supports structured and semantic queries.",
)
def answer_question(question: str) -> str:
    route = classify_question(question)

    if route == "structured":
        result = answer_structured(question)
        answer = result["answer"]
        sources = result.get("sources", [])
    else:
        results = semantic_search(question, top_k=5)
        if not results:
            answer = "I couldn't find relevant information in the documents."
            sources = []
        else:
            context = "\n\n".join([f"[Source: {_build_citation(r)}]\n{r['text']}" for r in results])
            answer = _generate_llm_answer(question, context)
            sources = results

    return answer + _format_sources(sources)
