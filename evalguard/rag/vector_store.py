import os
import math
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional
from evalguard.ingestion.loader import Document

class BaseVectorStore:
    def add_documents(self, documents: List[Document]) -> None:
        raise NotImplementedError
    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        raise NotImplementedError
    def clear(self) -> None:
        raise NotImplementedError

class SimpleTFIDFVectorStore(BaseVectorStore):
    """Zero-dependency vector store using TF-IDF cosine similarity."""

    def __init__(self, collection_name: str = "default"):
        self.collection_name = collection_name
        self.documents: List[Document] = []
        self.idf: Dict[str, float] = {}

    def _tokenize(self, text: str) -> List[str]:
        import re
        return re.findall(r"\w+", text.lower())

    def _compute_tf(self, tokens: List[str]) -> Dict[str, float]:
        tf = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        total = len(tokens) or 1
        return {k: v / total for k, v in tf.items()}

    def _rebuild_idf(self):
        n_docs = len(self.documents)
        df = {}
        for doc in self.documents:
            words = set(self._tokenize(doc.text))
            for w in words:
                df[w] = df.get(w, 0) + 1
        self.idf = {w: math.log((1 + n_docs) / (1 + count)) + 1.0 for w, count in df.items()}

    def add_documents(self, documents: List[Document]) -> None:
        self.documents.extend(documents)
        self._rebuild_idf()

    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        if not self.documents:
            return []

        q_tokens = self._tokenize(query)
        q_tf = self._compute_tf(q_tokens)
        q_vec = {w: q_tf[w] * self.idf.get(w, 1.0) for w in q_tf}
        q_norm = math.sqrt(sum(v * v for v in q_vec.values())) or 1e-9

        scored_results = []
        for doc in self.documents:
            d_tokens = self._tokenize(doc.text)
            d_tf = self._compute_tf(d_tokens)
            d_vec = {w: d_tf[w] * self.idf.get(w, 1.0) for w in d_tf}
            d_norm = math.sqrt(sum(v * v for v in d_vec.values())) or 1e-9

            # Dot product
            dot = sum(q_vec.get(w, 0) * d_vec.get(w, 0) for w in q_vec)
            sim = dot / (q_norm * d_norm)

            scored_results.append({
                "text": doc.text,
                "metadata": doc.metadata,
                "doc_id": doc.doc_id,
                "score": float(sim)
            })

        scored_results.sort(key=lambda x: x["score"], reverse=True)
        return scored_results[:top_k]

    def clear(self) -> None:
        self.documents = []
        self.idf = {}

_EMBEDDERS: Dict[str, Any] = {}
_EMBEDDER_LOCK = threading.Lock()


def get_embedding_function(model_name: str):
    """One embedding model per process. Every vector store used to load its own copy (hundreds of MB, several seconds)
    on every request, which made the first chat message slow and could exhaust memory on a small machine."""
    with _EMBEDDER_LOCK:
        if model_name not in _EMBEDDERS:
            from chromadb.utils import embedding_functions
            try:
                _EMBEDDERS[model_name] = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=model_name)
            except Exception:  # sentence-transformers missing or the model can't be downloaded
                _EMBEDDERS[model_name] = embedding_functions.DefaultEmbeddingFunction()
        return _EMBEDDERS[model_name]


def warm_up(model_name: str) -> None:
    """Load the embedding model and run it once, so the first real request doesn't pay for it."""
    get_embedding_function(model_name)(["warm up"])


class ChromaVectorStore(BaseVectorStore):
    """ChromaDB implementation with sentence-transformers embeddings."""

    def __init__(self, persist_dir: str, collection_name: str = "evalguard_docs", embedding_model_name: str = "all-MiniLM-L6-v2"):
        import chromadb

        self.persist_dir = persist_dir
        self.collection_name = collection_name
        Path(persist_dir).mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(path=persist_dir)
        self.emb_fn = get_embedding_function(embedding_model_name)

        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.emb_fn,
            metadata={"hnsw:space": "cosine"}
        )

    def add_documents(self, documents: List[Document]) -> None:
        if not documents:
            return

        texts = [doc.text for doc in documents]
        metadatas = []
        for doc in documents:
            clean_meta = {}
            for k, v in doc.metadata.items():
                if isinstance(v, (str, int, float, bool)):
                    clean_meta[k] = v
                else:
                    clean_meta[k] = str(v)
            metadatas.append(clean_meta)

        ids = [doc.doc_id or f"doc_{i}" for i, doc in enumerate(documents)]
        self.collection.upsert(
            documents=texts,
            metadatas=metadatas,
            ids=ids
        )

    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k
        )

        output = []
        if results and "documents" in results and results["documents"]:
            docs = results["documents"][0]
            metas = results["metadatas"][0] if "metadatas" in results and results["metadatas"] else [{}] * len(docs)
            ids = results["ids"][0] if "ids" in results and results["ids"] else [""] * len(docs)
            distances = results["distances"][0] if "distances" in results and results["distances"] else [0.0] * len(docs)

            for text, meta, doc_id, dist in zip(docs, metas, ids, distances):
                # Cosine distance to similarity: sim = 1 - dist
                sim = max(0.0, 1.0 - dist)
                output.append({
                    "text": text,
                    "metadata": meta,
                    "doc_id": doc_id,
                    "score": float(sim)
                })

        return output

    def clear(self) -> None:
        try:
            self.client.delete_collection(self.collection_name)
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=self.emb_fn,
                metadata={"hnsw:space": "cosine"}  # must match __init__, else Chroma falls back to L2
            )
        except Exception as e:
            print(f"[Warning] Clear collection: {e}")

def get_vector_store(collection_name: str = "evalguard_docs") -> BaseVectorStore:
    """Factory creating ChromaVectorStore if chromadb is installed, else TF-IDF store."""
    try:
        import chromadb
        from evalguard.config import settings
        return ChromaVectorStore(
            persist_dir=settings.CHROMA_PERSIST_DIR,
            collection_name=collection_name,
            embedding_model_name=settings.EMBEDDING_MODEL
        )
    except (ImportError, Exception) as e:
        # Graceful fallback to SimpleTFIDFVectorStore
        return SimpleTFIDFVectorStore(collection_name=collection_name)
