from pydantic import BaseModel

from app.enums import HealthStatus


class HealthResponse(BaseModel):
    status: HealthStatus
