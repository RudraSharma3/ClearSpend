# backend/app/models.py
from pydantic import BaseModel
from enum import Enum
from typing import Optional

class TransactionType(str, Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"
    UNKNOWN = "UNKNOWN"

class Transaction(BaseModel):
    amount: Optional[float] = None
    merchant: str
    bank_name: str
    type: TransactionType
    category: str
    plain_language_summary: str