"""Print row counts for all document tables in SQLite."""

from ..db.schema import get_connection

TABLES = [
    "documents",
    "invoices",
    "purchase_orders",
    "shipping_orders",
    "inventory_reports",
    "contracts",
    "document_chunks",
]


def main():
    conn = get_connection()
    for table in TABLES:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count}")
    conn.close()


if __name__ == "__main__":
    main()
