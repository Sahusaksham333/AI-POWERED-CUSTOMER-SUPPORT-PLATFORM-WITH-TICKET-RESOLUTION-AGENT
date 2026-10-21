"""Chunk and index Markdown, text, PDF and DOCX knowledge files in Chroma."""
from __future__ import annotations
import argparse
import hashlib
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import chromadb
from pypdf import PdfReader
from docx import Document
from sentence_transformers import SentenceTransformer
from app.supportpilot.config import CHROMA_DIR, EMBEDDING_MODEL, KNOWLEDGE_DIR

SUPPORTED = {".md", ".txt", ".pdf", ".docx"}


def read_document(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    if suffix == ".docx":
        document = Document(str(path))
        return "\n".join(p.text for p in document.paragraphs if p.text.strip())
    return ""


def chunk_text(text: str, size: int = 1000, overlap: int = 150) -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []
    chunks, start = [], 0
    while start < len(text):
        chunk = text[start:start + size].strip()
        if chunk:
            chunks.append(chunk)
        if start + size >= len(text):
            break
        start += size - overlap
    return chunks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=KNOWLEDGE_DIR)
    parser.add_argument("--reset", action="store_true", help="Replace the current SupportPilot collection")
    parser.add_argument("--chunk-size", type=int, default=1000)
    parser.add_argument("--overlap", type=int, default=150)
    args = parser.parse_args()
    files = sorted(p for p in args.path.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED and p.name.lower() != "readme.md")
    if not files:
        raise SystemExit(f"No supported knowledge files found under {args.path}. Add .md, .txt, .pdf or .docx files first.")
    chunks, ids, metadatas = [], [], []
    for file in files:
        content = read_document(file)
        rel = str(file.relative_to(args.path)).replace("\\", "/")
        for index, chunk in enumerate(chunk_text(content, args.chunk_size, args.overlap)):
            unique = hashlib.sha1(f"{rel}:{index}:{chunk}".encode("utf-8")).hexdigest()
            chunks.append(chunk)
            ids.append(unique)
            metadatas.append({"source": rel, "chunk": index})
    if not chunks:
        raise SystemExit("No non-empty text was extracted. Scanned PDFs may require OCR, which this script does not perform.")
    print(f"Loaded {len(files)} files and prepared {len(chunks)} chunks.")
    embedder = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    try:
        if args.reset:
            client.delete_collection("supportpilot_knowledge")
    except Exception:
        pass
    collection = client.get_or_create_collection(
        name="supportpilot_knowledge", metadata={"hnsw:space": "cosine", "embedding_model": EMBEDDING_MODEL}
    )
    # Replace same IDs safely; batches avoid large temporary memory allocations.
    for start in range(0, len(chunks), 64):
        batch_docs = chunks[start:start + 64]
        vectors = embedder.encode(batch_docs, normalize_embeddings=True, show_progress_bar=False).tolist()
        collection.upsert(ids=ids[start:start + 64], documents=batch_docs,
                          metadatas=metadatas[start:start + 64], embeddings=vectors)
        print(f"Indexed {min(start + 64, len(chunks))}/{len(chunks)} chunks")
    print(f"Chroma collection ready at {CHROMA_DIR}; total chunks: {collection.count()}")

if __name__ == "__main__":
    main()
