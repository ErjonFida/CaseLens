from typing import Annotated

from pydantic import BaseModel, Field, EmailStr

# Filenames the user selected to ask about. Empty means all of their documents.
SelectedDocuments = Annotated[
    list[Annotated[str, Field(min_length=1, max_length=512)]],
    Field(default_factory=list, max_length=200),
]


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
    documents: SelectedDocuments


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    documents: SelectedDocuments

