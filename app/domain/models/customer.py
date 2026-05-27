from sqlalchemy import BigInteger, Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.infrastructure.db import Base

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    shopify_customer_id = Column(BigInteger, unique=True, nullable=False)
    email = Column(String(255), nullable=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
