# Evolution of the Document MCP Server

This document captures key architectural decisions and how testing drove code
changes throughout development.

## Phase 1: Initial Architecture (Convention Over Code)

### Chosen approach: data/ dir → regex extraction → SQLite → ChromaDB

We opted for regex-based extraction over LLM parsing because:
- 270 documents × LLM calls = expensive and slow
- Northwind templates are consistent — regex is reliable enough
- LLM parsing adds latency for no quality gain on templated data

The doc-type classifier in `retrieval/classifier.py` routes questions to either
`answer_structured` (direct SQL) or `semantic_search` (vector) + LLM. This
hybrid approach means invoices/POs can be answered from structured columns
costing ~0 LLM calls while contract-intent questions route to vector search +
Ollama.

## Phase 2: Testing Reveals Problems

### Bug: MCP server can't load as a module

Running `mcp dev` failed because `mcp dev` loads the server file via
`importlib`, not as a package module. Relative imports (`from .. import
settings`) only work inside packages. The fix was to switch to absolute imports
in `server/mcp_server.py`.

### Bug: `mcp dev` only supports FastMCP

The low-level `mcp.Server` class works with custom stdio transports but `mcp
dev` only wraps `FastMCP`. We created `server/fast_mcp_server.py` as a thin
wrapper, keeping `mcp_server.py` for production use.

### Discovery: Pipeline is not idempotent

Re-running the pipeline created duplicate rows: `INSERT INTO documents` has no
`UNIQUE` constraint, and `ingest.py` always inserts. After 6 runs the DB had
270 "documents" instead of 45 — inflating chunk counts and making evaluation
misleading.

**Fix (schema.py + ingest.py):**
- Added `UNIQUE(filename)` to the `documents` table
- Switched to `INSERT OR IGNORE` + `SELECT` for existing ID

### Discovery: Duplicate chunks flood search results

`semantic_search` returned the top K chunks by cosine score, but a single
71-page contract produced dozens of near-identical chunks. All 5 result slots
were filled by the same document, drowning out relevant POs and shipping
orders.

**Fix (semantic.py):**
- After scoring, deduplicate by `document_id`, keeping only the highest-scoring
  chunk per document
- Added token-overlap reranking (cosine × 0.7 + overlap × 0.3) as a lightweight
  BM25 surrogate — no extra dependencies

### Discovery: Structured search is broken for entity queries

`answer_structured` called `search_structured(question)` which does a bare
`LIKE '%full question%'` — impossible to match vendor names or order numbers
embedded in questions.

**Fix (structured.py):**
- Added `_extract_entities()` to parse numbers and capitalized multi-word names
  from the question
- Added `_search_tables_for()` to search all structured tables for extracted
  values
- Two bugs found: `table_key` (doc-type) vs `table_name` mismatch when
  indexing `SEARCHABLE_COLUMNS`, and missing `\s*` between preposition
  alternatives (`for|from|by|...`) and the name capture group

## Phase 3: Measured Impact

Metrics before and after the fixes (45 documents, 133 chunks):

| Metric | Before | After |
|---|---|---|
| Semantic Recall@5 (type) | 0.78 | 0.94 |
| Semantic MRR (type) | 0.778 | 0.875 |
| Semantic Recall@5 (file) | 0.44 | 0.78 |
| Semantic MRR (file) | 0.444 | 0.667 |
| Structured Accuracy | 0.33 | 1.00 |

The one remaining semantic miss ("Shipped date for order 10603") is a genuine
embedding quality issue: PO text with "Order Date" fields semantically outranks
shipping order text. A future improvement would be hybrid BM25+vector search
via `rank_bm25` for more aggressive exact-token boosting.

### Bug: Tesseract OCR crashes on non-UTF-8 stderr output

Running the pipeline in environments where Tesseract emits non-UTF-8 bytes to
stderr caused a `UnicodeDecodeError` inside pytesseract's `get_errors()` — it
blindly calls `error_string.decode("utf-8")` on the raw stderr bytes.

**Fix (ingest.py):**
- Monkey-patch `pytesseract.pytesseract.get_errors` at module load time to
  catch `UnicodeDecodeError` and retry with `errors='replace'`
- This handles any encoding issue in Tesseract's stderr regardless of locale
- No changes needed to individual OCR call sites

## Remaining Trade-offs

1. **Regex extraction is brittle** — works for Northwind templates; real-world
   invoices would need LLM extraction or per-vendor templates
2. **`all-MiniLM-L6-v2` is small but loses nuance** — domain-fine-tuned models
   (e.g. `intfloat/e5-small-v2` fine-tuned on procurement) would improve
   cross-document semantic matching
3. **Full-scan cosine search doesn't scale** — O(N) on every query with all
   chunks in memory. For a production 10M-chunk corpus, use an ANN index
   (HNSW in ChromaDB, pgvector, etc.)
4. **`search_structured` still uses bare LIKE** — not an issue at this scale but
   would need FTS5 at 10K+ rows
5. **Classify → route is hardcoded** — the classifier patterns work for this
   dataset but would need ML-based intent detection for general procurement
   queries
