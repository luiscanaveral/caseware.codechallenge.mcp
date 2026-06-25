import re

STRUCTURED_PATTERNS = [
    r"missing.*purchase order",
    r"invoices?.*without.*po",
    r"which.*invoice",
    r"list.*invoice",
    r"show.*invoice",
    r"purchase order.*\d+",
    r"order.*\d+",
    r"total.*amount",
    r"how many",
    r"count.*invoice",
    r"find.*vendor",
    r"supplier.*named?",
    r"highest.*amount",
    r"largest.*order",
    r"po.*number",
    r"invoice.*number",
]

SEMANTIC_PATTERNS = [
    r"summarize",
    r"summary",
    r"what.*about",
    r"explain",
    r"terms",
    r"conditions",
    r"tell me about",
    r"contract",
    r"agreement",
    r"describe",
    r"overview",
]


def classify_question(question: str) -> str:
    q = question.lower().strip()

    for pat in STRUCTURED_PATTERNS:
        if re.search(pat, q):
            return "structured"

    for pat in SEMANTIC_PATTERNS:
        if re.search(pat, q):
            return "semantic"

    has_wh = any(w in q for w in ["what", "which", "who", "where", "when", "how many", "how much"])
    has_number = bool(re.search(r"\d+", q))

    if has_wh and has_number:
        return "structured"

    return "semantic"
