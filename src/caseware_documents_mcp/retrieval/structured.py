import re

from .. import settings
from ..db.queries import (
    get_invoices_missing_po,
    get_related_to_po,
    search_structured,
)


def _extract_entities(question: str) -> list[str]:
    terms = []
    numbers = re.findall(r"\b(\d{4,})\b", question)
    terms.extend(numbers)

    m = re.search(r"(?:for|from|by|of|to|named?\s+|called\s+)\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", question)
    if m:
        terms.append(m.group(1))

    return terms


def _search_tables_for(value: str) -> list[dict]:
    from ..db.schema import get_connection
    conn = get_connection()
    results = []
    for table_name in settings.SEARCHABLE_COLUMNS:
        cols = settings.SEARCHABLE_COLUMNS[table_name]
        conditions = " OR ".join(f"CAST(t.{c} AS TEXT) LIKE ?" for c in cols)
        params = tuple(f"%{value}%" for _ in cols)
        try:
            rows = conn.execute(
                f"""
                SELECT t.*, d.filename, d.document_type
                FROM {table_name} t
                JOIN documents d ON d.id = t.document_id
                WHERE {conditions}
                """,
                params,
            ).fetchall()
            for r in rows:
                results.append(dict(r))
        except Exception:
            continue
    conn.close()
    return results


def answer_structured(question: str) -> dict:
    q = question.lower()

    if "missing" in q and ("purchase order" in q or "po" in q):
        invoices = get_invoices_missing_po()
        if not invoices:
            return {
                "answer": "All invoices have a matching purchase order.",
                "sources": [],
            }
        lines = []
        for inv in invoices:
            lines.append(f"- Invoice #{inv['invoice_number'] or 'N/A'} ({inv['filename']})")
        return {
            "answer": f"The following {len(invoices)} invoice(s) are missing a purchase order:\n" + "\n".join(lines),
            "sources": [{"file": inv["filename"], "type": "invoice"} for inv in invoices],
        }

    m = re.search(r"order\s*(?:number\s*)?(\d{4,})", q)
    if m:
        po_num = m.group(1)
        from ..db.schema import get_connection
        conn = get_connection()
        po = conn.execute(
            "SELECT id FROM purchase_orders WHERE po_number = ?", (po_num,)
        ).fetchone()
        conn.close()
        if po:
            related = get_related_to_po(po["id"])
            po_data = related["purchase_order"]
            invoices = related["invoices"]
            shipments = related["shipments"]

            answer = f"**Order {po_num}**\n\n"
            if po_data:
                answer += f"- Vendor: {po_data.get('vendor', 'N/A')}\n"
                answer += f"- Amount: ${po_data.get('amount', 'N/A')}\n"
            answer += f"\n**Related Invoices ({len(invoices)}):**\n"
            for inv in invoices:
                answer += f"- {inv.get('invoice_number', 'N/A')} ({inv['filename']})\n"
            answer += f"\n**Related Shipments ({len(shipments)}):**\n"
            for ship in shipments:
                answer += f"- {ship.get('shipment_number', 'N/A')} ({ship['filename']})\n"

            sources = []
            if po_data:
                sources.append({"file": po_data["filename"], "type": "purchase_order"})
            for inv in invoices:
                sources.append({"file": inv["filename"], "type": "invoice"})
            for ship in shipments:
                sources.append({"file": ship["filename"], "type": "shipping_order"})

            return {"answer": answer, "sources": sources}

        fallback = _search_tables_for(po_num)
        if fallback:
            lines = []
            for r in fallback[:10]:
                label = r.get("invoice_number") or r.get("po_number") or r.get("vendor") or r.get("shipment_number") or f"ID {r['id']}"
                lines.append(f"- {label} ({r['filename']})")
            return {
                "answer": f"Documents related to order {po_num}:\n" + "\n".join(lines),
                "sources": [{"file": r["filename"], "type": r.get("document_type", "unknown")} for r in fallback[:10]],
            }

    entities = _extract_entities(question)
    for value in entities:
        if value.isdigit() and m and value == m.group(1):
            continue
        results = _search_tables_for(value)
        if results:
            lines = []
            seen = set()
            for r in results[:10]:
                key = r["filename"]
                if key in seen:
                    continue
                seen.add(key)
                label = r.get("invoice_number") or r.get("po_number") or r.get("vendor") or r.get("shipment_number") or f"ID {r['id']}"
                lines.append(f"- {label} ({r['filename']})")
            return {
                "answer": f"Documents matching '{value}':\n" + "\n".join(lines),
                "sources": [{"file": r["filename"], "type": r.get("document_type", "unknown")} for r in results[:10]],
            }

    results = search_structured(question)
    if results:
        lines = []
        for r in results[:10]:
            label = r.get("invoice_number") or r.get("po_number") or r.get("vendor") or f"ID {r['id']}"
            lines.append(f"- {label} ({r['filename']})")
        return {
            "answer": "Related documents:\n" + "\n".join(lines),
            "sources": [{"file": r["filename"], "type": r.get("document_type", "unknown")} for r in results[:10]],
        }

    return {"answer": "No structured results found.", "sources": []}
