from pydantic import BaseModel
from typing import Optional

class VerificationResponse(BaseModel):
    status: str
    message: str
    confidence: float
    author_hash: Optional[str] = None
    content_hash: Optional[str] = None
    timestamp: Optional[float] = None
    version: Optional[int] = None
    media_category: Optional[str] = None
    strategy_used: Optional[str] = None

class ErrorResponse(BaseModel):
    detail: str
