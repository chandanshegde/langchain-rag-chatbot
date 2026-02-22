from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import os
import logging
import time
import requests
import json
import threading
import queue
from collections import defaultdict
from typing import Dict, List, Any
import redis
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.callbacks.base import BaseCallbackHandler
try:
    from langchain.agents import initialize_agent, AgentType
except ImportError:
    from langchain_community.agent_toolkits.load_tools import load_tools
    from langchain.agents import AgentType, initialize_agent

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

class StreamingCallbackHandler(BaseCallbackHandler):
    def __init__(self, q):
        self.q = q

    def on_agent_action(self, action, **kwargs):
        # The 'log' attribute contains the LLM's full thought text leading up to the action
        thought_text = action.log.split("Action:")[0].replace("Thought:", "").strip()
        self.q.put({
            "type": "thought", 
            "tool": action.tool, 
            "tool_input": action.tool_input,
            "thought": thought_text
        })

    def on_tool_end(self, output, **kwargs):
        self.q.put({"type": "observation", "observation": str(output)})

def get_or_create_agent(tenant_id: str, mcp_url: str, callbacks=None):
    """
    Fetches the cached Agent for the tenant, or builds it dynamically if it doesn't exist.
    """
    if tenant_id in AGENT_CACHE:
        logging.info(f"Using cached agent for tenant: {tenant_id}")
        return AGENT_CACHE[tenant_id]

    logging.info(f"CACHE MISS for tenant: {tenant_id}. Creating new agent...")
    llm = ChatGoogleGenerativeAI(
        model="gemini-flash-latest",
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
        max_iterations=10,
        handle_parsing_errors=True,
        return_intermediate_steps=True
    )
    
    # We don't cache the agent with callbacks because callbacks are per-request
    if not callbacks:
        AGENT_CACHE[tenant_id] = agent
    return agent

def warm_up_agents():
    """
    Pre-initializes agents for all discovered tenants to avoid latency on the first query.
    """
    logging.info("Warming up agents for all tenants...")
    for tenant_id, mcp_url in TENANT_MCP_SERVERS.items():
        try:
            # Wait a few seconds for MCP servers to potentially finish booting (ChromaDB can be slow)
            logging.info(f"Pre-initializing agent for {tenant_id}...")
            get_or_create_agent(tenant_id, mcp_url)
            logging.info(f"Successfully warmed up agent for {tenant_id}")
        except Exception as e:
            logging.error(f"Failed to warm up agent for {tenant_id}: {e}")

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
    session_id = data.get('session_id', 'default_user_session')
    
    mcp_url = TENANT_MCP_SERVERS.get(tenant_id)
    if not mcp_url:
        return jsonify({"response": f"Error: Unknown tenant '{tenant_id}'."}), 400

    logging.info(f"[{tenant_id} | Session: {session_id}] Query received: {user_query}")
    
    def generate():
        q = queue.Queue()
        handler = StreamingCallbackHandler(q)
        
        # We need a fresh agent instance to attach the request-specific callback
        agent = get_or_create_agent(tenant_id, mcp_url, callbacks=[handler])
        
        history = get_session_memory(session_id)
        history_text = "\n".join([f"{msg['role']}: {msg['text']}" for msg in history])
        context_prompt = f"\n\nRecent Chat History with User:\n{history_text}\n" if history else ""

        system_prefix = (
            f"You are a helpful AI assistant connected to the Multi-Tenant Backend for '{tenant_id}'.\n"
            "You MUST follow the ReAct format precisely:\n"
            "Thought: <your reasoning>\n"
            "Action: <tool_name>\n"
            "Action Input: <tool_input>\n\n"
            "Once you have the final information, you MUST respond in this format:\n"
            "Final Answer: <your natural language response to the user>\n\n"
            "Tool Usage Rules:\n"
            "- If you don't know the versions, search for 'list all versions' first.\n"
            "- Always use 'get_database_schema' before running any SQL queries."
        )
        
        full_query = f"{system_prefix}{context_prompt}\n\nUser Question: {user_query}"

        def run_agent():
            try:
                # Add callback to the agent call
                result = agent.invoke({"input": full_query}, {"callbacks": [handler]})
                final_answer = result.get('output', '')
                q.put({"type": "final", "output": final_answer})
                
                # 4. Save to Redis Session Memory for context in next turn
                save_session_memory(session_id, [
                    {"role": "User", "text": user_query},
                    {"role": "AI", "text": final_answer}
                ])
            except Exception as e:
                logging.error(f"Agent error: {e}")
                q.put({"type": "error", "message": str(e)})
            finally:
                q.put(None)

        threading.Thread(target=run_agent).start()

        while True:
            item = q.get()
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "Central Orchestrator (LangChain Active)"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print("=" * 60)
    print("LANGCHAIN ORCHESTRATOR STARTING")
    print(f"Simulating Multi-Tenant routing. Port: {port}")
    print("=" * 60)
    
    # Pre-initialize agents before taking traffic
    warm_up_agents()
    
    # Disable debug mode in container to prevent reloader from wiping cache
    app.run(host='0.0.0.0', port=port, debug=False)
