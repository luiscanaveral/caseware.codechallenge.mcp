import sqlite3

from .. import settings


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            document_type TEXT NOT NULL,
            raw_text TEXT NOT NULL,
            ocr_used INTEGER DEFAULT 0,
            page_count INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL REFERENCES documents(id),
            invoice_number TEXT,
            po_number TEXT,
            vendor TEXT,
            amount REAL,
            date TEXT
        );

        CREATE TABLE IF NOT EXISTS purchase_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL REFERENCES documents(id),
            po_number TEXT,
            vendor TEXT,
            amount REAL,
            date TEXT
        );

        CREATE TABLE IF NOT EXISTS shipping_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL REFERENCES documents(id),
            shipment_number TEXT,
            po_number TEXT,
            date TEXT
        );

        CREATE TABLE IF NOT EXISTS inventory_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL REFERENCES documents(id),
            period TEXT,
            item_counts TEXT
        );

        CREATE TABLE IF NOT EXISTS contracts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL REFERENCES documents(id),
            vendor TEXT,
            contract_terms TEXT
        );

        CREATE TABLE IF NOT EXISTS document_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL REFERENCES documents(id),
            chunk_index INTEGER NOT NULL,
            text TEXT NOT NULL,
            page INTEGER
        );

        CREATE TABLE IF NOT EXISTS invoice_po_match (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL REFERENCES invoices(id),
            po_id INTEGER NOT NULL REFERENCES purchase_orders(id),
            confidence REAL NOT NULL DEFAULT 1.0,
            match_method TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS shipment_po_match (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shipment_id INTEGER NOT NULL REFERENCES shipping_orders(id),
            po_id INTEGER NOT NULL REFERENCES purchase_orders(id),
            confidence REAL NOT NULL DEFAULT 1.0,
            match_method TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_invoices_po ON invoices(po_number);
        CREATE INDEX IF NOT EXISTS idx_purchase_orders_po ON purchase_orders(po_number);
        CREATE INDEX IF NOT EXISTS idx_shipping_orders_po ON shipping_orders(po_number);
        CREATE INDEX IF NOT EXISTS idx_invoices_vendor ON invoices(vendor);
        CREATE INDEX IF NOT EXISTS idx_purchase_orders_vendor ON purchase_orders(vendor);
    """)
    conn.commit()
    conn.close()
