from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, Index, Integer, BigInteger, String, Text, DateTime, ForeignKey, JSON, UniqueConstraint, false
)
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    email = Column(String(254), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(255), default="")
    last_name = Column(String(255), default="")
    company = Column(String(255), default="")
    phone_number = Column(String(50), default="")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    # The shared read-only demo account: no password sign-in, no uploads or
    # deletions, and a daily cap on questions. Created by seed_demo.py.
    is_demo = Column(Boolean, nullable=False, default=False, server_default=false())

    # passive_deletes: the foreign keys cascade in the database. Without it the
    # ORM loads every child row - chunks with their embeddings - to delete each
    # one itself.
    devices = relationship("KnownDevice", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    documents = relationship("Document", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)

    def __repr__(self):
        return self.email


class KnownDevice(Base):
    __tablename__ = "known_devices"
    __table_args__ = (Index("ix_known_devices_user_device", "user_id", "device_hash"),)

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
    # Extracted page text, for whole-document chat context. NULL for documents
    # indexed before it was kept; those fall back to retrieval.
    pages = Column(JSON, nullable=True)

    user = relationship("User", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan", passive_deletes=True)

    def __repr__(self):
        return f"{self.filename} (user_id={self.user_id})"


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    document_id = Column(BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page = Column(Integer, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    embedding = Column(Vector())
    embedding_model = Column(String(128), nullable=False, server_default="gemini-embedding-001")

    document = relationship("Document", back_populates="chunks")

    def __repr__(self):
        return f"Chunk {self.chunk_index} (page {self.page}) of doc_id={self.document_id}"
