from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.infrastructure.db import Base

class PaymentMethod(Base):
    __tablename__ = "payment_methods"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(100), unique=True, nullable=False)
    display_name = Column(String(150), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
