# System Diagrams

## 1. Entity-Relationship Diagram

```mermaid
erDiagram
    documents {
        int id PK
        text filename UK
        text document_type
        text raw_text
        int ocr_used
        int page_count
        text created_at
    }

    invoices {
        int id PK
        int document_id FK
        text invoice_number
        text po_number
        text vendor
        real amount
        text date
    }

    purchase_orders {
        int id PK
        int document_id FK
        text po_number
        text vendor
        real amount
        text date
    }

    shipping_orders {
        int id PK
        int document_id FK
        text shipment_number
        text po_number
        text date
    }

    inventory_reports {
        int id PK
        int document_id FK
        text period
        text item_counts
    }

    contracts {
        int id PK
        int document_id FK
        text vendor
        text contract_terms
    }

    document_chunks {
        int id PK
        int document_id FK
        int chunk_index
        text text
        int page
    }

    invoice_po_match {
        int id PK
        int invoice_id FK
        int po_id FK
        real confidence
        text match_method
    }

    shipment_po_match {
        int id PK
        int shipment_id FK
        int po_id FK
        real confidence
        text match_method
    }

    documents ||--o{ invoices : "1-to-many"
    documents ||--o{ purchase_orders : "1-to-many"
    documents ||--o{ shipping_orders : "1-to-many"
    documents ||--o{ inventory_reports : "1-to-many"
    documents ||--o{ contracts : "1-to-many"
    documents ||--o{ document_chunks : "1-to-many"
    invoices ||--o{ invoice_po_match : "matched by"
    purchase_orders ||--o{ invoice_po_match : "matched by"
    purchase_orders ||--o{ shipment_po_match : "matched by"
    shipping_orders ||--o{ shipment_po_match : "matched by"
```

---

## 2. Pipeline Flow (Ingestion → Extraction → Embedding → Indexing)

```mermaid
sequenceDiagram
    participant FS as data/ dir
    participant Ingest as ingest.py
    participant DB as SQLite
    participant Extract as extract.py
    participant Embed as embed.py
    participant Index as index.py

    Ingest->>FS: Walk subdirs (invoices/, purchase_orders/, ...)
    Ingest->>Ingest: Classify by subdir name
    
    loop Each file
        Ingest->>Ingest: OCR (jpg/png) or PyMuPDF (pdf)
        Ingest->>DB: INSERT OR IGNORE INTO documents
        Ingest->>DB: SELECT id (existing or new)
    end

    Ingest-->>Extract: 45 documents ingested

    Extract->>DB: SELECT all documents
    
    loop Each document
        Extract->>Extract: Dispatch to parser by doc_type
        Extract->>Extract: Regex extraction (invoice#, vendor, PO#, amounts...)
        Extract->>DB: INSERT OR IGNORE INTO type-specific table
    end

    Extract-->>Embed: Structured data extracted

    Embed->>DB: SELECT documents (ordered by id)
    
    loop Each document
        Embed->>Embed: chunk_text() — split by paragraphs, ~512 chars
        Embed->>Embed: SentenceTransformer encode(chunks)
        Embed->>DB: INSERT INTO document_chunks
    end

    Embed-->>Index: 133 chunks in DB

    Index->>DB: Match invoices → POs by po_number
    Index->>DB: Match shipments → POs by po_number
    Index->>DB: Fallback match by vendor+amount similarity
    Index->>DB: INSERT INTO invoice_po_match / shipment_po_match

    Index-->>: Pipeline complete (5 cross-refs)
```

---

## 3. MCP Tool Dispatch

```mermaid
sequenceDiagram
    participant Client as MCP Client (Claude/mcp dev)
    participant Server as mcp_server.py (FastMCP wrapper)
    participant Router as call_tool()
    participant Handler as Handler function
    participant DB as SQLite / SentenceTransformer

    Client->>Server: JSON-RPC: tools/list
    Server-->>Client: 4 tools (search_documents, get_related_documents, find_order_evidence, answer_question)

    Client->>Server: JSON-RPC: tools/call { name, arguments }
    Server->>Router: dispatch(name, arguments)

    alt search_documents
        Router->>Handler: handle_search()
        Handler->>Handler: search_structured(query) — LIKE across columns
        Handler->>Handler: semantic_search(query) — vector cosine + token overlap
        Handler-->>Client: Combined structured + semantic results

    else get_related_documents
        Router->>Handler: handle_get_related()
        Handler->>DB: get_document_by_id()
        Handler->>DB: Look up PO/invoice/shipment by type
        Handler->>DB: get_related_to_po()
        Handler-->>Client: Document type + cross-refs

    else find_order_evidence
        Router->>Handler: handle_find_order()
        Handler->>DB: Query purchase_orders, invoices, shipping_orders
        Handler-->>Client: Evidence chain (PO → invoices → shipments)

    else answer_question
        Router->>Handler: handle_answer()
        Handler->>Handler: classify_question() → "structured" | "semantic"
        
        alt structured
            Handler->>Handler: answer_structured()
            Handler->>Handler: Extract entities (numbers, vendor names)
            Handler->>DB: _search_tables_for(entity) or get_related_to_po()
            Handler-->>Client: Direct SQL answer + sources
        
        else semantic
            Handler->>Handler: semantic_search(question)
            Handler->>Handler: _generate_llm_answer(context + question)
            Note over Handler: Ollama llama3.2, fallback to excerpts
            Handler-->>Client: LLM answer + citations
        end
    end
```

