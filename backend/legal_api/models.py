from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, DateTime, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    email = Column(String(254), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(255), default="")
    last_name = Column(String(255), default="")
    company = Column(String(255), default="")
    phone_number = Column(String(50), default="")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    devices = relationship("KnownDevice", back_populates="user", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return self.email


class KnownDevice(Base):
    __tablename__ = "known_devices"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    device_hash = Column(String(255), nullable=False)
    last_login = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="devices")

    def __repr__(self):
        return f"{self.user_id} - {self.device_hash[:12]}"


class RateLimit(Base):
    """Fixed-window request counter, shared across workers."""

    __tablename__ = "rate_limits"

    key = Column(String(255), primary_key=True)
    window_start = Column(DateTime(timezone=True), nullable=False)
    count = Column(Integer, nullable=False, default=0)

    def __repr__(self):
        return f"{self.key}: {self.count}"


class UploadStatus(Base):
    __tablename__ = "upload_status"

    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    filename = Column(String(512), primary_key=True)
    status = Column(String(255), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"{self.filename}: {self.status}"


class Document(Base):
    __tablename__ = "documents"
    
    __table_args__ = (
        UniqueConstraint("user_id", "filename", name="uq_documents_user_filename"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    filename = Column(String(512), nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")

    def __repr__(self):
        return f"{self.filename} (user_id={self.user_id})"


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    document_id = Column(BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    page = Column(Integer, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    embedding = Column(Vector(768))
    embedding_model = Column(String(128), nullable=False, server_default="gemini-embedding-001", index=True)

    document = relationship("Document", back_populates="chunks")

    def __repr__(self):
        return f"Chunk {self.chunk_index} (page {self.page}) of doc_id={self.document_id}"
