from typing import List
from .loader import Document

class TextChunker:
    """Splits documents into overlapping character or paragraph chunks."""

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_text(self, text: str) -> List[str]:
        text = text.strip()
        if not text:
            return []

        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        start = 0
        step = self.chunk_size - self.chunk_overlap

        while start < len(text):
            end = start + self.chunk_size
            chunk = text[start:end]

            # Try to snap to the nearest newline or period if possible
            if end < len(text):
                last_newline = chunk.rfind("\n")
                last_period = chunk.rfind(". ")
                break_point = max(last_newline, last_period)
                if break_point > int(self.chunk_size * 0.5):
                    chunk = text[start : start + break_point + 1]
                    # keep the configured overlap, but always make forward progress
                    start = max(start + 1, start + break_point + 1 - self.chunk_overlap)
                else:
                    start += step
            else:
                start += step

            cleaned = chunk.strip()
            if cleaned:
                chunks.append(cleaned)

        return chunks

    def chunk_documents(self, documents: List[Document]) -> List[Document]:
        chunked_docs = []
        for doc in documents:
            text_chunks = self.split_text(doc.text)
            for idx, chunk_text in enumerate(text_chunks):
                chunk_meta = dict(doc.metadata)
                chunk_meta["chunk_index"] = idx
                chunk_meta["total_chunks"] = len(text_chunks)
                chunk_id = f"{doc.doc_id or 'doc'}_chunk_{idx}"
                chunked_docs.append(Document(
                    text=chunk_text,
                    metadata=chunk_meta,
                    doc_id=chunk_id
                ))
        return chunked_docs
