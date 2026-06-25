from ..db.queries import (
    get_invoices_missing_po,
    get_related_to_po,
    search_structured,
)


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

    po_match = None
    m = __import__("re").search(r"order\s*(?:number\s*)?(\d{4,})", q)
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
