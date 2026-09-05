import logging
from sqlalchemy import select, delete, func
from sqlalchemy.orm import Session

from embeddings import get_embedder

logger = logging.getLogger("vector_store")


class LegalVectorStore:
    def __init__(self, embedder=None):
        
        self.embedder = embedder or get_embedder()

    def chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 150) -> list[str]:
        if not text:
            return []
        words = text.split()
        chunks = []
        current_chunk = []
        current_size = 0
        for word in words:
            current_chunk.append(word)
            current_size += len(word) + 1
            if current_size >= chunk_size:
                chunks.append(" ".join(current_chunk))
                overlap_words = []
                overlap_size = 0
                for w in reversed(current_chunk):
                    if overlap_size + len(w) + 1 < overlap:
                        overlap_words.insert(0, w)
                        overlap_size += len(w) + 1
                    else:
                        break
                current_chunk = overlap_words
                current_size = overlap_size
        if current_chunk:
            chunks.append(" ".join(current_chunk))
        return chunks

    def add_document_pages(self, filename: str, pages: list[dict], user, session: Session,
                           chunk_size: int = 1000, overlap: int = 150):

        from legal_api.models import Document, DocumentChunk

        logger.info(f"Indexing document pages: {filename} for owner: {user.email}...")
        try:
            document = Document(filename=filename, user_id=user.id)
            session.add(document)
            session.flush()  # Get the document.id

            all_chunks = []
            all_metadatas = []

            for p in pages:
                page_num = p["page"]
                page_text = p["text"]
                chunks = self.chunk_text(page_text, chunk_size=chunk_size, overlap=overlap)
                for i, chunk in enumerate(chunks):
                    all_chunks.append(chunk)
                    all_metadatas.append({
                        "page": page_num,
                        "chunk_index": i
                    })

            if not all_chunks:
                logger.warning(f"No text to index for file {filename}")
                session.commit()
                return

            logger.info(f"Split {filename} into {len(all_chunks)} chunks across pages. Generating embeddings...")
            embeddings = self.embedder.embed_documents(all_chunks)

            db_chunks = [
                DocumentChunk(
                    document_id=document.id,
                    page=all_metadatas[i]["page"],
                    chunk_index=all_metadatas[i]["chunk_index"],
                    text=chunk_text,
                    embedding=embedding,
                    embedding_model=self.embedder.name
                )
                for i, (chunk_text, embedding) in enumerate(zip(all_chunks, embeddings))
            ]
            session.add_all(db_chunks)
            session.commit()
            logger.info(f"Successfully indexed {filename} in vector database for user '{user.email}'.")
        except Exception as e:
            session.rollback()
            logger.error(f"Error indexing document {filename}: {e}")
            # Clean up the document database record if indexing failed
            try:
                session.execute(
                    delete(Document).where(Document.filename == filename, Document.user_id == user.id)
                )
                session.commit()
            except Exception as cleanup_err:
                session.rollback()
                logger.error(f"Error cleaning up document {filename} record: {cleanup_err}")
            raise e

    def query_similar_context(self, query: str, user, session: Session, top_k: int = 5) -> list[dict]:

        from legal_api.models import Document, DocumentChunk

        if not query:
            return []

        logger.info(f"Searching vector database for query: {query} (owner: {user.email})")
        query_embedding = self.embedder.embed_query(query)

        results = (
            session.query(
                DocumentChunk.text,
                DocumentChunk.page,
                DocumentChunk.chunk_index,
                Document.filename,
                DocumentChunk.embedding.l2_distance(query_embedding).label("distance")
            )
            .join(Document, DocumentChunk.document_id == Document.id)
            .filter(Document.user_id == user.id)
            .filter(DocumentChunk.embedding_model == self.embedder.name)
            .order_by("distance")
            .limit(top_k)
            .all()
        )

        return [
            {
                "text": row.text,
                "metadata": {
                    "filename": row.filename,
                    "page": row.page,
                    "chunk_index": row.chunk_index,
                    "owner": user.email
                },
                "distance": round(float(row.distance), 4)
            }
            for row in results
        ]

    def list_documents(self, user, session: Session) -> list[str]:

        from legal_api.models import Document
        result = session.execute(
            select(Document.filename).where(Document.user_id == user.id)
        )
        docs = [row[0] for row in result.all()]
        return sorted(docs)

    def delete_document(self, filename: str, user, session: Session) -> int:

        from legal_api.models import Document, DocumentChunk

        try:
            doc = session.execute(
                select(Document).where(Document.user_id == user.id, Document.filename == filename)
            )
            doc = doc.scalar_one_or_none()
            if not doc:
                return 0

            chunk_count = session.execute(
                select(func.count()).select_from(DocumentChunk).where(DocumentChunk.document_id == doc.id)
            )
            chunk_count = chunk_count.scalar()

            session.delete(doc)  # Cascade deletes chunks
            session.commit()
            logger.info(f"Deleted {chunk_count} chunks for '{filename}' (owner: {user.email})")
            return chunk_count
        except Exception:
            session.rollback()
            logger.exception(f"Error deleting document {filename} for {user.email}")
            raise
