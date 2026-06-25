import logging
import os
from pathlib import Path

_ENV_LOADED = False


def _load_dotenv():
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip()
            if not os.environ.get(key):
                os.environ[key] = val
    _ENV_LOADED = True


def _get(key: str, default: str) -> str:
    _load_dotenv()
    return os.environ.get(key, default)


def _get_int(key: str, default: int) -> int:
    try:
        return int(_get(key, str(default)))
    except (ValueError, TypeError):
        return default


def _get_float(key: str, default: float) -> float:
    try:
        return float(_get(key, str(default)))
    except (ValueError, TypeError):
        return default


def _get_set(key: str, default: str) -> set[str]:
    raw = _get(key, default)
    return {x.strip() for x in raw.split(",") if x.strip()}


# ── Paths ──────────────────────────────────────────────────────────
DATA_DIR = _get("DATA_DIR", "data")
DB_PATH = _get("DB_PATH", "storage/sqlite.db")
CHROMA_PATH = _get("CHROMA_PATH", "storage/chroma")

# ── Models ─────────────────────────────────────────────────────────
EMBEDDING_MODEL = _get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
LLM_MODEL = _get("LLM_MODEL", "llama3.2")

# ── Chunking ───────────────────────────────────────────────────────
CHUNK_SIZE = _get_int("CHUNK_SIZE", 512)
CHUNK_OVERLAP = _get_int("CHUNK_OVERLAP", 64)
TEXT_TRUNCATE = _get_int("TEXT_TRUNCATE", 500)

# ── Retrieval ──────────────────────────────────────────────────────
SEMANTIC_TOP_K = _get_int("SEMANTIC_TOP_K", 10)
DEFAULT_SEARCH_LIMIT = _get_int("DEFAULT_SEARCH_LIMIT", 20)
COSINE_THRESHOLD = _get_float("COSINE_THRESHOLD", 0.1)
COSINE_WEIGHT = _get_float("COSINE_WEIGHT", 0.7)

# ── LLM ────────────────────────────────────────────────────────────
LLM_TEMPERATURE = _get_float("LLM_TEMPERATURE", 0.1)
LLM_NUM_PREDICT = _get_int("LLM_NUM_PREDICT", 512)

# ── Matching confidence ────────────────────────────────────────────
CONFIDENCE_EXACT = _get_float("CONFIDENCE_EXACT", 1.0)
CONFIDENCE_VENDOR = _get_float("CONFIDENCE_VENDOR", 0.8)
CONFIDENCE_VENDOR_AMOUNT = _get_float("CONFIDENCE_VENDOR_AMOUNT", 0.95)
AMOUNT_DIFF_RATIO = _get_float("AMOUNT_DIFF_RATIO", 0.1)

# ── Server ─────────────────────────────────────────────────────────
SERVER_NAME = _get("SERVER_NAME", "caseware-documents-mcp")
SERVER_VERSION = _get("SERVER_VERSION", "0.1.0")
LOG_LEVEL = _get("LOG_LEVEL", "INFO")
LOG_FORMAT = _get("LOG_FORMAT", "%(levelname)s: %(message)s")

# ── File extensions ────────────────────────────────────────────────
OCR_EXTENSIONS = _get_set("OCR_EXTENSIONS", ".jpg,.jpeg,.png,.tiff,.tif")
ALLOWED_EXTENSIONS = _get_set("ALLOWED_EXTENSIONS", ".pdf,.jpg,.jpeg,.png,.tiff,.tif")

# ── Contract extraction ────────────────────────────────────────────
CONTRACT_REGEX_WINDOW = _get_int("CONTRACT_REGEX_WINDOW", 5000)
CONTRACT_TERMS_MAX_CHARS = _get_int("CONTRACT_TERMS_MAX_CHARS", 20000)

# ── Document type map ──────────────────────────────────────────────
DOCUMENT_TYPE_MAP: dict[str, str] = {
    "invoices": "invoice",
    "purchase_orders": "purchase_order",
    "shipping_orders": "shipping_order",
    "inventory_reports": "inventory_report",
    "contracts": "contract",
}

DOCUMENT_TYPES: set[str] = set(DOCUMENT_TYPE_MAP.values())

TABLE_MAP: dict[str, str] = {
    "invoice": "invoices",
    "purchase_order": "purchase_orders",
    "shipping_order": "shipping_orders",
    "inventory_report": "inventory_reports",
    "contract": "contracts",
}

TABLE_COLUMNS: dict[str, list[str]] = {
    "invoices": ["document_id", "invoice_number", "po_number", "vendor", "amount", "date"],
    "purchase_orders": ["document_id", "po_number", "vendor", "amount", "date"],
    "shipping_orders": ["document_id", "shipment_number", "po_number", "date"],
    "inventory_reports": ["document_id", "period", "item_counts"],
    "contracts": ["document_id", "vendor", "contract_terms"],
}

SEARCHABLE_COLUMNS: dict[str, list[str]] = {
    "invoices": ["id", "po_number", "vendor", "invoice_number"],
    "purchase_orders": ["id", "po_number", "vendor"],
    "shipping_orders": ["id", "po_number", "shipment_number"],
    "contracts": ["id", "vendor"],
}


def configure_logging():
    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(level=level, format=LOG_FORMAT)
