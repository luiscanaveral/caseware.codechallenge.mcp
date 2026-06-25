import logging

from mcp.server import Server, NotificationOptions
from mcp.types import (
    TextContent,
    Tool,
)

from .. import settings
from ..db.schema import get_connection
from ..db.queries import search_structured, get_related_to_po
from ..retrieval.classifier import classify_question
from ..retrieval.structured import answer_structured
from ..retrieval.semantic import semantic_search, get_chunks_for_document

logger = logging.getLogger("caseware-mcp")


def format_sources(sources: list[dict]) -> str:
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


def build_citation(chunk: dict) -> str:
    parts = []
    if chunk.get("file"):
        parts.append(chunk["file"])
    if chunk.get("page"):
        parts.append(f"page {chunk['page']}")
    if chunk.get("chunk_id"):
        parts.append(f"chunk {chunk['chunk_id']}")
    return " - ".join(parts)


server = Server("caseware-documents-mcp")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_documents",
            description="Search documents by keyword or phrase. Optionally filter by document type (invoice, purchase_order, shipping_order, inventory_report, contract).",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "document_type": {
                        "type": "string",
                        "description": "Optional: filter by document type",
                        "enum": sorted(settings.DOCUMENT_TYPES) + [None],
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_related_documents",
            description="Find all documents related to a given document ID (invoice, PO, shipment, etc.)",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {
                        "type": "integer",
                        "description": "Document ID to find related documents for",
                    },
                },
                "required": ["document_id"],
            },
        ),
        Tool(
            name="find_order_evidence",
            description="Trace an order number across all document types (invoices, purchase orders, shipments). Returns a complete evidence chain with citations.",
            inputSchema={
                "type": "object",
                "properties": {
                    "order_number": {
                        "type": "string",
                        "description": "Order number to trace (e.g. '10687')",
                    },
                },
                "required": ["order_number"],
            },
        ),
        Tool(
            name="answer_question",
            description="Answer a question about the documents. Supports both structured queries (e.g. 'which invoices are missing a PO?') and semantic queries (e.g. 'summarize contract terms'). Returns grounded answers with citations.",
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Natural language question about the documents",
                    },
                },
                "required": ["question"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "search_documents":
        return await handle_search(arguments)
    elif name == "get_related_documents":
        return await handle_get_related(arguments)
    elif name == "find_order_evidence":
        return await handle_find_order(arguments)
    elif name == "answer_question":
        return await handle_answer(arguments)
    else:
        raise ValueError(f"Unknown tool: {name}")


async def handle_search(args: dict) -> list[TextContent]:
    query = args["query"]
    doc_type = args.get("document_type")

    structured_results = search_structured(query, doc_type, limit=5)
    semantic_results = semantic_search(query, doc_type, top_k=5)

    lines = [f"Search results for: {query}"]
    if doc_type:
        lines[0] += f" (filtered by: {doc_type})"

    if structured_results:
        lines.append("\n### Structured Matches")
        for r in structured_results[:5]:
            label = r.get("invoice_number") or r.get("po_number") or r.get("vendor") or f"ID {r['id']}"
            lines.append(f"- **{label}** ({r['filename']})")

    if semantic_results:
        lines.append("\n### Semantic Matches")
        for r in semantic_results[:5]:
            lines.append(f"- {r['text'][:200]}...")
            lines.append(f"  *Source: {build_citation(r)} (score: {r['score']:.2f})*")

    if not structured_results and not semantic_results:
        lines.append("\nNo results found.")

    return [TextContent(type="text", text="\n".join(lines))]


async def handle_get_related(args: dict) -> list[TextContent]:
    doc_id = args["document_id"]

    from ..db.queries import get_document_by_id
    doc = get_document_by_id(doc_id)
    if not doc:
        return [TextContent(type="text", text=f"Document with ID {doc_id} not found.")]

    lines = [f"Related documents for: {doc['filename']} (type: {doc['document_type']})"]

    conn = get_connection()

    if doc["document_type"] == "invoice":
        inv = conn.execute("SELECT id, po_number FROM invoices WHERE document_id = ?", (doc_id,)).fetchone()
        if inv and inv["po_number"]:
            po = conn.execute(
                "SELECT id FROM purchase_orders WHERE po_number = ?", (inv["po_number"],)
            ).fetchone()
            if po:
                related = get_related_to_po(po["id"])
                for inv_rel in related.get("invoices", []):
                    if inv_rel.get("filename") != doc["filename"]:
                        lines.append(f"- Invoice: {inv_rel.get('invoice_number', 'N/A')} ({inv_rel['filename']})")
                for ship in related.get("shipments", []):
                    lines.append(f"- Shipment: {ship.get('shipment_number', 'N/A')} ({ship['filename']})")
        chunks = get_chunks_for_document(doc_id)
        if chunks:
            lines.append(f"\nDocument has {len(chunks)} indexed chunk(s).")

    elif doc["document_type"] == "purchase_order":
        po = conn.execute("SELECT id, po_number FROM purchase_orders WHERE document_id = ?", (doc_id,)).fetchone()
        if po:
            related = get_related_to_po(po["id"])
            for inv in related.get("invoices", []):
                lines.append(f"- Invoice: {inv.get('invoice_number', 'N/A')} ({inv['filename']})")
            for ship in related.get("shipments", []):
                lines.append(f"- Shipment: {ship.get('shipment_number', 'N/A')} ({ship['filename']})")

    elif doc["document_type"] == "shipping_order":
        ship = conn.execute("SELECT po_number FROM shipping_orders WHERE document_id = ?", (doc_id,)).fetchone()
        if ship and ship["po_number"]:
            po = conn.execute(
                "SELECT id FROM purchase_orders WHERE po_number = ?", (ship["po_number"],)
            ).fetchone()
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

    return [TextContent(type="text", text="\n".join(lines))]


async def handle_find_order(args: dict) -> list[TextContent]:
    order_number = args["order_number"]
    lines = [f"## Evidence chain for order: {order_number}"]

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
    shipments = [dict(r) for r in ship_rows]

    if shipments:
        for ship in shipments:
            lines.append(f"\n### Shipment: {ship.get('shipment_number', 'N/A')}")
            lines.append(f"- File: {ship.get('filename', 'N/A')}")

    conn.close()

    if len(lines) == 1:
        lines.append(f"\nNo documents found for order {order_number}.")

    return [TextContent(type="text", text="\n".join(lines))]


async def handle_answer(args: dict) -> list[TextContent]:
    question = args["question"]
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
            context = "\n\n".join([f"[Source: {build_citation(r)}]\n{r['text']}" for r in results])
            answer = _generate_llm_answer(question, context, results)
            sources = results

    source_text = format_sources(sources)
    return [TextContent(type="text", text=answer + source_text)]


def _generate_llm_answer(question: str, context: str, results: list[dict]) -> str:
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
        logger.warning(f"Ollama call failed: {e}")
        fallback = []
        for r in results[:3]:
            fallback.append(f"- {r['text'][:200]}")
        return "Relevant excerpts:\n" + "\n".join(fallback)
