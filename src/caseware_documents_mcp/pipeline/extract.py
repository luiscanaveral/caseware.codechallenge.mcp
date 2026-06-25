import re

from .. import settings
from ..db.schema import get_connection


def parse_invoice(text: str, filename: str) -> dict | None:
    data: dict = {"invoice_number": None, "po_number": None, "vendor": None, "amount": None, "date": None}

    m = re.search(r"Order ID:\s*(\d+)", text)
    if m:
        data["po_number"] = m.group(1)

    m = re.search(r"Invoice no[:\s]+(\S+)", text, re.IGNORECASE)
    if m:
        data["invoice_number"] = m.group(1)

    m = re.search(r"Order Date:\s*([\d-]+)", text)
    if m:
        data["date"] = m.group(1)

    m = re.search(r"Date of issue:\s*([\d/]+)", text)
    if m and not data["date"]:
        parts = m.group(1).split("/")
        if len(parts) == 3:
            data["date"] = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"

    m = re.search(r"Total(?:Price|Due)?[:\s]*\$?([\d,.]+)", text)
    if m:
        raw = m.group(1).replace(",", "")
        try:
            data["amount"] = float(raw)
        except ValueError:
            pass

    m = re.search(r"Sub Total[:\s]*\$?([\d,.]+)", text)
    if m and not data["amount"]:
        raw = m.group(1).replace(",", "")
        try:
            data["amount"] = float(raw)
        except ValueError:
            pass

    m = re.search(r"Contact Name:\s*\n(.+)", text)
    if m:
        data["vendor"] = m.group(1).strip()

    m = re.search(r"Customer Name:\s*(.+)", text)
    if m and not data["vendor"]:
        data["vendor"] = m.group(1).strip()

    m = re.search(r"Seller:\s*\n(.+)", text)
    if m and not data["vendor"]:
        data["vendor"] = m.group(1).strip()

    if not data["invoice_number"]:
        m = re.search(r"invoice[_\s]?(\d+)", filename, re.IGNORECASE)
        if m:
            data["invoice_number"] = "INV-" + m.group(1)

    return data if any(v is not None for v in data.values()) else None


def parse_purchase_order(text: str, filename: str) -> dict | None:
    data: dict = {"po_number": None, "vendor": None, "amount": None, "date": None}

    m = re.search(r"Order ID[\s\S]*?(\d{4,})", text)
    if m:
        data["po_number"] = m.group(1)

    m = re.search(r"Order Date[\s\S]*?([\d-]+)", text)
    if m:
        data["date"] = m.group(1)

    m = re.search(r"Customer Name[\s\S]*?(.+?)(?:\nProducts|\Z)", text)
    if m:
        data["vendor"] = m.group(1).strip()

    amounts = re.findall(r"Unit Price:\s*\$?([\d,.]+)", text)
    quantities = re.findall(r"Quantity:\s*(\d+)", text)
    unit_prices = re.findall(r"Unit Price:\s*\$?([\d,.]+)", text)
    if quantities and unit_prices and len(quantities) == len(unit_prices):
        total = 0.0
        for q, up in zip(quantities, unit_prices):
            try:
                total += int(q) * float(up.replace(",", ""))
            except ValueError:
                pass
        if total > 0:
            data["amount"] = round(total, 2)

    return data if data["po_number"] else None


def parse_shipping_order(text: str, filename: str) -> dict | None:
    data: dict = {"shipment_number": None, "po_number": None, "date": None}

    m = re.search(r"Order ID:\s*(\d+)", text)
    if m:
        data["po_number"] = m.group(1)
        data["shipment_number"] = m.group(1)

    m = re.search(r"Shipped Date:\s*([\d-]+)", text)
    if m:
        data["date"] = m.group(1)

    if not data["shipment_number"]:
        m = re.search(r"(\d+)", filename)
        if m:
            data["shipment_number"] = m.group(1)

    return data if data["shipment_number"] else None


def parse_inventory_report(text: str, filename: str) -> dict | None:
    data: dict = {"period": None, "item_counts": None}

    m = re.search(r"Stock Report for\s+([\d-]+)", text)
    if m:
        data["period"] = m.group(1)

    product_lines = re.findall(r"^(\w[\w\s\-']+?)\s+(\d+)\s+(\d+)", text, re.MULTILINE)
    if product_lines:
        counts = {}
        for name, sold, stock in product_lines:
            counts[name.strip()] = int(stock)
        data["item_counts"] = str(counts)

    return data if data["period"] else None


def parse_contract(text: str, filename: str) -> dict | None:
    data: dict = {"vendor": None, "contract_terms": None}

    m = re.search(r'"([^"]+)"\);\s*\n\s*and\s*\n\s*\(2\)\s*\n\s*\[([^\]]+)\]', text[:settings.CONTRACT_REGEX_WINDOW])
    if m:
        data["vendor"] = m.group(2).strip()

    if not data["vendor"]:
        m = re.search(r"Supplier Signatory[\s\S]*?\[([^\]]+)\]", text[:settings.CONTRACT_REGEX_WINDOW])
        if m:
            data["vendor"] = m.group(1).strip()

    data["contract_terms"] = text[:settings.CONTRACT_TERMS_MAX_CHARS]

    return data


PARSERS = {
    "invoice": parse_invoice,
    "purchase_order": parse_purchase_order,
    "shipping_order": parse_shipping_order,
    "inventory_report": parse_inventory_report,
    "contract": parse_contract,
}


def extract_all():
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, filename, document_type, raw_text FROM documents ORDER BY id"
    ).fetchall()

    for row in rows:
        doc_id = row["id"]
        doc_type = row["document_type"]
        raw_text = row["raw_text"]
        filename = row["filename"]

        parser = PARSERS.get(doc_type)
        if not parser:
            continue

        parsed = parser(raw_text, filename)
        if not parsed:
            continue

        table_name = settings.TABLE_MAP[doc_type]
        fields = settings.TABLE_COLUMNS[table_name]

        values = [doc_id]
        for field in fields[1:]:
            values.append(parsed.get(field))

        placeholders = ", ".join("?" for _ in fields)
        columns = ", ".join(fields)
        conn.execute(
            f"INSERT OR IGNORE INTO {table_name} ({columns}) VALUES ({placeholders})",
            values,
        )

    conn.commit()
    conn.close()
