from datetime import date as date_type
from pydantic import BaseModel, Field
from typing import Optional


class Document(BaseModel):
    id: int | None = None
    filename: str
    document_type: str
    raw_text: str
    ocr_used: bool = False
    page_count: int = 1


class Invoice(BaseModel):
    id: int | None = None
    document_id: int
    invoice_number: str | None = None
    po_number: str | None = None
    vendor: str | None = None
    amount: float | None = None
    doc_date: str | None = None
    filename: str = ""


class PurchaseOrder(BaseModel):
    id: int | None = None
    document_id: int
    po_number: str | None = None
    vendor: str | None = None
    amount: float | None = None
    doc_date: str | None = None
    filename: str = ""


class ShippingOrder(BaseModel):
    id: int | None = None
    document_id: int
    shipment_number: str | None = None
    po_number: str | None = None
    doc_date: str | None = None
    filename: str = ""


class InventoryReport(BaseModel):
    id: int | None = None
    document_id: int
    period: str | None = None
    item_counts: str | None = None
    filename: str = ""


class Contract(BaseModel):
    id: int | None = None
    document_id: int
    vendor: str | None = None
    contract_terms: str | None = None
    filename: str = ""


class DocumentChunk(BaseModel):
    id: int | None = None
    document_id: int
    chunk_index: int
    text: str
    page: int | None = None
    embedding: list[float] | None = None


class DocMatch(BaseModel):
    source_id: int
    target_id: int
    source_type: str
    target_type: str
    confidence: float
    match_method: str
