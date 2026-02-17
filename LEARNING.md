# Understanding the RAG System - A Developer's Guide

*Written for Java/Spring Boot developers learning Python, LangChain, and RAG concepts*

---

## Table of Contents

1. [MCP Server: What It Actually Does](#mcp-server)
2. [Vector Embeddings: The Math Behind RAG](#vector-embeddings)
3. [LangChain: Orchestrating LLM Calls](#langchain)
4. [ChromaDB: Vector Storage](#chromadb)
5. [Python Concepts for Java Developers](#python-for-java)
6. [Svelte: Component-Based UI](#svelte)

---

## MCP Server: What It Actually Does {#mcp-server}

### The Confusion

When you first hear "MCP Server" and "natural language," it's natural to think the server parses human language into commands. It doesn't. That would be nuts—you'd be reimplementing an LLM.

### What Actually Happens

The MCP server is a function library with a standard interface. Think Spring Boot `@RestController`, but using JSON-RPC instead of REST, and designed specifically for LLMs to call.

**The flow:**
1. User types: "Show me failed tasks from last week"
2. LLM (Gemini/GPT) does the NLP parsing
3. LLM decides: "This needs the execute_sql tool"
4. LLM generates: `execute_sql(query="SELECT * FROM tasks WHERE status='failed' AND start_time > DATE('now', '-7 days')")`
5. LLM sends JSON-RPC request to MCP server
6. MCP server executes the Python function
7. MCP server returns results
8. LLM formats results into human-readable response

The MCP server never sees "Show me failed tasks." It only sees structured function calls with typed arguments.

### Why JSON-RPC?

REST would work too, but JSON-RPC is a better fit for function calling:

**REST:**
```http
POST /api/sql/execute
Content-Type: application/json

{"query": "SELECT * FROM tasks"}
```

**JSON-RPC:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "execute_sql",
    "arguments": {"query": "SELECT * FROM tasks"}
  }
}
```

JSON-RPC includes:
- Standard error codes (-32600 = Invalid Request, -32601 = Method not found)
- Request/response matching via `id`
- Method introspection (`tools/list` to discover available functions)
- Batch requests support

### Tool Schemas = OpenAPI for LLMs

When you expose a REST API, you might write an OpenAPI spec so clients know what endpoints exist and what parameters they expect.

MCP tools work the same way:

```python
{
    "name": "execute_sql",
    "description": "Execute a SQL query on the database",  # LLM reads this
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The SQL SELECT query"
            }
        },
        "required": ["query"]
    }
}
```

The LLM reads this schema and learns:
- When to use this tool (based on description)
- What arguments it needs
- What types those arguments should be

It's like Swagger/OpenAPI, but the "client" is an LLM that can generate the correct function calls from natural language.

### The Separation of Concerns

```
┌─────────────────────┐
│   User's Brain      │  "I want to see failed tasks"
└──────────┬──────────┘
           │ Natural language
┌──────────▼──────────┐
│   LLM (Gemini)      │  Understands intent, knows available tools
│   Does: NLP         │  Generates: function_name(args)
└──────────┬──────────┘
           │ Structured function call (JSON-RPC)
┌──────────▼──────────┐
│   MCP Server        │  Just executes functions
│   Does: Execute     │  No intelligence, just business logic
└──────────┬──────────┘
           │ Results (JSON)
┌──────────▼──────────┐
│   LLM (Gemini)      │  Formats results for human
│   Does: Synthesis   │  Generates: "Here are 3 failed tasks..."
└─────────────────────┘
```

This is why you can swap LLMs (Gemini → GPT → Claude) without touching the MCP server. The MCP server doesn't care about language; it only executes typed function calls.

---

## Vector Embeddings: The Math Behind RAG {#vector-embeddings}

### The Problem RAG Solves

Traditional search sucks at meaning:
- "connection timeout" doesn't match "connection fails" (no shared keywords)
- "OOM error" doesn't match "out of memory" (acronym vs full phrase)
- "my deploy is stuck" doesn't match "deployment hanging" (different words, same meaning)

Vector embeddings solve this by converting text into numbers that capture meaning, not just keywords.

### How Embeddings Work

An embedding model is a neural network trained to convert text → vector (array of numbers).

**Example with text-embedding-004 (768 dimensions):**

```python
text = "Connection timeout error"
vector = embedding_model(text)
# Result: [0.234, -0.567, 0.123, ..., 0.891]
#         ↑ 768 numbers total
```

**Why 768 numbers?**

Each dimension captures some aspect of meaning. This isn't interpretable (dimension 42 doesn't mean "networking"), but collectively, these 768 numbers encode semantic information.

### Similarity via Math

The magic: texts with similar meanings get similar vectors.

```python
v1 = embed("connection timeout")     # [0.23, 0.45, 0.12, ...]
v2 = embed("connection fails")       # [0.25, 0.43, 0.14, ...]  ← Similar!
v3 = embed("out of memory")          # [0.78, -0.12, 0.56, ...] ← Different!
```

To measure similarity, we use cosine similarity:

```python
def cosine_similarity(v1, v2):
    dot_product = sum(a * b for a, b in zip(v1, v2))
    magnitude1 = sqrt(sum(a * a for a in v1))
    magnitude2 = sqrt(sum(b * b for b in v2))
    return dot_product / (magnitude1 * magnitude2)

# Result: 0.0 to 1.0 (higher = more similar)
similarity(v1, v2)  # 0.92 (very similar)
similarity(v1, v3)  # 0.23 (not similar)
```

### The RAG Process

**Ingestion (happens once):**

```python
# Step 1: Split documents into chunks
doc = "Connection timeout usually occurs when firewall blocks port 443..."
chunks = split_into_chunks(doc, chunk_size=500)

# Step 2: Convert each chunk to vector
for chunk in chunks:
    vector = embedding_model(chunk)
    chromadb.add(id="doc1_chunk1", vector=vector, text=chunk)
```

**Query (happens every search):**

```python
# Step 1: User query → vector
query = "why does my connection fail?"
query_vector = embedding_model(query)

# Step 2: Find similar vectors in database
results = chromadb.search(query_vector, top_k=3)
# Returns: 3 chunks with highest cosine similarity

# Step 3: LLM reads those chunks and generates answer
context = "\n\n".join([r.text for r in results])
answer = llm(f"Context: {context}\n\nQuestion: {query}")
```

### Why This Works

Embedding models are trained on billions of text pairs. They learn that:
- "timeout" and "hangs" often appear in similar contexts
- "connection" and "network" are related concepts
- "error" and "fails" indicate problems

So even though "connection timeout" and "network hangs" share no keywords, their embeddings are close in vector space.

### The Limitations

Embeddings aren't magic:
- They capture statistical patterns, not understanding
- They fail on very domain-specific jargon (unless the model was trained on it)
- They don't do well with negation ("not a timeout" vs "timeout")
- They need decent chunk sizes (too small = no context, too large = too much noise)

---

## LangChain: Orchestrating LLM Calls {#langchain}

### What LangChain Actually Is

LangChain is a library for chaining LLM calls together. That's it.

You could build this yourself:
```python
# Without LangChain
prompt = f"Given this context: {context}\n\nAnswer: {query}"
response = openai.ChatCompletion.create(messages=[{"role": "user", "content": prompt}])
```

But LangChain provides:
- Prompt templates (less string formatting)
- Chains (sequence multiple LLM calls)
- Agents (LLM decides which tool to call)
- Memory (conversation history)
- Integrations (works with 50+ LLM providers)

### The Key Concepts

**1. Prompts**

```python
# Without LangChain
prompt = f"You are a SQL expert. Generate a query for: {user_input}"

# With LangChain
from langchain.prompts import ChatPromptTemplate

template = ChatPromptTemplate.from_messages([
    ("system", "You are a SQL expert. Generate queries for user requests."),
    ("user", "{user_input}")
])
prompt = template.format(user_input="show me failed tasks")
```

Why use templates? Reusability and type safety.

**2. Chains**

A chain is multiple steps executed in sequence:

```python
from langchain.chains import LLMChain

# Define chain
chain = (
    template  # Step 1: Format prompt
    | llm     # Step 2: Call LLM
    | parser  # Step 3: Parse output
)

# Execute
result = chain.invoke({"user_input": "show failed tasks"})
```

In Java terms, this is function composition:
```java
Function<Input, String> chain = 
    input -> parser.apply(llm.apply(template.apply(input)));
```

**3. Agents**

An agent is an LLM that decides which tool to call:

```python
# You give agent a list of tools
tools = [execute_sql, search_docs, get_schema]

# Agent decides which to use based on query
agent = create_agent(llm, tools)
result = agent.invoke("show me failed tasks")

# Internally, agent does:
# 1. LLM reads tool descriptions
# 2. LLM decides: "I need execute_sql"
# 3. LLM generates: execute_sql(query="SELECT...")
# 4. Agent executes tool
# 5. LLM formats result
```

This is the "orchestration" part of our RAG system. The orchestrator is a LangChain agent that routes queries to the right specialized agent (SQL, Support, or Release).

### When to Use LangChain

**Use it when:**
- You're chaining multiple LLM calls
- You need conversation memory
- You want to swap LLM providers easily
- You're building agents that use tools

**Don't use it when:**
- You're making a single LLM call (just use the API directly)
- You need fine-grained control over prompts
- You're building something production-critical (LangChain moves fast, breaking changes happen)

For our portfolio project, we use LangChain for:
- Agent orchestration (routing queries to specialized agents)
- Prompt templates (cleaner than string formatting)
- MCP client integration (calling tools)

---

## ChromaDB: Vector Storage {#chromadb}

### What It Does

ChromaDB is a database for vectors. Instead of SQL tables with rows/columns, you store:
- **Vectors**: Arrays of numbers (embeddings)
- **Metadata**: Key-value pairs about the document
- **Text**: Original text (for retrieval)

### The Data Model

```python
chromadb.add(
    ids=["doc1", "doc2"],
    embeddings=[[0.1, 0.2, ...], [0.3, 0.4, ...]],  # The vectors
    documents=["Connection timeout error...", "Out of memory..."],  # Original text
    metadatas=[{"type": "support", "date": "2024-01-15"}, {...}]  # Extra info
)
```

In SQL terms, this is like:
```sql
CREATE TABLE vectors (
    id TEXT PRIMARY KEY,
    embedding FLOAT[],  -- Not actually supported in SQL!
    document TEXT,
    metadata JSON
);
```

But SQL can't efficiently search vectors. You can't do `WHERE embedding SIMILAR TO [0.1, 0.2, ...]`.

### How Vector Search Works

When you query:
```python
results = chromadb.query(
    query_embeddings=[[0.23, 0.45, ...]],
    n_results=3
)
```

ChromaDB uses an approximate nearest neighbor (ANN) algorithm called HNSW (Hierarchical Navigable Small World).

**Why approximate?**

Exact nearest neighbor search is slow: you'd compare your query vector to every single vector in the database. For 100,000 documents, that's 100,000 comparisons.

HNSW builds a graph structure where similar vectors are linked. It traverses the graph to find approximate nearest neighbors in milliseconds instead of seconds.

**The trade-off:**
- Exact search: 100% accurate, O(n) time
- HNSW: ~95-99% accurate, O(log n) time

For RAG, this is fine. Getting the 3rd-best document instead of the exact 3rd-best doesn't matter much.

### Collections

ChromaDB organizes vectors into collections (like SQL tables):

```python
support_docs = chroma.get_or_create_collection("support_docs")
release_notes = chroma.get_or_create_collection("release_notes")

support_docs.add(...)  # Add to support collection
release_notes.add(...) # Add to release collection
```

Collections are isolated: searching one doesn't search the other.

### Persistence

ChromaDB can run in-memory or persist to disk:

```python
# In-memory (data lost on restart)
chroma = chromadb.Client()

# Persistent (data saved to disk)
chroma = chromadb.PersistentClient(path="./chroma_db")
```

For our project, we use persistent storage so embeddings survive restarts. Generating embeddings costs API calls ($), so you don't want to re-embed on every startup.

---

## Python Concepts for Java Developers {#python-for-java}

### Type Hints (Java's Types)

Python is dynamically typed, but you can add type hints:

```python
# Without types (valid Python)
def execute_sql(query):
    return cursor.execute(query)

# With types (better)
def execute_sql(query: str) -> dict:
    return cursor.execute(query)
```

Java equivalent:
```java
public Map<String, Object> executeSql(String query) {
    return cursor.execute(query);
}
```

Type hints don't enforce types at runtime (Python doesn't care), but they help IDEs and linters catch errors.

### **kwargs (Java's Method Overloading)

Python uses `**kwargs` for variable keyword arguments:

```python
def create_user(name: str, **kwargs):
    email = kwargs.get('email')
    age = kwargs.get('age')
```

Java equivalent:
```java
// You'd use method overloading
public void createUser(String name) { ... }
public void createUser(String name, String email) { ... }
public void createUser(String name, String email, int age) { ... }
```

Python just uses one method with optional arguments.

### Decorators (Java's Annotations)

Python decorators are like Java annotations:

```python
@app.route('/api/health')  # Flask decorator
def health():
    return {"status": "ok"}
```

Java equivalent:
```java
@GetMapping("/api/health")  // Spring annotation
public Map<String, String> health() {
    return Map.of("status", "ok");
}
```

Decorators wrap functions to add behavior (logging, authentication, routing).

### Context Managers (Java's try-with-resources)

```python
# Python
with open('file.txt') as f:
    data = f.read()
# File automatically closed

# Java
try (FileReader f = new FileReader("file.txt")) {
    // Read file
}  // File automatically closed
```

`with` in Python = `try-with-resources` in Java.

### List Comprehensions (Java Streams)

```python
# Python
numbers = [1, 2, 3, 4, 5]
doubled = [n * 2 for n in numbers if n > 2]
# Result: [6, 8, 10]

# Java
List<Integer> numbers = List.of(1, 2, 3, 4, 5);
List<Integer> doubled = numbers.stream()
    .filter(n -> n > 2)
    .map(n -> n * 2)
    .collect(Collectors.toList());
```

Python list comprehensions are more concise, but they're conceptually the same as Java streams.

### None (Java's null)

```python
# Python
result = None  # No value

if result is None:  # Check for None
    print("No result")
```

Java equivalent:
```java
Result result = null;

if (result == null) {
    System.out.println("No result");
}
```

One difference: Python uses `is None` instead of `== None`. `is` checks identity (same object), `==` checks equality (same value).

### Dictionaries (Java's HashMap)

```python
# Python
user = {"name": "John", "age": 30}
print(user["name"])  # "John"
user["email"] = "john@example.com"  # Add key
```

Java equivalent:
```java
Map<String, Object> user = new HashMap<>();
user.put("name", "John");
user.put("age", 30);
System.out.println(user.get("name"));
```

Python dicts are more convenient (no explicit type declarations), but they're the same concept.

---

## Svelte: Component-Based UI {#svelte}

### What Makes Svelte Different

React/Vue: Runtime frameworks (ship framework code to browser)
Svelte: Compile-time framework (compiles to vanilla JS, no framework runtime)

**React:**
```jsx
function Counter() {
  const [count, setCount] = useState(0);
  return <button onClick={() => setCount(count + 1)}>{count}</button>;
}
```

**Svelte:**
```svelte
<script>
  let count = 0;
</script>

<button on:click={() => count++}>{count}</button>
```

Svelte is simpler: no `useState` hook, no JSX, just regular JavaScript.

### Component Structure

A Svelte component is a single `.svelte` file with three sections:

```svelte
<script>
  // JavaScript logic
  let name = "World";
  function greet() {
    alert(`Hello ${name}!`);
  }
</script>

<style>
  /* CSS scoped to this component */
  button {
    background: blue;
    color: white;
  }
</style>

<!-- HTML template -->
<button on:click={greet}>
  Hello {name}!
</button>
```

Think of it like JSP/Thymeleaf, but with reactive data binding built in.

### Reactivity

Svelte automatically updates the DOM when variables change:

```svelte
<script>
  let count = 0;
  
  // count++ triggers DOM update automatically
</script>

<p>Count: {count}</p>
<button on:click={() => count++}>Increment</button>
```

React equivalent (more verbose):
```jsx
const [count, setCount] = useState(0);
// Must call setCount() to trigger update
<button onClick={() => setCount(count + 1)}>Increment</button>
```

### Props (Component Inputs)

```svelte
<!-- ChatMessage.svelte -->
<script>
  export let message;  // "export" makes it a prop
  export let sender;
</script>

<div class="message">
  <strong>{sender}:</strong> {message}
</div>
```

Usage:
```svelte
<ChatMessage sender="Alice" message="Hello!" />
```

Java equivalent: method parameters
```java
public void renderMessage(String sender, String message) { ... }
```

### Events (Component Outputs)

```svelte
<!-- Button.svelte -->
<script>
  import { createEventDispatcher } from 'svelte';
  const dispatch = createEventDispatcher();
  
  function handleClick() {
    dispatch('click', { detail: 'Button clicked' });
  }
</script>

<button on:click={handleClick}>Click me</button>
```

Usage:
```svelte
<Button on:click={handleButtonClick} />
```

This is like Java interfaces/callbacks:
```java
button.setOnClickListener(event -> handleButtonClick(event));
```

### Why We Chose Svelte

1. **Simplicity**: Less boilerplate than React
2. **No build complexity**: Vite handles everything
3. **Small bundle size**: No runtime framework
4. **Easy to understand**: Looks like HTML/CSS/JS, not JSX

For a portfolio project, readability matters. Hiring managers can understand Svelte code even if they don't know Svelte.

---

## Summary: How It All Fits Together

```
User: "Show me failed tasks from last week"
  ↓
Frontend (Svelte): 
  - POST /chat with query
  ↓
Backend (Flask): 
  - Receives query
  - Calls Orchestrator (LangChain)
  ↓
Orchestrator:
  - Uses LLM to classify intent
  - Decides: "This is an analytics query"
  - Routes to SQL Agent
  ↓
SQL Agent:
  - Uses LLM to generate SQL query
  - Calls MCP tool: execute_sql(query="SELECT...")
  ↓
MCP Server:
  - Executes function (no NLP, just execution)
  - Queries SQLite database
  - Returns results as JSON
  ↓
SQL Agent:
  - Receives results
  - Uses LLM to format into human-readable text
  ↓
Backend:
  - Streams response to frontend
  ↓
Frontend:
  - Displays response in chat
  - Shows routing info: "Used SQL Agent (95% confidence)"
```

Every piece has a clear job:
- **MCP Server**: Function execution
- **ChromaDB**: Vector storage and similarity search
- **LangChain**: LLM orchestration
- **LLM (Gemini)**: NLP and text generation
- **Flask**: HTTP server
- **Svelte**: UI rendering

This separation makes the system testable, maintainable, and easy to understand.

---

*Last updated: 2026-02-13*
