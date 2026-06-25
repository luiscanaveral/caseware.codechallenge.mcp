# MCPHOWTO: Caseware Procurement Document MCP Server

## Prerequisites

- Python 3.12+
- [Ollama](https://ollama.ai) running locally with `llama3.2` model pulled:
  ```bash
  ollama pull llama3.2
  ```

## Install

```bash
# Install from project root
pip install -e /ABSOLUTE/PATH/TO/caseware.mcp-codechallege

# This makes the `caseware-mcp` command available globally
```

## Run the Server

After installation, the `caseware-mcp` command is available globally:

```bash
caseware-mcp
```

This will:
1. Ingest all documents from `data/` (PDFs + JPGs with OCR)
2. Extract structured fields (invoice numbers, PO numbers, vendors, amounts)
3. Generate embeddings and index chunks
4. Build cross-document references (invoice ↔ PO ↔ shipment)
5. Start the MCP server on stdio

To skip the pipeline (if already indexed):
```bash
caseware-mcp --skip-pipeline
```

## Claude Desktop Integration

1. Open or create `~/Library/Application Support/Claude/claude_desktop_config.json`

2. Add the MCP server configuration (using the `caseware-mcp` console script — no `cwd` needed):

```json
{
  "mcpServers": {
    "caseware-documents": {
      "command": "caseware-mcp",
      "args": ["--skip-pipeline"]
    }
  }
}
```

> **Note:** `--skip-pipeline` is recommended here because the pipeline runs once on first install. If you omit it, the server will re-index all documents on every connection, which takes ~10–15 seconds.

If you haven't run the pipeline yet, run `caseware-mcp --pipeline-only` from the terminal first.

3. Restart Claude Desktop

4. You should see a hammer icon indicating the MCP tools are available.

## Available Tools

| Tool | Description |
|------|-------------|
| `search_documents` | Search by keyword, optionally filter by document type |
| `get_related_documents` | Find all documents related to a given document ID |
| `find_order_evidence` | Trace an order number across invoices, POs, and shipments |
| `answer_question` | Ask natural language questions with grounded answers |

## Example Questions to Ask

- "Which invoices are missing a purchase order?"
- "Find all documents related to order 10687"
- "Summarize the contract terms"
- "Show me all invoices"
- "What is the total amount for order 10603?"
- "Find all shipments for order 10687"
