"""
MCP (Model Context Protocol) Server Implementation

WHAT THIS IS:
- A JSON-RPC 2.0 server that exposes "tools" to LLMs
- Tools are functions that the LLM can call by name with arguments
- Similar to Spring Boot's @RestController, but using JSON-RPC instead of REST

KEY CONCEPTS:
1. JSON-RPC: Remote procedure call protocol using JSON
   - Client sends: {"jsonrpc": "2.0", "method": "tools/call", "params": {...}}
   - Server responds: {"jsonrpc": "2.0", "result": {...}}

2. Tools: Functions that LLMs can discover and call
   - Each tool has: name, description, input_schema (JSON Schema)
   - LLM reads the schema to understand what arguments to pass

3. NO NLP HERE: MCP server doesn't parse natural language!
   - The LLM (Gemini/GPT) does the NLP
   - LLM converts "show me failed tasks" → execute_sql(query="SELECT * FROM tasks WHERE status='failed'")
   - MCP server just executes the function call
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import chromadb
from chromadb.utils import embedding_functions
import os
import yaml
from pathlib import Path

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests

# ============================================================================
# DATABASE CONNECTIONS
# ============================================================================

import setup_database
# Automatically initialize database on import if it doesn't exist
setup_database.main()

def get_db_connection():
    """
    Get SQLite database connection
    Similar to: DataSource.getConnection() in Spring Boot
    """
    conn = sqlite3.connect('data/database.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row  # Return rows as dictionaries
    return conn

# Initialize ChromaDB for vector search
# This is like initializing a search engine (think: Elasticsearch/Solr)
chroma_client = chromadb.PersistentClient(path="./chroma_db")

# Embedding function converts text → vectors (numbers)
# Example: "connection timeout" → [0.23, 0.45, 0.12, ...]
google_ef = embedding_functions.GoogleGenerativeAiEmbeddingFunction(
    api_key=os.getenv("GEMINI_API_KEY", ""),
    model_name="models/gemini-embedding-001"
)

# Get or create collections (like database tables, but for vectors)
try:
    support_collection = chroma_client.get_or_create_collection(
        name="support_docs",
        embedding_function=google_ef
    )
    release_collection = chroma_client.get_or_create_collection(
        name="release_notes", 
        embedding_function=google_ef
    )
except Exception as e:
    print(f"Warning: ChromaDB collections not ready: {e}")
    support_collection = None
    release_collection = None

# ============================================================================
# TOOL IMPLEMENTATIONS
# These are the actual functions that the LLM can call
# Think of each as a @PostMapping method in Spring Boot
# ============================================================================

def execute_sql(query: str = "", **kwargs) -> dict:
    """
    Tool: Execute SQL query on database
    
    HOW IT WORKS:
    1. LLM generates SQL from natural language (e.g., "show failed tasks" → SQL)
    2. LLM calls this tool via JSON-RPC: execute_sql(query="SELECT * FROM tasks...")
    3. This function executes the SQL and returns results
    4. LLM formats results into human-readable response
    
    INPUT (from LLM): {"query": "SELECT * FROM tasks WHERE status='failed'"}
    OUTPUT: {"columns": [...], "rows": [...], "row_count": 5}
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(query)
        
        # Get column names
        columns = [description[0] for description in cursor.description]
        
        # Fetch all rows and convert to list of dicts
        rows = []
        for row in cursor.fetchall():
            rows.append(dict(zip(columns, row)))
        
        conn.close()
        
        return {
            "success": True,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def get_database_schema(**kwargs) -> dict:
    """
    Tool: Get database schema (tables, columns, types)
    
    HOW IT WORKS:
    - LLM calls this to understand what data is available
    - Similar to SQL's INFORMATION_SCHEMA
    - LLM uses this to generate correct SQL queries
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get all table names
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        schema = {}
        for table in tables:
            # Get column info for each table
            cursor.execute(f"PRAGMA table_info({table})")
            columns = []
            for col in cursor.fetchall():
                columns.append({
                    "name": col[1],
                    "type": col[2],
                    "nullable": not col[3],
                    "primary_key": bool(col[5])
                })
            schema[table] = columns
        
        conn.close()
        return {
            "success": True,
            "schema": schema
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def search_support_docs(query: str = "", top_k: int = 3, **kwargs) -> dict:
    """
    Tool: Semantic search over support documentation
    
    HOW IT WORKS (THE RAG PART):
    1. Query text is converted to a vector (embedding)
       Example: "connection timeout" → [0.23, 0.45, 0.12, ...]
    
    2. ChromaDB finds documents with similar vectors (cosine similarity)
       Think: Find docs whose embeddings are "close" in vector space
    
    3. Returns top-K most similar documents
    
    4. LLM reads these docs and synthesizes an answer
    
    THIS IS NOT NLP - it's vector math:
    - Each document is already converted to vectors (done during ingestion)
    - Query is converted to vector
    - Find closest vectors using math (not keyword matching!)
    """
    if support_collection is None:
        return {"success": False, "error": "Support docs collection not initialized"}
    
    try:
        # This is where the vector search happens
        # query_texts: converts query to vector automatically
        # n_results: how many similar docs to return
        results = support_collection.query(
            query_texts=[query],
            n_results=top_k
        )
        
        # results structure:
        # - ids: document IDs
        # - documents: actual text content
        # - distances: how "far" each doc is from query (lower = more similar)
        # - metadatas: extra info about each doc
        
        documents = []
        if results['documents'] and len(results['documents']) > 0:
            for i, doc in enumerate(results['documents'][0]):
                documents.append({
                    "content": doc,
                    "metadata": results['metadatas'][0][i] if results['metadatas'] else {},
                    "similarity_score": 1 - results['distances'][0][i]  # Convert distance to similarity
                })
        
        return {
            "success": True,
            "documents": documents,
            "query": query
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def search_release_notes(query: str = "", top_k: int = 3, **kwargs) -> dict:
    """
    Tool: Semantic search over release notes
    Same concept as search_support_docs, but different data source
    """
    if release_collection is None:
        return {"success": False, "error": "Release notes collection not initialized"}
    
    try:
        results = release_collection.query(
            query_texts=[query],
            n_results=top_k
        )
        
        documents = []
        if results['documents'] and len(results['documents']) > 0:
            for i, doc in enumerate(results['documents'][0]):
                documents.append({
                    "content": doc,
                    "metadata": results['metadatas'][0][i] if results['metadatas'] else {},
                    "similarity_score": 1 - results['distances'][0][i]
                })
        
        return {
            "success": True,
            "documents": documents,
            "query": query
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

# ============================================================================
# TOOL REGISTRY
# This defines what tools are available to the LLM
# Similar to: Swagger/OpenAPI spec in Spring Boot
# ============================================================================

TOOLS = [
    {
        "name": "execute_sql",
        "description": "Execute a SQL query on the database. Use this for data retrieval. MUST CALL get_database_schema FIRST to understand the tables since they change per tenant! The query property must be the exact raw SQL SELECT query to run.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The exact SQL select query to execute (SELECT statements only)"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_database_schema",
        "description": "Get the database schema (tables, columns, types). Use this to understand what data is available before writing SQL queries.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "search_support_docs",
        "description": "Search support documentation for troubleshooting and error resolution. Use this when users ask about errors, issues, or how to fix problems.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query (natural language)"
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of documents to return (default: 3)",
                    "default": 3
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_release_notes",
        "description": "Search release notes for version information, features, bug fixes, and deprecations. Use this when users ask about releases, versions, or what's new.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query (natural language)"
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of documents to return (default: 3)",
                    "default": 3
                }
            },
            "required": ["query"]
        }
    }
]

# Map tool names to actual Python functions
TOOL_HANDLERS = {
    "execute_sql": execute_sql,
    "get_database_schema": get_database_schema,
    "search_support_docs": search_support_docs,
    "search_release_notes": search_release_notes
}

# ============================================================================
# JSON-RPC ENDPOINTS
# These implement the MCP protocol
# ============================================================================

@app.route('/mcp', methods=['POST'])
def mcp_handler():
    """
    Main MCP endpoint - handles all JSON-RPC requests
    
    JSON-RPC REQUEST FORMAT:
    {
        "jsonrpc": "2.0",
        "method": "tools/list" | "tools/call",
        "params": {...},
        "id": 1
    }
    
    RESPONSE FORMAT:
    {
        "jsonrpc": "2.0",
        "result": {...} | "error": {...},
        "id": 1
    }
    """
    data = request.json
    
    # Validate JSON-RPC format
    if 'jsonrpc' not in data or data['jsonrpc'] != '2.0':
        return jsonify({
            "jsonrpc": "2.0",
            "error": {
                "code": -32600,
                "message": "Invalid Request: missing jsonrpc version"
            },
            "id": data.get('id')
        }), 400
    
    method = data.get('method')
    params = data.get('params', {})
    request_id = data.get('id')
    
    # Handle different methods
    if method == 'tools/list':
        # Return list of available tools
        # LLM calls this first to discover what it can do
        return jsonify({
            "jsonrpc": "2.0",
            "result": {"tools": TOOLS},
            "id": request_id
        })
    
    elif method == 'tools/call':
        # Execute a specific tool
        tool_name = params.get('name')
        tool_args = params.get('arguments', {})
        
        if tool_name not in TOOL_HANDLERS:
            return jsonify({
                "jsonrpc": "2.0",
                "error": {
                    "code": -32601,
                    "message": f"Tool not found: {tool_name}"
                },
                "id": request_id
            }), 404
        
        # Execute the tool function
        # This is where the actual work happens!
        handler = TOOL_HANDLERS[tool_name]
        result = handler(**tool_args)
        
        return jsonify({
            "jsonrpc": "2.0",
            "result": result,
            "id": request_id
        })
    
    else:
        return jsonify({
            "jsonrpc": "2.0",
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}"
            },
            "id": request_id
        }), 404

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "MCP Server"})

# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 3001))
    print("=" * 60)
    print("MCP SERVER STARTING")
    print("=" * 60)
    print(f"Available tools: {list(TOOL_HANDLERS.keys())}")
    print(f"Endpoint: http://0.0.0.0:{port}/mcp")
    print(f"Protocol: JSON-RPC 2.0")
    print("=" * 60)
    app.run(host='0.0.0.0', port=port, debug=True)
