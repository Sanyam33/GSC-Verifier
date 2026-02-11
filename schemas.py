from pydantic import BaseModel, AnyUrl
from typing import Optional
from uuid import UUID

class GSCVerificationCreate(BaseModel):
    site_url: AnyUrl

class GSCVerificationResult(BaseModel):
    site_url: str
    verified: bool
    permission_level: Optional[str] = None

class GSCVerificationDB(GSCVerificationResult):
    id: UUID
    email: Optional[str] = None

    class Config:
        from_attributes = True
