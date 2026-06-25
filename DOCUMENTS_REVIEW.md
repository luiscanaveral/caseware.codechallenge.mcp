# Document Review

## Overview

45 documents across 5 types, totaling ~133 chunks (after idempotent pipeline).

| Type | Count | File Formats | Size Range | Extraction Method |
|---|---|---|---|---|
| Invoice | 13 | `.pdf` (8), `.jpg` (5) | 1–324 KB | PyMuPDF (PDF) / Tesseract OCR (JPG) |
| Shipping Order | 16 | `.pdf` (16) | ~2 KB | PyMuPDF |
| Purchase Order | 8 | `.pdf` (8) | ~8 KB | PyMuPDF |
| Inventory Report | 7 | `.pdf` (7) | ~1 KB | PyMuPDF |
| Contract | 1 | `.pdf` (1) | ~908 KB | PyMuPDF |

---

## Invoice (13 files)

### Two sub-families

| Family | Files | Format | Source |
|---|---|---|---|
| **Northwind** | `invoice_10248.pdf` through `invoice_10839.pdf` (8) | PDF, templated | Generated from Northwind database |
| **Batch** | `batch1-1486.jpg`, `batch1-1488.jpg`, `batch2-0998.jpg`, `batch2-0999.jpg`, `batch2-1000.jpg` (5) | Scanned JPG, OCR needed | Varied real-world-ish invoices |

### Northwind sample text
```
Invoice
Order ID: 10248
Customer ID: VINET
Order Date: 2016-07-04
Customer Details:
Contact Name:
Paul Henriot
...
Product Details:
Product ID  Product Name        Quantity  Unit Price
11          Queso Cabrales      12        14.0
...
TotalPrice  440.0
```

### Batch sample text (OCR'd from JPG)
```
Invoice no: 23285582
Date of issue:
Seller:
Harris-Green
97868 Adam Parkways
...
ITEMS
No.  Description                             Qty  UM
    16 Inches Marble Coffee Table             4   each
    6'x3' Black Marble Large Dining Table     5   each
...
Total                                      $11,850.00
```

### Extraction regex (`parse_invoice`)

| Field | Regex | Example |
|---|---|---|
| `po_number` | `Order ID:\s*(\d+)` | `"10248"` |
| `invoice_number` | `Invoice no[:\s]+(\S+)` or filename fallback `INV-\d+` | `"23285582"`, `"INV-10248"` |
| `date` | `Order Date:\s*([\d-]+)` or `Date of issue:\s*([\d/]+)` | `"2016-07-04"`, `"2015-12-19"` |
| `amount` | `Total(?:Price\|Due)?[:\s]*\$?([\d,.]+)` | `440.0`, `11850.0` |
| `vendor` | `Contact Name:\s*\n(.+)` then `Customer Name:\s*(.+)` then `Seller:\s*\n(.+)` | `"Paul Henriot"`, `"Harris-Green"` |

### Known limitation
- Batch invoices set `po_number` from `Order ID:` which only exists in Northwind invoices — batch invoices have no cross-reference field. They correctly end up in `get_invoices_missing_po()` (3 of the 13 invoices lack a PO reference).

---

## Purchase Order (8 files)

### Files
`purchase_orders_10248.pdf` through `purchase_orders_10711.pdf` — one per Northwind order.

### Sample text
```
Purchase Orders
Order ID        Order Date     Customer Name
10248           2016-07-04     Paul Henriot
Products
Product ID:  Product:              Quantity:  Unit Price:
11           Queso Cabrales        12         14
42           Singaporean Hokkien   10         9.8
72           Mozzarella di Giovanni 5         34.8
```

### Extraction regex (`parse_purchase_order`)

| Field | Regex | Example |
|---|---|---|
| `po_number` | `Order ID[\s\S]*?(\d{4,})` | `"10248"` |
| `date` | `Order Date[\s\S]*?([\d-]+)` | `"2016-07-04"` |
| `vendor` | `Customer Name[\s\S]*?(.+?)(?:\nProducts|\Z)` | `"Paul Henriot"` |
| `amount` | Computed: `SUM(Quantity × Unit Price)` | `440.0` |

### Notes
- Tabular format (no JSON/CSV). The regexes use `[\s\S]*?` to cross newlines between headers and values.
- Amount is computed client-side by multiplying Qty × Price across all line items, since no total appears in the source.
- All 8 POs have a valid `po_number` — none are rejected by the parser guard.

---

## Shipping Order (16 files)

### Files
`order_10248.pdf` through `order_10993.pdf` — 16 shipping records for Northwind orders.

### Sample text
```
Order ID: 10248
Shipping Details:
Ship Name: Vins et alcools Chevalier
Ship Address: 59 rue de l-Abbaye
...
Shipper Details:
Shipper ID: 3
Shipper Name: Federal Shipping
Order Details:
Order Date: 2016-07-04
Shipped Date: 2016-07-16
Products:
  Product: Queso Cabrales    Quantity: 12
```

### Extraction regex (`parse_shipping_order`)

