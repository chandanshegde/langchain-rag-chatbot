from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import requests
import json
import logging
from collections import defaultdict
from typing import Dict, List, Any
import redis

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import initialize_agent, AgentType
from langchain.tools import Tool

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)

# Dynamically discover tenants from environment variables (e.g., TENANT_A_MCP_URL)
TENANT_MCP_SERVERS = {}
for key, value in os.environ.items():
    if key.startswith("TENANT_") and key.endswith("_MCP_URL"):
        tenant_id = key.replace("_MCP_URL", "").lower()
        TENANT_MCP_SERVERS[tenant_id] = value

# Default local mapping if no environment variables are detected
if not TENANT_MCP_SERVERS:
    TENANT_MCP_SERVERS = {
        "tenant_a": "http://localhost:3001/mcp",
        "tenant_b": "http://localhost:3002/mcp",
    }

logging.info(f"Orchestrator initialized with tenants: {list(TENANT_MCP_SERVERS.keys())}")

# Ensure API Key is bound
gemini_key = os.getenv("GEMINI_API_KEY")
if not gemini_key:
    logging.warning("No GEMINI_API_KEY provided! The LangChain Agent may fail.")

def call_mcp_tool(mcp_url: str, tool_name: str, arguments: dict):
    """
    Submits a JSON-RPC request to the target multi-tenant MCP server.
    """
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        },
        "id": 1
    }
    try:
        response = requests.post(mcp_url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

# Global caches securely storing Agents per tenant
AGENT_CACHE: Dict[str, Any] = {}

# Initialize Redis for Production-grade Session Management
try:
    REDIS_CLIENT = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
except:
    REDIS_CLIENT = None

def get_session_memory(session_id: str) -> List[Any]:
    if not REDIS_CLIENT: return []
    try:
        mem_str = REDIS_CLIENT.get(f"session:{session_id}")
        return json.loads(str(mem_str)) if mem_str else []
    except Exception as e:
        logging.error(f"Redis get error: {e}")
        return []

def save_session_memory(session_id: str, new_messages: List[Any]):
    if not REDIS_CLIENT: return
    try:
        current = get_session_memory(session_id)
        current.extend(new_messages)
        # Keep only the last 6 messages
        length = len(current)
        if length > 6:
            current = current[length-6:]
        REDIS_CLIENT.set(f"session:{session_id}", json.dumps(current), ex=86400) # Expire in 24h
    except Exception as e:
        logging.error(f"Redis set error: {e}")

def discover_mcp_tools(mcp_url: str):
    """
    Dynamically asks the MCP server for its capabilities via 'tools/list'.
    This means the orchestrator doesn't need to hardcode tool schemas!
    """
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/list",
        "params": {},
        "id": 1
    }
    try:
        response = requests.post(mcp_url, json=payload, timeout=10)
        mcp_tools_data = response.json().get("result", {}).get("tools", [])
        
        langchain_tools = []
        for mcp_tool in mcp_tools_data:
            tool_name = mcp_tool["name"]
            tool_desc = mcp_tool["description"]
            
            # Create a closure binding the specific tool name for LangChain
            def make_tool_func(name):
                def _func(arguments_str: str):
                    # Zero-Shot ReAct passes args usually as a single string. 
                    # If it's valid JSON, parse it, otherwise assign it to 'query' parameter
                    try:
                        args = json.loads(arguments_str) if arguments_str.strip().startswith("{") else {"query": arguments_str}
                    except:
                        args = {"query": arguments_str}
                        
                    return call_mcp_tool(mcp_url, name, args)
                return _func
                
            langchain_tools.append(Tool(
                name=tool_name,
                func=make_tool_func(tool_name),
                description=tool_desc
            ))
            
        logging.info(f"Discovered {len(langchain_tools)} tools from {mcp_url}")
        return langchain_tools
    except Exception as e:
        logging.error(f"Failed to discover tools: {e}")
        return []

def get_or_create_agent(tenant_id: str, mcp_url: str):
    """
    Fetches the cached Agent for the tenant, or builds it dynamically if it doesn't exist.
    """
    if tenant_id in AGENT_CACHE:
        return AGENT_CACHE[tenant_id]

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-pro",
        temperature=0,
        google_api_key=gemini_key
    )

    # Ask the specific tenant's MCP server what it is capable of
    tools = discover_mcp_tools(mcp_url)

    # Initialize a conversational zero-shot agent
    agent = initialize_agent(
        tools,
        llm,
        agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
        verbose=True,
        max_iterations=5,
        handle_parsing_errors=True,
        return_intermediate_steps=True
    )
    
    AGENT_CACHE[tenant_id] = agent
    return agent

@app.route('/chat', methods=['POST', 'OPTIONS'])
def chat():
    """
    The Orchestrator Endpoint
    Receives queries from the Frontend, determines the tenant context, 
    and uses the LangChain LLM to orchestrate calls to the tenant's MCP server.
    """
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    data = request.json
    user_query = data.get('query', '')
    tenant_id = data.get('tenant_id', 'tenant_a')
    session_id = data.get('session_id', 'default_user_session') # Capture User session
    
    mcp_url = TENANT_MCP_SERVERS.get(tenant_id)
    if not mcp_url:
        return jsonify({"response": f"Error: Unknown tenant '{tenant_id}'."}), 400

    logging.info(f"[{tenant_id} | Session: {session_id}] Query received: {user_query}")
    
    try:
        # 1. Grab or rebuild Agent specifically configured with the Tenant's MCP tools
        agent = get_or_create_agent(tenant_id, mcp_url)
        
        # 2. Extract recent chat history from Redis for context
        history = get_session_memory(session_id)
        history_text = "\n".join([f"{msg['role']}: {msg['text']}" for msg in history])
        context_prompt = f"\n\nRecent Chat History with User:\n{history_text}\n" if history else ""

        # 3. Formulate Prompt
        system_prefix = (
            f"You are a helpful AI assistant connected to the Multi-Tenant Backend for '{tenant_id}'. "
            "You have access to a database via the execute_sql tool, but remember the schema changes per tenant. "
            "Use get_database_schema to learn the schema before querying."
        )
        
        full_query = f"{system_prefix}{context_prompt}\n\nUser Question: {user_query}"
        
        # Execute the Langchain workflow (Reasoning -> Tool Call (RPC) -> Answer)
        result = agent.invoke({"input": full_query})
        
        final_answer = result.get('output', 'Sorry, I failed to generate an answer.')
        
        # Extract intermediate steps to show the LLM's "thoughts"
        thoughts = []
        if 'intermediate_steps' in result:
            for action, observation in result['intermediate_steps']:
                thoughts.append({
                    "tool": action.tool,
                    "tool_input": action.tool_input,
                    "observation": str(observation)[:200] + "..." if len(str(observation)) > 200 else observation
                })
        
        # 4. Save to Redis Session Memory
        save_session_memory(session_id, [
            {"role": "User", "text": user_query},
            {"role": "AI", "text": final_answer}
        ])
        
    except Exception as e:
        logging.error(f"LangChain orchestration failed: {e}")
        final_answer = f"Error communicating with LangChain / Gemini: {str(e)}"
        thoughts = []

    return jsonify({
        "response": final_answer,
        "thoughts": thoughts,
        "agent_used": f"LangChain Agent ({tenant_id})"
    })

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "Central Orchestrator (LangChain Active)"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print("=" * 60)
    print("LANGCHAIN ORCHESTRATOR STARTING")
    print(f"Simulating Multi-Tenant routing. Port: {port}")
    print("=" * 60)
    app.run(host='0.0.0.0', port=port, debug=True)
