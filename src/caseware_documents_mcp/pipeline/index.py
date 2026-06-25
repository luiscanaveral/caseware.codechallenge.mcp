from .. import settings
from ..db.schema import get_connection


def normalize_po_number(po: str | None) -> str | None:
    if not po:
        return None
    digits = "".join(c for c in po if c.isdigit())
    return digits if digits else None


def build_invoice_po_matches():
    conn = get_connection()

    conn.execute("DELETE FROM invoice_po_match")

    invoices = conn.execute(
        "SELECT i.id, i.invoice_number, i.po_number, i.vendor, i.amount, i.date FROM invoices i WHERE i.po_number IS NOT NULL"
    ).fetchall()

    pos = conn.execute(
        "SELECT p.id, p.po_number, p.vendor, p.amount, p.date FROM purchase_orders p WHERE p.po_number IS NOT NULL"
    ).fetchall()

    po_index = {}
    for po in pos:
        norm = normalize_po_number(po["po_number"])
        if norm:
            po_index.setdefault(norm, []).append(po)

    for inv in invoices:
        norm_inv_po = normalize_po_number(inv["po_number"])

        matched = False

        if norm_inv_po and norm_inv_po in po_index:
            for po in po_index[norm_inv_po]:
                conn.execute(
                    "INSERT INTO invoice_po_match (invoice_id, po_id, confidence, match_method) VALUES (?, ?, ?, ?)",
                    (inv["id"], po["id"], settings.CONFIDENCE_EXACT, "po_number_exact"),
                )
                matched = True

        if not matched and inv["vendor"]:
            for po in pos:
                if po["vendor"] and inv["vendor"].lower() == po["vendor"].lower():
                    confidence = settings.CONFIDENCE_VENDOR
                    if inv["amount"] and po["amount"] and abs(inv["amount"] - po["amount"]) / max(inv["amount"], po["amount"]) < settings.AMOUNT_DIFF_RATIO:
                        confidence = settings.CONFIDENCE_VENDOR_AMOUNT
                    conn.execute(
                        "INSERT INTO invoice_po_match (invoice_id, po_id, confidence, match_method) VALUES (?, ?, ?, ?)",
                        (inv["id"], po["id"], confidence, "vendor_amount"),
                    )
                    matched = True

    conn.commit()
    return conn.execute("SELECT COUNT(*) FROM invoice_po_match").fetchone()[0]


def build_shipment_po_matches():
    conn = get_connection()

    conn.execute("DELETE FROM shipment_po_match")

    shipments = conn.execute(
        "SELECT s.id, s.shipment_number, s.po_number FROM shipping_orders s WHERE s.po_number IS NOT NULL"
    ).fetchall()

    pos = conn.execute(
        "SELECT p.id, p.po_number FROM purchase_orders p WHERE p.po_number IS NOT NULL"
    ).fetchall()

    po_index = {}
    for po in pos:
        norm = normalize_po_number(po["po_number"])
        if norm:
            po_index.setdefault(norm, []).append(po)

    for ship in shipments:
        norm_ship_po = normalize_po_number(ship["po_number"])
        if norm_ship_po and norm_ship_po in po_index:
            for po in po_index[norm_ship_po]:
                conn.execute(
                    "INSERT INTO shipment_po_match (shipment_id, po_id, confidence, match_method) VALUES (?, ?, ?, ?)",
                    (ship["id"], po["id"], settings.CONFIDENCE_EXACT, "po_number_exact"),
                )

    conn.commit()
    return conn.execute("SELECT COUNT(*) FROM shipment_po_match").fetchone()[0]


def build_cross_references():
    inv_count = build_invoice_po_matches()
    ship_count = build_shipment_po_matches()
    return inv_count, ship_count
