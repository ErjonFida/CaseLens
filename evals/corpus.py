import argparse
import hashlib
import logging
from pathlib import Path
from legal_api.models import User
from . import CORPUS_DIR, EVAL_TENANT_EMAIL, EVAL_ROOT
from .cache import CachedEmbedder, EmbeddingCache
from embeddings import get_embedder
from database import SyncSessionLocal
from legal_api.models import Document
from ocr import extract_document_pages
from vector_store import LegalVectorStore

logger = logging.getLogger("evals.corpus")

SUPPORTED = {".pdf", ".txt", ".png", ".jpg", ".jpeg", ".tiff", ".bmp"}


def get_or_create_tenant(session):

    user = session.query(User).filter_by(email=EVAL_TENANT_EMAIL).one_or_none()
    if user is None:
        user = User(
            email=EVAL_TENANT_EMAIL,
            password_hash="!",  # unusable: this tenant is never logged into
            first_name="Evaluation",
            last_name="Harness",
        )
        session.add(user)
        session.commit()
        logger.info(f"Created evaluation tenant {EVAL_TENANT_EMAIL}")
    return user


def build_embedder(chunk_note: str = ""):

    cache = EmbeddingCache(EVAL_ROOT / ".cache" / "embeddings.sqlite3")
    return CachedEmbedder(get_embedder(), cache), cache


def corpus_fingerprint(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED:
            digest.update(path.name.encode("utf-8"))
            digest.update(str(path.stat().st_size).encode("utf-8"))
    return digest.hexdigest()[:16]


def index(directory: Path = CORPUS_DIR, chunk_size: int = 1000, overlap: int = 150) -> dict:

    files = sorted(p for p in directory.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED)
    if not files:
        raise SystemExit(
            f"No documents in {directory}. Drop 40-80 legal documents there first - "
            f"retrieval metrics over a handful of files measure nothing."
        )

    session = SyncSessionLocal()
    embedder, cache = build_embedder()
    store = LegalVectorStore(embedder=embedder)  

    try:
        user = get_or_create_tenant(session)

        existing = session.query(Document).filter_by(user_id=user.id).all()
        for document in existing:
            session.delete(document)  
        session.commit()
        if existing:
            logger.info(f"Cleared {len(existing)} previously indexed documents")

        indexed, skipped, total_pages = 0, [], 0
        for path in files:
            try:
                pages = extract_document_pages(str(path))
            except Exception as e:
                logger.error(f"Extraction failed for {path.name}: {e}")
                skipped.append(path.name)
                continue

            pages = [p for p in pages if p.get("text", "").strip()]
            if not pages:
                logger.warning(f"No extractable text in {path.name}")
                skipped.append(path.name)
                continue

            store.add_document_pages(path.name, pages, user, session, chunk_size=chunk_size, overlap=overlap)
            indexed += 1
            total_pages += len(pages)
            logger.info(f"[{indexed}/{len(files)}] {path.name} ({len(pages)} pages)")

        summary = {
            "documents_indexed": indexed,
            "documents_skipped": skipped,
            "pages": total_pages,
            "chunk_size": chunk_size,
            "overlap": overlap,
            "embedding_model": embedder.name,
            "dimensions": embedder.dimensions,
            "corpus_fingerprint": corpus_fingerprint(directory),
            "cache": cache.stats,
        }
        return summary
    finally:
        cache.close()
        session.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Index the evaluation corpus.")
    parser.add_argument("--corpus", type=Path, default=CORPUS_DIR)
    parser.add_argument("--chunk-size", type=int, default=1000)
    parser.add_argument("--overlap", type=int, default=150)
    args = parser.parse_args()

    summary = index(args.corpus, args.chunk_size, args.overlap)
    print()
    for key, value in summary.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
