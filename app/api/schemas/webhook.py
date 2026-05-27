from datetime import datetime
from pydantic import BaseModel

class WebhookLogResponse(BaseModel):
    id: int
    topic: str
    payload: dict
    headers: dict
    received_at: datetime
    verified: bool
    attempt_count: int

    model_config = {"from_attributes": True}