---

## 4. Semantic Search Internals

```mermaid
sequenceDiagram
    participant Caller as handle_search / handle_answer
    participant SS as semantic_search()
    participant Model as SentenceTransformer
    participant DB as document_chunks table
    participant Ranker as dedup + rerank

    Caller->>SS: semantic_search(query, doc_type, top_k=5)
    
    SS->>Model: encode(query)
    Model-->>SS: query_embedding (384-d vector)

    SS->>DB: SELECT id, document_id, text, page FROM document_chunks
    DB-->>SS: 133 rows (all chunks)

    SS->>Model: encode(chunk_texts) — batch
    Model-->>SS: chunk_embeddings [133 × 384-d]

    SS->>SS: cosine_similarity(query_emb × chunk_embs)
    SS->>SS: token_overlap(query, chunk_text) — Jaccard-like
    
    SS->>Ranker: combined = 0.7 × cosine + 0.3 × overlap

    Ranker->>Ranker: Sort all by combined score ↓
    Ranker->>Ranker: Skip score < COSINE_THRESHOLD
    Ranker->>Ranker: Dedup — keep 1 chunk per document_id
    Ranker->>Ranker: Filter by doc_type if specified
    
    Note over Ranker: Earlier: 5 identical contract chunks<br/>Now: 1 contract + 4 diverse docs

    Ranker-->>Caller: [{ chunk_id, text, page, score, file, document_type }]

    alt Answer question (semantic route)
        Caller->>Caller: Build context string from top-5 results
        Caller->>Caller: _generate_llm_answer(context, question)
        Note over Caller: Ollama call or fallback to excerpt list
    else Search documents
        Caller->>Caller: Format results for TextContent
    end
```

---

## 5. Classifier Routing Logic

```mermaid
flowchart TD
    Q["question: str"] --> C["classify_question()"]
    
    C --> P1{"matches STRUCTURED_PATTERNS?"}
    P1 -- Yes --> ROUTE_STRUCTURED["route = 'structured'"]
    P1 -- No --> P2
    
    P2{"matches SEMANTIC_PATTERNS?"}
    P2 -- Yes --> ROUTE_SEMANTIC["route = 'semantic'"]
    P2 -- No --> P3
    
    P3{"has WH-word AND has number?"}
    P3 -- Yes --> ROUTE_STRUCTURED
    P3 -- No --> ROUTE_SEMANTIC

    ROUTE_STRUCTURED --> AS["answer_structured()"]
    ROUTE_SEMANTIC --> AQ["semantic_search() + LLM"]

    AS --> AS1{"missing + purchase_order?"}
    AS1 -- Yes --> AS2["get_invoices_missing_po()"]
    AS1 -- No --> AS3{"order + number?"}
    
    AS3 -- Yes --> AS4["get_related_to_po(po_num)"]
    AS4 -- Found --> AS5["Format order chain"]
    AS4 -- Not found --> AS6["_search_tables_for(po_num)"]
    
    AS3 -- No --> AS7["_extract_entities(question)"]
    AS7 --> AS8["_search_tables_for(entity) loop"]
    AS8 -- Found --> AS9["Format entity results"]
    AS8 -- Not found --> AS10["search_structured(question) — bare LIKE fallback"]
    AS10 -- Found --> AS9
    AS10 -- Not found --> AS11["No structured results found."]
```

---

## 6. File Layout and Module Dependencies

```mermaid
graph TD
    subgraph "Entry Point"
        MAIN["main.py"]
    end

    subgraph "Pipeline"
        INGEST["pipeline/ingest.py"]
        EXTRACT["pipeline/extract.py"]
        EMBED["pipeline/embed.py"]
        INDEX["pipeline/index.py"]
    end

    subgraph "Retrieval"
        SEMANTIC["retrieval/semantic.py"]
        STRUCTURED["retrieval/structured.py"]
        CLASSIFIER["retrieval/classifier.py"]
    end

    subgraph "Database"
        SCHEMA["db/schema.py"]
        QUERIES["db/queries.py"]
    end

    subgraph "Server"
        MCP["server/mcp_server.py"]
        FAST_MCP["server/fast_mcp_server.py"]
    end

    subgraph "Support"
        SETTINGS["settings.py"]
        SCRIPTS["scripts/ (evaluate.py, test_db.py)"]
    end

    MAIN --> INGEST
    MAIN --> EXTRACT
    MAIN --> EMBED
    MAIN --> INDEX

    MCP --> SEMANTIC
    MCP --> STRUCTURED
    MCP --> CLASSIFIER
    MCP --> QUERIES
    MCP --> SCHEMA

    FAST_MCP --> MCP

    INGEST --> SCHEMA
    EXTRACT --> SCHEMA
    EMBED --> SCHEMA
    INDEX --> SCHEMA
    QUERIES --> SCHEMA

    SEMANTIC --> QUERIES
    STRUCTURED --> QUERIES
    STRUCTURED --> SEMANTIC

    INGEST --> SETTINGS
    EXTRACT --> SETTINGS
    EMBED --> SETTINGS
    INDEX --> SETTINGS
    SEMANTIC --> SETTINGS
    STRUCTURED --> SETTINGS
    CLASSIFIER --> SETTINGS
    MCP --> SETTINGS
    SCHEMA --> SETTINGS
    QUERIES --> SETTINGS
    SCRIPTS --> SETTINGS
```
