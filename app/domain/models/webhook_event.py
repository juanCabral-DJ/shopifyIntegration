from sqlalchemy import Column, Integer, String, DateTime, JSON, Boolean
from sqlalchemy.sql import func
from app.infrastructure.db import Base

class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id = Column(Integer, primary_key=True, index=True)
    topic = Column(String(128), nullable=False)
    payload = Column(JSON, nullable=False)
    headers = Column(JSON, nullable=True)
    received_at = Column(DateTime(timezone=True), server_default=func.now())
    verified = Column(Boolean, nullable=False, default=False)
    attempt_count = Column(Integer, nullable=False, default=1)
