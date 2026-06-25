from .. import settings
from .schema import get_connection


def get_invoices_missing_po():
    conn = get_connection()
    rows = conn.execute("""
        SELECT i.*, d.filename
        FROM invoices i
        JOIN documents d ON d.id = i.document_id
        WHERE i.po_number IS NULL OR i.po_number = ''
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_document_by_id(doc_id: int):
    conn = get_connection()
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_structured_by_type(doc_type: str, limit: int | None = None):
    limit = limit or settings.DEFAULT_SEARCH_LIMIT
    table = settings.TABLE_MAP.get(doc_type)
    if not table:
        return []

    conn = get_connection()
    rows = conn.execute(f"""
        SELECT t.*, d.filename, d.document_type
        FROM {table} t
        JOIN documents d ON d.id = t.document_id
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_related_to_po(po_id: int):
    conn = get_connection()
    result = {
        "purchase_order": None,
        "invoices": [],
        "shipments": [],
    }

    po = conn.execute("""
        SELECT p.*, d.filename, d.document_type
        FROM purchase_orders p
        JOIN documents d ON d.id = p.document_id
        WHERE p.id = ?
    """, (po_id,)).fetchone()
    if po:
        result["purchase_order"] = dict(po)

    invoices = conn.execute("""
        SELECT i.*, d.filename, d.document_type
        FROM invoices i
        JOIN documents d ON d.id = i.document_id
        JOIN invoice_po_match m ON m.invoice_id = i.id
        WHERE m.po_id = ?
        ORDER BY m.confidence DESC
    """, (po_id,)).fetchall()
    result["invoices"] = [dict(r) for r in invoices]

    shipments = conn.execute("""
        SELECT s.*, d.filename, d.document_type
        FROM shipping_orders s
        JOIN documents d ON d.id = s.document_id
        JOIN shipment_po_match m ON m.shipment_id = s.id
        WHERE m.po_id = ?
        ORDER BY m.confidence DESC
    """, (po_id,)).fetchall()
    result["shipments"] = [dict(r) for r in shipments]

    conn.close()
    return result


def search_structured(query: str, doc_type: str | None = None, limit: int | None = None):
    limit = limit or settings.DEFAULT_SEARCH_LIMIT
    conn = get_connection()
    like = f"%{query}%"
    table_config = settings.SEARCHABLE_COLUMNS

    if doc_type:
        table = settings.TABLE_MAP.get(doc_type)
        if not table or table not in table_config:
            conn.close()
            return []
        cols = table_config[table]
        conditions = " OR ".join(f"CAST(t.{c} AS TEXT) LIKE ?" for c in cols)
        params = tuple(like for _ in cols) + (limit,)
        rows = conn.execute(f"""
            SELECT t.*, d.filename, d.document_type
            FROM {table} t
            JOIN documents d ON d.id = t.document_id
            WHERE {conditions}
            LIMIT ?
        """, params).fetchall()
    else:
        results = []
        for table, cols in table_config.items():
            conditions = " OR ".join(f"CAST(t.{c} AS TEXT) LIKE ?" for c in cols)
            params = tuple(like for _ in cols) + (limit,)
            try:
                type_rows = conn.execute(f"""
                    SELECT t.*, d.filename, d.document_type
                    FROM {table} t
                    JOIN documents d ON d.id = t.document_id
                    WHERE {conditions}
                    LIMIT ?
                """, params).fetchall()
                results.extend([dict(r) for r in type_rows])
            except Exception:
                continue
        rows = results[:limit]

    conn.close()
    return [dict(r) for r in rows] if not isinstance(rows, list) else rows
