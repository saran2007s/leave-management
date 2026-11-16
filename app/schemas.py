from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role: str
    manager_id: int | None

    # Allow Pydantic v2 to read attributes directly from SQLAlchemy ORM objects
    model_config = ConfigDict(from_attributes=True)