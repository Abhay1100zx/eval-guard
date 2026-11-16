import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class Document:
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    doc_id: Optional[str] = None

class DocumentLoader:
    """Loads documents from files or directories (.txt, .md, .pdf)."""

    def __init__(self, domain: Optional[str] = None):
        self.domain = domain

    def load_file(self, file_path: Path) -> List[Document]:
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = file_path.suffix.lower()
        metadata = {
            "source": file_path.name,
            "file_path": str(file_path),
            "domain": self.domain or "general"
        }

        if ext in [".txt", ".md", ".json"]:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return [Document(text=content, metadata=metadata, doc_id=file_path.name)]

        elif ext == ".pdf":
            try:
                import pypdf
                reader = pypdf.PdfReader(str(file_path))
                docs = []
                for page_idx, page in enumerate(reader.pages):
                    page_text = page.extract_text() or ""
                    if page_text.strip():
                        page_meta = {**metadata, "page": page_idx + 1}
                        docs.append(Document(
                            text=page_text,
                            metadata=page_meta,
                            doc_id=f"{file_path.name}_p{page_idx+1}"
                        ))
                return docs
            except ImportError:
                print(f"[Warning] pypdf not installed. Reading {file_path.name} as text.")
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                return [Document(text=content, metadata=metadata, doc_id=file_path.name)]

        else:
            # Fallback to plain text read
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return [Document(text=content, metadata=metadata, doc_id=file_path.name)]

    def load_directory(self, directory_path: Path) -> List[Document]:
        directory_path = Path(directory_path)
        if not directory_path.exists():
            raise FileNotFoundError(f"Directory not found: {directory_path}")

        documents = []
        for file_path in directory_path.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in [".txt", ".md", ".pdf"]:
                docs = self.load_file(file_path)
                documents.extend(docs)
        return documents
