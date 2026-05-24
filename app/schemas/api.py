from pydantic import BaseModel, Field


class MeResponse(BaseModel):
    user_id: str = Field(description="Authenticated user id from the JWT `sub` claim.")
