"""
Document Embedding Script

This script loads documents (markdown + YAML) and converts them into vector embeddings
stored in ChromaDB for semantic search.

PROCESS:
1. Load documents from filesystem
2. Split into chunks (500 characters each)
3. Generate embeddings for each chunk (text → vector)
4. Store in ChromaDB with metadata

WHY CHUNKING?
- Embedding models have context limits (e.g., 8192 tokens)
- Smaller chunks = more precise retrieval
- But too small = loss of context
- Sweet spot: 300-800 characters per chunk
"""

import os
import chromadb
from chromadb.utils import embedding_functions
from pathlib import Path
import yaml
from dotenv import load_dotenv

load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
CHROMA_PATH = "./chroma_db"
SUPPORT_DOCS_PATH = os.getenv("SUPPORT_DOCS_PATH", "./source_data/support_docs")
RELEASES_PATH = os.getenv("RELEASES_PATH", "./source_data/releases")

# Chunk configuration
# These values are tuned based on testing:
# - Too small (< 200): Lose context
# - Too large (> 1000): Too much noise, less precise retrieval
CHUNK_SIZE = 500  # characters
CHUNK_OVERLAP = 50  # characters to overlap between chunks (for continuity)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    """
    Split text into overlapping chunks
    
    WHY OVERLAP?
    If we have: "...connection timeout. The firewall..."
    Without overlap, we might split at the period and lose the connection
    between "timeout" and "firewall".
    
    With overlap, chunk 1 ends with "...timeout. The firewall..."
    and chunk 2 starts with "The firewall..."
    So both chunks contain the key transition.
    
    Java equivalent: sliding window algorithm
    """
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        
        # Skip very small chunks (< 100 chars) at the end
        if len(chunk.strip()) > 100:
            chunks.append(chunk.strip())
        
        start += chunk_size - overlap  # Move window forward
    
    return chunks

def load_markdown_files(directory: str):
    """Load all .md files from directory"""
    documents = []
    path = Path(directory)
    
    if not path.exists():
        print(f"Warning: Directory not found: {directory}")
        return documents
    
    for md_file in path.glob("*.md"):
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()
            documents.append({
                "content": content,
                "metadata": {
                    "source": str(md_file.name),
                    "type": "support_doc"
                }
            })
    
    return documents

def load_yaml_files(directory: str):
    """Load all .yaml files from directory"""
    documents = []
    path = Path(directory)
    
    if not path.exists():
        print(f"Warning: Directory not found: {directory}")
        return documents
    
    for yaml_file in path.glob("*.yaml"):
        with open(yaml_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            
            # Convert YAML to readable text format
            # This makes embeddings more meaningful
            content_parts = []
            content_parts.append(f"Version: {data.get('version', 'Unknown')}")
            content_parts.append(f"Release Date: {data.get('release_date', 'Unknown')}")
            content_parts.append(f"\nSummary:\n{data.get('summary', '')}")
            
            if 'features' in data:
                content_parts.append("\nFeatures:")
                for feature in data['features']:
                    content_parts.append(f"- {feature.get('name')}: {feature.get('description')}")
            
            if 'bug_fixes' in data and data['bug_fixes']:
                content_parts.append("\nBug Fixes:")
                for fix in data['bug_fixes']:
                    content_parts.append(f"- {fix.get('description')} (Severity: {fix.get('severity')})")
            
            if 'breaking_changes' in data and data['breaking_changes']:
                content_parts.append("\nBreaking Changes:")
                for change in data['breaking_changes']:
                    content_parts.append(f"- {change.get('change')}: {change.get('impact')}")
            
            if 'deprecations' in data and data['deprecations']:
                content_parts.append("\nDeprecations:")
                for dep in data['deprecations']:
                    content_parts.append(f"- {dep.get('feature')} (Deprecated in {dep.get('deprecated_in')})")
            
            content = "\n".join(content_parts)
            documents.append({
                "content": content,
                "metadata": {
                    "source": str(yaml_file.name),
                    "version": data.get('version', 'Unknown'),
                    "type": "release_note"
                }
            })
    
    return documents

# ============================================================================
# EMBEDDING PIPELINE
# ============================================================================

def embed_documents():
    """Main embedding pipeline"""
    
    print("=" * 60)
    print("DOCUMENT EMBEDDING PIPELINE")
    print("=" * 60)
    
    if not GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY not set in environment")
        print("Please create a .env file with: GEMINI_API_KEY=your_key_here")
        return
    
    # Initialize ChromaDB client
    # PersistentClient saves data to disk (unlike Client which is in-memory only)
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    
    # Create embedding function
    # This is the neural network that converts text → vectors
    # Google's text-embedding-004 produces 768-dimensional vectors
    google_ef = embedding_functions.GoogleGenerativeAiEmbeddingFunction(
        api_key=GEMINI_API_KEY,
        model_name="models/gemini-embedding-001"
    )
    
    print(f"\nUsing embedding model: gemini-embedding-001")
    print(f"ChromaDB storage: {CHROMA_PATH}")
    
    # ========================================================================
    # EMBED SUPPORT DOCUMENTS
    # ========================================================================
    
    print("\n" + "-" * 60)
    print("EMBEDDING SUPPORT DOCUMENTS")
    print("-" * 60)
    
    # Delete existing collection if it exists (for clean setup)
    try:
        client.delete_collection("support_docs")
        print("Deleted existing support_docs collection")
    except:
        pass
    
    # Create collection
    # A collection is like a table in SQL - it groups related vectors
    support_collection = client.create_collection(
        name="support_docs",
        embedding_function=google_ef,
        metadata={"description": "Support documentation for troubleshooting"}
    )
    
    # Load documents
    support_docs = load_markdown_files(SUPPORT_DOCS_PATH)
    print(f"Loaded {len(support_docs)} support documents")
    
    # Process each document
    total_chunks = 0
    for doc in support_docs:
        # Split into chunks
        chunks = chunk_text(doc['content'])
        print(f"  {doc['metadata']['source']}: {len(chunks)} chunks")
        
        # Add to ChromaDB
        # Note: We don't manually create embeddings here!
        # ChromaDB uses the embedding_function to automatically generate vectors
        for i, chunk in enumerate(chunks):
            chunk_id = f"{doc['metadata']['source']}_chunk{i}"
            support_collection.add(
                ids=[chunk_id],
                documents=[chunk],
                metadatas=[{
                    **doc['metadata'],
                    "chunk_index": i,
                    "total_chunks": len(chunks)
                }]
            )
        
        total_chunks += len(chunks)
    
    print(f"[OK] Embedded {total_chunks} chunks into support_docs collection")
    
    # ========================================================================
    # EMBED RELEASE NOTES
    # ========================================================================
    
    print("\n" + "-" * 60)
    print("EMBEDDING RELEASE NOTES")
    print("-" * 60)
    
    try:
        client.delete_collection("release_notes")
        print("Deleted existing release_notes collection")
    except:
        pass
    
    release_collection = client.create_collection(
        name="release_notes",
        embedding_function=google_ef,
        metadata={"description": "Product release notes and version history"}
    )
    
    # Load documents
    release_docs = load_yaml_files(RELEASES_PATH)
    print(f"Loaded {len(release_docs)} release notes")
    
    # Process each document
    total_chunks = 0
    for doc in release_docs:
        chunks = chunk_text(doc['content'])
        print(f"  {doc['metadata']['source']}: {len(chunks)} chunks")
        
        for i, chunk in enumerate(chunks):
            chunk_id = f"{doc['metadata']['source']}_chunk{i}"
            release_collection.add(
                ids=[chunk_id],
                documents=[chunk],
                metadatas=[{
                    **doc['metadata'],
                    "chunk_index": i,
                    "total_chunks": len(chunks)
                }]
            )
        
        total_chunks += len(chunks)
    
    print(f"[OK] Embedded {total_chunks} chunks into release_notes collection")
    
    # ========================================================================
    # VERIFY EMBEDDINGS
    # ========================================================================
    
    print("\n" + "-" * 60)
    print("VERIFICATION")
    print("-" * 60)
    
    # Test query to verify embeddings work
    print("\nTesting semantic search with query: 'connection timeout'")
    results = support_collection.query(
        query_texts=["connection timeout"],
        n_results=2
    )
    
    if results['documents'] and len(results['documents']) > 0:
        print(f"Found {len(results['documents'][0])} results:")
        for i, doc in enumerate(results['documents'][0]):
            print(f"\n  Result {i+1}:")
            print(f"  Similarity: {1 - results['distances'][0][i]:.3f}")
            print(f"  Source: {results['metadatas'][0][i].get('source')}")
            print(f"  Preview: {doc[:100]}...")
    else:
        print("Warning: No results found. Embeddings may not be working correctly.")
    
    print("\n" + "=" * 60)
    print("EMBEDDING COMPLETE")
    print("=" * 60)
    print(f"\nTotal collections: 2")
    print(f"  - support_docs: {support_collection.count()} chunks")
    print(f"  - release_notes: {release_collection.count()} chunks")
    print(f"\nChromaDB ready for queries!")

if __name__ == '__main__':
    embed_documents()
