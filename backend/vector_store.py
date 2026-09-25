import logging
import re
from sqlalchemy import select, delete, desc, func, text
from sqlalchemy.orm import Session

from embeddings import get_embedder

logger = logging.getLogger("vector_store")


_NAME_RANK_SQL = text("""
WITH word AS (
    SELECT DISTINCT regexp_replace(lex, '[^a-z0-9]', '', 'g') AS w
    FROM unnest(tsvector_to_array(to_tsvector('simple', :q))) AS lex
    WHERE ts_lexize('english_stem', lex) <> '{}'
      AND length(regexp_replace(lex, '[^a-z0-9]', '', 'g')) >= 3
),
doc AS (
    SELECT id, lower(regexp_replace(filename, '[^A-Za-z0-9]', '', 'g')) AS name
    FROM documents WHERE user_id = :uid
),
hit AS (
    SELECT doc.id, word.w FROM doc JOIN word ON position(word.w IN doc.name) > 0
),
df AS (
    SELECT w, count(*) AS n FROM hit GROUP BY w
)
SELECT hit.id AS id, sum(1.0 / df.n) AS rank, string_agg(hit.w, ' ') AS words
FROM hit JOIN df USING (w)
GROUP BY hit.id
ORDER BY rank DESC
""")


# The generator's instructions and context formats live beside the retrieval
# that produces the context, so the API and evals/faithfulness.py send the
# model byte-for-byte the same prompt. The eval only measures what ships if so.
SYSTEM_PROMPT = (
    "You are a helpful and professional Legal Assistant. Answer based strictly on the provided document contexts.\n"
    "If the answer cannot be found in the context, state so. Always reference sources (filenames and page numbers).\n"
    "If the question asks about a specific provision and the context contains none, say that first. You may then "
    "mention related provisions, labelled as related, but never present one as the answer or infer the missing "
    "provision from it.\n\n"
    "CONTEXT:\n{context}"
)


def format_chunks(hits: list[dict]) -> str:
    return "\n\n".join(
        f"--- Chunk {i + 1} (Source: {h['metadata'].get('filename', '?')}, Page: {h['metadata'].get('page', 1)}) ---\n{h['text']}"
        for i, h in enumerate(hits)
    )


def format_pages(filename: str, pages: list[dict]) -> str:
    return "\n\n".join(f"--- {filename}, Page {p['page']} ---\n{p['text']}" for p in pages if p["text"].strip())


def estimate_tokens(pages: list[dict]) -> int:
    """Four characters a token: rough, and the estimate the eval sized documents by."""
    return sum(len(p["text"]) for p in pages) // 4


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
            document = Document(
                filename=filename,
                user_id=user.id,
                pages=[{"page": p["page"], "text": p["text"]} for p in pages],
            )
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

    def match_documents_by_name(self, query: str, user, session: Session) -> list[tuple[int, float, str]]:

        from legal_api.models import Document

        if not query:
            return []

        rows = session.execute(_NAME_RANK_SQL, {"q": query, "uid": user.id}).all()
        return [(row.id, float(row.rank), row.words) for row in rows if row.rank and row.rank > 0]

    def query_similar_context(self, query: str, user, session: Session, top_k: int = 5,
                              document_ids: list[int] | None = None) -> list[dict]:

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
        )
        if document_ids:
            results = results.filter(Document.id.in_(document_ids))
        results = (
            results
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

    @staticmethod
    def _strip_title(query: str, matched: set[str]) -> str:
        tokens = query.split()
        norm = [re.sub(r"[^a-z0-9]", "", t.lower()) for t in tokens]
        hits = [i for i, t in enumerate(norm) if t in matched]
        if not hits:
            return query
        connectors = {"of", "and", "the", "inc", "co", "llc", "ltd", "corp", "plc", "sa", "ag"}
        end = hits[-1]
        start = end
        i = end - 1
        while i >= 0 and (norm[i] in matched or norm[i] in connectors):
            start = i
            i -= 1
        while start < end and norm[start] not in matched:
            start += 1
        residual = tokens[:start] + tokens[end + 1:]
        return " ".join(residual) if len(residual) >= 2 else query

    @staticmethod
    def _pick_document(matches: list[tuple[int, float, str]], candidates: list[int] | None = None,
                       margin: float = 1.5) -> tuple[int, float, str] | None:
        if candidates:
            allowed = set(candidates)
            matches = [m for m in matches if m[0] in allowed]
        if matches and (len(matches) == 1 or matches[0][1] > matches[1][1] * margin - 1e-9):
            return matches[0]
        return None

    def resolve_scope(self, query: str, user, session: Session, document_ids: list[int] | None = None,
                      margin: float = 1.5) -> tuple[list[int] | None, str]:

        matches = self.match_documents_by_name(query, user, session)
        picked = self._pick_document(matches, document_ids, margin)
        if not picked:
            return (list(document_ids) if document_ids else None), query
        doc_id, _, words = picked
        query = self._strip_title(query, set(words.split()))
        logger.info(f"Query scoped to document id={doc_id}; searching for: {query!r}")
        return [doc_id], query

    def query_scoped_context(self, query: str, user, session: Session, top_k: int = 5,
                             margin: float = 1.5, document_ids: list[int] | None = None) -> list[dict]:
        scope, query = self.resolve_scope(query, user, session, document_ids, margin)
        return self.query_similar_context(query, user, session, top_k=top_k, document_ids=scope)

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
