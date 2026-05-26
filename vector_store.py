import os
import uuid
import logging
import google.generativeai as genai
import chromadb
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("vector_store")

class LegalVectorStore:
    def __init__(self, db_path: str = "./db"):
        self.db_path = db_path
        self.collection_name = "legal_documents"
        
        # Initialize Google Generative AI config
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logger.warning("GEMINI_API_KEY not found in environment. Please set it.")
        else:
            genai.configure(api_key=api_key)
            
        # Initialize ChromaDB client
        self.chroma_client = chromadb.PersistentClient(path=self.db_path)
        self.collection = self.chroma_client.get_or_create_collection(
            name=self.collection_name
        )

    def _get_embedding(self, texts: list[str], task_type: str = "retrieval_document") -> list[list[float]]:
        """Generates embeddings using Google's gemini-embedding-001 model."""
        try:
            response = genai.embed_content(
                model="models/gemini-embedding-001",
                content=texts,
                task_type=task_type
            )
            # Response is typically a dictionary containing {"embedding": [[0.1, 0.2, ...]]}
            return response["embedding"]
        except Exception as e:
            logger.error(f"Error generating embedding with Gemini: {e}")
            raise e

    def _get_embeddings_batched(self, texts: list[str], task_type: str = "retrieval_document", batch_size: int = 20) -> list[list[float]]:
        """Generates embeddings in batches to avoid API token limits."""
        all_embeddings = []
        total_batches = (len(texts) + batch_size - 1) // batch_size
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_num = i // batch_size + 1
            if total_batches > 1:
                logger.info(f"Embedding batch {batch_num}/{total_batches} ({len(batch)} chunks)")
            embeddings = self._get_embedding(batch, task_type)
            all_embeddings.extend(embeddings)
        return all_embeddings

    def chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 150) -> list[str]:
        """
        Splits text into chunks of approximately chunk_size characters,
        preserving word boundaries and overlapping between chunks.
        """
        if not text:
            return []
            
        words = text.split()
        chunks = []
        current_chunk = []
        current_size = 0
        
        for word in words:
            current_chunk.append(word)
            current_size += len(word) + 1 # +1 for the space
            if current_size >= chunk_size:
                chunks.append(" ".join(current_chunk))
                # Build overlap for the next chunk
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

    def add_document(self, filename: str, text: str, owner: str):
        """Legacy fallback to index document as a single page (Page 1)."""
        self.add_document_pages(filename, [{"page": 1, "text": text}], owner)

    def add_document_pages(self, filename: str, pages: list[dict], owner: str):
        """Chunks a document page-by-page, generates embeddings, and indexes them with page metadata in ChromaDB."""
        logger.info(f"Indexing document pages: {filename} for owner: {owner}...")
        
        all_chunks = []
        all_metadatas = []
        
        for p in pages:
            page_num = p["page"]
            page_text = p["text"]
            chunks = self.chunk_text(page_text)
            for i, chunk in enumerate(chunks):
                all_chunks.append(chunk)
                all_metadatas.append({
                    "filename": filename,
                    "page": page_num,
                    "chunk_index": i,
                    "owner": owner
                })
                
        if not all_chunks:
            logger.warning(f"No text to index for file {filename}")
            return
            
        logger.info(f"Split {filename} into {len(all_chunks)} chunks across pages. Generating embeddings...")
        embeddings = self._get_embeddings_batched(all_chunks, task_type="retrieval_document")
        
        ids = [f"{filename}_p{meta['page']}_{meta['chunk_index']}_{str(uuid.uuid4())[:8]}" for meta in all_metadatas]
        
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=all_chunks,
            metadatas=all_metadatas
        )
        logger.info(f"Successfully indexed {filename} in vector database for user '{owner}'.")

    def query_similar_context(self, query: str, owner: str, top_k: int = 5) -> list[dict]:
        """
        Embeds the query, searches ChromaDB for matching contexts, 
        and returns list of matching documents with scores and metadata.
        """
        if not query:
            return []
            
        logger.info(f"Searching vector database for query: {query} (owner: {owner})")
        query_embedding = self._get_embedding([query], task_type="retrieval_query")[0]
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where={"owner": owner}
        )
        
        contexts = []
        if results and results["documents"]:
            # Parse results structure: results['documents'][0], results['metadatas'][0], results['distances'][0]
            docs = results["documents"][0]
            metas = results["metadatas"][0]
            distances = results["distances"][0] if "distances" in results else [0.0] * len(docs)
            
            for doc, meta, dist in zip(docs, metas, distances):
                contexts.append({
                    "text": doc,
                    "metadata": meta,
                    "distance": dist
                })
        return contexts

    def list_documents(self, owner: str) -> list[str]:
        """Returns a list of unique filenames indexed in the vector database for this owner.
        
        Uses include=[] to fetch only IDs (no metadata/embeddings), then extracts
        filenames from the ID format: '{filename}_p{page}_{chunk}_{uuid}'.
        Falls back to metadata if ID parsing fails.
        """
        results = self.collection.get(where={"owner": owner}, include=[])
        if not results or not results["ids"]:
            return []
        
        filenames = set()
        for doc_id in results["ids"]:
            # IDs are formatted as: {filename}_p{page}_{chunk}_{uuid8}
            # Extract filename by finding the last "_p\d+" pattern
            import re
            match = re.match(r"^(.+?)_p\d+_\d+_[a-f0-9]{8}$", doc_id)
            if match:
                filenames.add(match.group(1))
            else:
                # Fallback: fetch metadata for this single ID
                try:
                    meta_result = self.collection.get(ids=[doc_id], include=["metadatas"])
                    if meta_result and meta_result["metadatas"]:
                        meta = meta_result["metadatas"][0]
                        if meta and "filename" in meta:
                            filenames.add(meta["filename"])
                except Exception:
                    pass
        return sorted(list(filenames))

    def delete_document(self, filename: str, owner: str) -> int:
        """Deletes all chunks of a document from the vector store. Returns count of deleted chunks."""
        results = self.collection.get(
            where={"$and": [{"filename": filename}, {"owner": owner}]},
            include=[]
        )
        if not results or not results["ids"]:
            return 0

        ids_to_delete = results["ids"]
        self.collection.delete(ids=ids_to_delete)
        logger.info(f"Deleted {len(ids_to_delete)} chunks for '{filename}' (owner: {owner})")
        return len(ids_to_delete)

if __name__ == "__main__":
    print("Vector Store Module Initialized.")
