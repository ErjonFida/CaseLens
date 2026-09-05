from pydantic import BaseModel, Field, EmailStr


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=72)
    confirm_password: str = Field(..., min_length=6, max_length=72)
    first_name: str = Field(..., min_length=2)
    last_name: str = Field(..., min_length=2)
    company: str = Field(..., min_length=2)
    phone_number: str = Field(..., pattern=r"^\+?[\d\s\-()]{7,20}$")


class LoginRequest(BaseModel):
    email: str
    password: str


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=5000)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]

