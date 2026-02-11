from sqlalchemy import Column, String, Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from db import Base  # your Base

class GSCVerification(Base):
    __tablename__ = "gsc_verifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    site_url = Column(Text, nullable=False, index=True)
    
    google_account_id = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    
    permission_level = Column(String(50), nullable=True)  # siteOwner, siteFullUser
    
    verified = Column(Boolean, default=False)

    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