| Field | Regex | Example |
|---|---|---|
| `shipment_number` | `Order ID:\s*(\d+)` | `"10248"` |
| `po_number` | Same `Order ID:\s*(\d+)` (aliased) | `"10248"` |
| `date` | `Shipped Date:\s*([\d-]+)` | `"2016-07-16"` |

### Notes
- The `po_number` field in shipping_orders stores the `Order ID` from the document (not an external PO number). This is used for cross-referencing: `shipment_po_match` joins `shipping_orders.po_number → purchase_orders.po_number` to link each shipment to its purchase order.
- The shipment's *actual* purchase order number is the same as the Order ID in this dataset (the Northwind model uses Order ID as the primary key across all three document types).

---

## Inventory Report (7 files)

### Files
`StockReport_YYYY-MM_N.pdf` — one per month/category combination.

### Sample text
```
Stock Report for 2016-07
 Category : Seafood   id category : 8
Product                Units Sold   Units in Stock   Unit Price
Nord-Ost Matjeshering  60           10               25.89
Inlagd Sill            25           112              19
Boston Crab Meat       50           123              18.4
```

### Extraction regex (`parse_inventory_report`)

| Field | Regex | Example |
|---|---|---|
| `period` | `Stock Report for\s+([\d-]+)` | `"2016-07"` |
| `item_counts` | `^(\w[\w\s\-']+?)\s+(\d+)\s+(\d+)` (multiline) | `{'Boston Crab Meat': 123, ...}` |

### Notes
- `item_counts` is stored as a Python `dict` string representation (e.g., `"{'Boston Crab Meat': 123}"`). This is useful for semantic search (full-text is in `documents.raw_text`) but the structured column is not easily queried with `LIKE`.
- Each report covers one product category for one month. To find a product, you need to know which category it belongs to (encoded in the filename as `_N` suffix, e.g. `_8` = Seafood).
- The regex uses `re.MULTILINE` so `^` matches line starts. The pattern is fragile if product names contain numbers (none do in this dataset).

---

## Contract (1 file)

### File
`totalenergies_master-contract-for-supply-of-goods-and-or-services-otgts-20231231_2024_en_pdf.pdf`

### Size
163,481 chars (71 pages), ~908 KB PDF.

### Sample text
```
Page 1 sur 71
Master Contract for Supply of Goods and/or Services_ 20231231
TOTALENERGIES - All rights reserved
...
"TotalEnergies SE"); and
(2)
[TOTALENERGIES SE - full legal name]
...
Supplier Signatory: ________________________________
Name: [Supplier Representative]
Title: [Supplier Representative Title]
```

### Extraction regex (`parse_contract`)

| Field | Regex | Example |
|---|---|---|
| `vendor` | `"([^"]+)"\);\s*\n\s*and\s*\n\s*\(2\)\s*\n\s*\[([^\]]+)\]` or `Supplier Signatory[\s\S]*?\[([^\]]+)\]` | `"TOTALENERGIES SE"` |
| `contract_terms` | First 20,000 chars of raw text | Full legal text (truncated) |

### Notes
- This is a real TotalEnergies master contract template (71 pages). The extraction regex targets the specific legal formatting where parties are listed as `(1) "Company Name"); and (2) [Other Party]` and the signature block `Supplier Signatory: [Name]`.
- `contract_terms` stores the first 20K chars of the document. The full 163K is preserved in `documents.raw_text` and available via chunk search.
- Only 1 contract exists in this dataset. It dominates semantic search results (71 pages × ~6 chunks/page after paragraph-splitting) unless dedup is applied.

---

## Cross-Document Linking

The `index.py` pipeline builds two link tables:

```
invoice_po_match:  invoices.po_number  ──→  purchase_orders.po_number
shipment_po_match: shipping_orders.po_number  ──→  purchase_orders.po_number
```

- **5 invoice–PO matches** — 3 batch invoices have no PO reference (listed by `get_invoices_missing_po()`)
- **5 shipment–PO matches** — all shipments link to their corresponding PO via Order ID

The matching uses `normalize_po_number()` (extracts digits only) for fuzzy joining, then falls back to vendor-name + amount similarity when PO numbers don't align.

---

## Text Extraction Summary

| Type | Method | Quality | OCR Used |
|---|---|---|---|
| Northwind invoices (PDF) | PyMuPDF `page.get_text()` | High — structured text | No |
| Batch invoices (JPG) | Tesseract OCR | Medium — depends on image quality | Yes |
| Purchase orders (PDF) | PyMuPDF | High | No |
| Shipping orders (PDF) | PyMuPDF | High | No |
| Inventory reports (PDF) | PyMuPDF | High | No |
| Contract (PDF) | PyMuPDF | High — but includes headers/footers per page | No |

### Chunking strategy
- Paragraph-based splitting at ~512 chars (configurable via `CHUNK_SIZE` in `.env`)
- Overlap: ~64 chars (configurable via `CHUNK_OVERLAP`)
- Contract generates the most chunks due to length (71 pages)
- Inventory reports generate the fewest (1 chunk each, ~250 chars)
