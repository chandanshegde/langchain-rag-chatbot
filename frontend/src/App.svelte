<script>
  import ChatWindow from "./lib/ChatWindow.svelte";
  import ChatInput from "./lib/ChatInput.svelte";

  function generateSessionId() {
    return "session_" + Math.random().toString(36).substring(2, 9);
  }

  const initialId = generateSessionId();
  let isLoading = $state(false);
  let activeTenant = $state("tenant_a");
  let sessions = $state({ [initialId]: [] });
  let sessionIds = $state([initialId]);
  let sessionId = $state(initialId);

  let messages = $derived(sessions[sessionId] || []);

  function startNewSession() {
    const newId = generateSessionId();
    sessions[newId] = [];
    sessionIds = [...sessionIds, newId];
    sessionId = newId;
  }

  async function handleSendMessage(event) {
    const userText = event.detail.text;

    // Add user message to UI
    sessions[sessionId] = [
      ...sessions[sessionId],
      { text: userText, sender: "user" },
    ];
    isLoading = true;

    let botMsgIndex = -1;

    try {
      const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:5000";
      const response = await fetch(`${apiUrl}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: userText,
          tenant_id: activeTenant,
          session_id: sessionId,
        }),
      });

      if (!response.ok) throw new Error("Network response error");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop(); // Keep partial line in buffer

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6));

              // Only create the bot bubble when we actually have content or a step
              if (botMsgIndex === -1) {
                botMsgIndex = sessions[sessionId].length;
                sessions[sessionId] = [
                  ...sessions[sessionId],
                  {
                    text: "",
                    sender: "bot",
                    thoughts: [],
                    agentInfo: "LangChain Agent",
                  },
                ];
              }

              const currentMessages = [...sessions[sessionId]];
              const msg = currentMessages[botMsgIndex];

              if (data.type === "thought") {
                msg.thoughts = [
                  ...msg.thoughts,
                  {
                    tool: data.tool,
                    tool_input: data.tool_input,
                    thought: data.thought,
                    observation: "Thinking...",
                  },
                ];
              } else if (data.type === "observation") {
                if (msg.thoughts.length > 0) {
                  msg.thoughts[msg.thoughts.length - 1].observation =
                    data.observation;
                }
              } else if (data.type === "final") {
                msg.text = data.output;
              } else if (data.type === "error") {
                msg.text = "Error: " + data.message;
              }

              sessions[sessionId] = currentMessages;
            } catch (e) {
              console.error("Parse error", e);
            }
          }
        }
      }
    } catch (e) {
      console.error(e);
      if (botMsgIndex === -1) {
        sessions[sessionId] = [
          ...sessions[sessionId],
          {
            text: `Error: ${e.message}`,
            sender: "bot",
            thoughts: [],
            agentInfo: "System",
          },
        ];
      } else {
        sessions[sessionId][botMsgIndex].text = `Error: ${e.message}`;
      }
    } finally {
      isLoading = false;
    }
  }
</script>

<main>
  <div class="chat-container">
    <header>
      <div class="logo">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path
            d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"
          ></path>
          <polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline>
          <line x1="12" y1="22.08" x2="12" y2="12"></line>
        </svg>
      </div>
      <div class="title-info">
        <h1>RAG Multi-Tenant SaaS</h1>
        <span class="status"><span class="dot"></span> Orchestrator Linked</span
        >
      </div>

      <div class="tenant-selector">
        <label for="tenant">Context:</label>
        <select id="tenant" bind:value={activeTenant}>
          <option value="tenant_a">Tenant A (Silo)</option>
          <option value="tenant_b">Tenant B (Silo)</option>
        </select>

        <div class="session-actions">
          <select class="session-select" bind:value={sessionId}>
            {#each sessionIds as sid}
              <option value={sid}>Session #{sid.slice(-6)}</option>
            {/each}
          </select>
          <button class="new-session" onclick={startNewSession}>New</button>
        </div>
      </div>
    </header>

    <ChatWindow {messages} {isLoading} />
    <ChatInput onsubmit={handleSendMessage} {isLoading} />
  </div>
</main>

<style>
  main {
    width: 100%;
    max-width: 900px;
    height: 85vh;
    margin: auto;
  }

  .chat-container {
    background: var(--bg-secondary);
    border-radius: 16px;
    border: 1px solid var(--border-color);
    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
    backdrop-filter: blur(20px);
  }

  header {
    padding: 16px 24px;
    border-bottom: 1px solid var(--border-color);
    display: flex;
    align-items: center;
    gap: 16px;
    background: rgba(15, 17, 26, 0.4);
  }

  .logo {
    width: 40px;
    height: 40px;
    background: linear-gradient(135deg, var(--accent), #8b5cf6);
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    box-shadow: 0 4px 10px rgba(99, 102, 241, 0.3);
  }

  .title-info {
    display: flex;
    flex-direction: column;
  }

  h1 {
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--text-primary);
  }

  .status {
    font-size: 0.8rem;
    color: var(--text-secondary);
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .tenant-selector {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.85rem;
  }

  .tenant-selector select {
    background: rgba(30, 41, 59, 0.8);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
    padding: 6px 12px;
    border-radius: 8px;
    outline: none;
    cursor: pointer;
  }

  .session-actions {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-left: 12px;
    padding-left: 12px;
    border-left: 1px solid var(--border-color);
  }

  .session-select {
    background: rgba(30, 41, 59, 0.8);
    color: var(--text-secondary);
    border: 1px solid var(--border-color);
    padding: 4px 8px;
    border-radius: 6px;
    outline: none;
    cursor: pointer;
    font-size: 0.75rem;
    font-family: monospace;
  }

  .new-session {
    background: transparent;
    border: 1px solid var(--accent);
    color: var(--accent);
    padding: 4px 10px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.75rem;
    transition: all 0.2s;
  }

  .new-session:hover {
    background: var(--accent);
    color: white;
  }

  .dot {
    width: 8px;
    height: 8px;
    background: #10b981;
    border-radius: 50%;
    display: inline-block;
    box-shadow: 0 0 5px #10b981;
  }
</style>
