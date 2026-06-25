# Caseware Document MCP Server

MCP server over a procurement and inventory knowledge base. Ingests invoices, purchase orders, shipping orders, inventory reports, and contracts, then exposes structured (SQL) and semantic (vector) retrieval via MCP tools for AI agents.

## Architecture

```
Documents              Pipeline                Storage              MCP Server
─────────              ────────                ───────              ──────────
invoices/        ──▶  ingest.py  ──▶  SQLite                search_documents
purchase_orders/ ──▶  extract.py ──▶         ──▶  stdio ──▶ get_related_documents
shipping_orders/ ──▶  embed.py                       server    find_order_evidence
inventory_reports──▶  index.py                                answer_question
contracts/       ──▶
```

**Hybrid retrieval**: structured questions (e.g. "which invoices are missing a PO?") hit SQL; semantic questions (e.g. "summarize contract terms") hit vector search via sentence-transformers, then Ollama (`llama3.2`) generates grounded answers with citations.

## Prerequisites

- **Python 3.12+**
- **Tesseract OCR** (for image-based invoice extraction)
  - macOS: `brew install tesseract`
  - Ubuntu: `apt install tesseract-ocr`
- **Ollama** with `llama3.2` (for LLM-based answer generation)
  ```bash
  brew install ollama     # macOS
  # or: curl -fsSL https://ollama.com/install.sh | sh
  ollama pull llama3.2
  ```

## Quick Start

```bash
# Clone and enter the project
cd caseware.mcp-codechallege

# Install with pip (no venv required)
pip install -e .

# Run full pipeline + start MCP server
caseware-mcp

# Or with task (recommended)
task install
task
```

## Dependencies

| Package | Purpose |
|---------|---------|
| `pymupdf` | PDF text extraction |
| `pytesseract` + `pillow` | OCR for scanned/image documents |
| `sentence-transformers` | Local embeddings (`all-MiniLM-L6-v2`) |
| `pydantic` | Data models and validation |
| `mcp` | MCP protocol server (stdio transport) |
| `ollama` | LLM inference for grounded answer generation |

All listed in `pyproject.toml` — no requirements.txt needed.

## Data

Documents live in `data/` organized by type:

```
data/
├── invoices/             8 PDFs + 5 JPGs
├── purchase_orders/       8 PDFs
├── shipping_orders/      16 PDFs
├── inventory_reports/     7 PDFs
└── contracts/             1 PDF (71 pages)
```

The pipeline auto-detects format: PDFs via PyMuPDF, images via Tesseract OCR.

## Usage

### Taskfile (recommended)

| Command | Description |
|---------|-------------|
| `task` | Full pipeline + start MCP server |
| `task pipeline` | Index documents only |
| `task server` | Start server (skip indexing) |
| `task install` | Install into `.venv` |
| `task test` | Smoke test — list available tools |
| `task db` | Show document counts |
| `task clean` | Remove storage + `.venv` |

### Direct

```bash
# Full run
caseware-mcp

# Pipeline only (no server)
caseware-mcp --pipeline-only

# Skip indexing (if already indexed)
caseware-mcp --skip-pipeline
```

### MCP Tools

| Tool | Input | What it does |
|------|-------|-------------|
| `search_documents` | `{query, document_type?}` | Hybrid SQL + vector search |
| `get_related_documents` | `{document_id}` | Cross-document lookup via invoice↔PO↔shipment refs |
| `find_order_evidence` | `{order_number}` | Trace an order across all document types with citations |
| `answer_question` | `{question}` | Routes to SQL or vector search → Ollama answer with sources |

### Example questions

- "Which invoices are missing a purchase order?"
- "Find all documents related to order 10687"
- "Summarize the contract terms"
- "Show me all invoices for Roland Mendel"

### Claude Desktop Integration

See `MCPHOWTO.md` for detailed setup instructions.

## Project Structure

```
src/caseware_documents_mcp/
├── models.py            # Pydantic models
├── main.py              # Entry point
├── pipeline/
│   ├── ingest.py        # PDF + OCR extraction
│   ├── extract.py       # Structured field parsing
│   ├── embed.py         # Chunking + embeddings
│   └── index.py         # Cross-document reference builder
├── db/
│   ├── schema.py        # SQLite DDL
│   └── queries.py       # SQL queries
├── retrieval/
│   ├── classifier.py    # Question routing
│   ├── structured.py    # SQL-based retrieval
│   └── semantic.py      # Vector search
└── server/
    └── mcp_server.py    # MCP stdio server
```

## Design Decisions

- **SQLite** as the single store — procurement data is fundamentally relational; vector search alone misses invoice↔PO↔shipment links. Embeddings are stored alongside structured data in the same SQLite database.
- **Regex extraction** over LLM-based parsing — the documents follow predictable templates (Northwind-style); regex is faster, cheaper, and more reliable
- **sentence-transformers** for local embeddings — no API calls needed; `all-MiniLM-L6-v2` is 80MB and runs on CPU
- **Ollama** for answer generation — keeps everything local; `llama3.2` provides good results for summarization and reasoning
- **Keyword classifier** over LLM router — pattern matching on the question is sufficient to distinguish "which invoices are missing a PO?" (SQL) from "summarize the contract" (vector)
