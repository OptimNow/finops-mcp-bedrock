from dotenv import load_dotenv
load_dotenv()

import asyncio
import json
import os
import chainlit as cl
from loguru import logger
from typing import cast
from langchain.tools import StructuredTool
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from src.utils.mcp_tools_wrapper import wrap_mcp_tools

ENABLE_MCP = os.getenv("CHAINLIT_ENABLE_MCP", "true").lower() == "true"
cl.enable_mcp = True

# Debug MCP configuration
logger.info("=" * 50)
logger.info("MCP CONFIGURATION DEBUG")
logger.info("=" * 50)
mcp_config_env = os.getenv('CHAINLIT_MCP_CONFIG')
logger.info(f"CHAINLIT_MCP_CONFIG env: {mcp_config_env}")

if mcp_config_env and os.path.exists(mcp_config_env):
    with open(mcp_config_env) as f:
        mcp_json = json.load(f)
        logger.info(f"MCP JSON content: {json.dumps(mcp_json, indent=2)}")
else:
    logger.error(f"MCP config file not found or env var not set!")

logger.info(f"Chainlit enable_mcp: {getattr(cl, 'enable_mcp', 'not set')}")
logger.info("=" * 50)

from src.tools.visual import titan_image_generate, render_vega_lite_png
from src.utils.bedrock import get_chat_model
from src.utils.models import ModelId
from src.utils.stream import stream_to_chainlit

# ============================================================================
# Global MCP state
# ============================================================================
_mcp_tools = []
_mcp_ready = False
_mcp_connections = []


async def initialize_mcp():
    """
    Initialize MCP tools from all servers defined in CHAINLIT_MCP_CONFIG.
    Creates a separate session for each MCP server and keeps connections alive.
    """
    global _mcp_tools, _mcp_ready, _mcp_connections

    if _mcp_ready:
        logger.info("MCP already initialized, skipping...")
        return

    if not ENABLE_MCP:
        logger.info("MCP is disabled via configuration. Skipping MCP initialization.")
        _mcp_tools = []
        _mcp_ready = False
        return

    logger.info("=" * 60)
    logger.info("🔌 Initializing MCP servers...")
    logger.info("=" * 60)

    mcp_config_path = os.getenv("CHAINLIT_MCP_CONFIG", ".chainlit/mcp.json")
    logger.info(f"Using MCP config file: {mcp_config_path}")

    try:
        with open(mcp_config_path, "r") as f:
            mcp_config = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load MCP config from {mcp_config_path}: {e}")
        _mcp_tools = []
        _mcp_ready = False
        return

    servers = mcp_config.get("mcpServers", {})
    if not servers:
        logger.warning("No 'mcpServers' section found in MCP config.")
        _mcp_tools = []
        _mcp_ready = False
        return

    all_tools = []

    for server_name, server_cfg in servers.items():
        command = server_cfg.get("command")
        args = server_cfg.get("args", [])
        env = server_cfg.get("env", {})

        logger.info(f"📡 Loading MCP server '{server_name}'...")
        logger.info(f"   Command: {command}")
        logger.info(f"   Args: {args}")

        if not command:
            logger.warning(f"Skipping '{server_name}' - missing 'command'")
            continue

        try:
            server_params = StdioServerParameters(
                command=command,
                args=args,
                env=env
            )
            
            client_context = stdio_client(server_params)
            read, write = await client_context.__aenter__()
            
            session_context = ClientSession(read, write)
            session = await session_context.__aenter__()
            await session.initialize()
            
            server_tools = await load_mcp_tools(session)

            _mcp_connections.append({
                'name': server_name,
                'client_context': client_context,
                'session_context': session_context,
                'session': session,
                'tools': server_tools
            })

            logger.info(f"✅ Server '{server_name}' loaded with {len(server_tools)} tools:")
            for tool in server_tools:
                logger.info(f"   - {tool.name}")
            
            all_tools.extend(server_tools)

        except Exception as e:
            logger.error(f"❌ Failed to load server '{server_name}': {str(e)}")
            logger.exception("Full error:")

    _mcp_tools = all_tools
    _mcp_ready = len(all_tools) > 0

    logger.info("=" * 60)
    logger.info(f"✅ MCP initialization complete!")
    logger.info(f"   Total servers attempted: {len(servers)}")
    logger.info(f"   Total servers connected: {len(_mcp_connections)}")
    logger.info(f"   Total tools loaded: {len(_mcp_tools)}")
    logger.info("=" * 60)

    if not _mcp_ready:
        logger.warning("⚠️  No MCP tools loaded successfully")


async def cleanup_mcp():
    """Clean up MCP connections on shutdown."""
    global _mcp_connections
    
    logger.info("🔌 Cleaning up MCP connections...")
    
    for connection in _mcp_connections:
        try:
            server_name = connection['name']
            await connection['session_context'].__aexit__(None, None, None)
            await connection['client_context'].__aexit__(None, None, None)
            logger.info(f"✅ Closed connection to '{server_name}'")
        except Exception as e:
            logger.error(f"❌ Error closing '{server_name}': {e}")
    
    _mcp_connections.clear()


def base_tools():
    """Return base visual tools."""
    return [
        StructuredTool.from_function(
            func=titan_image_generate,
            name="generate_image",
            description="Generate an image using Amazon Titan Image Generator based on a text prompt"
        ),
        StructuredTool.from_function(
            func=render_vega_lite_png,
            name="render_chart",
            description="Render a Vega-Lite JSON spec as a PNG image for visualization"
        ),
    ]


def build_agent(tools: list) -> CompiledStateGraph:
    """Build the LangGraph agent with provided tools and system prompt."""
    
    system_prompt = """You are the OptimNow FinOps Agent, an AWS cost optimization expert.

## Behavior Rules
- Be direct and concise - NO apologies, NO excessive politeness
- If a tool fails, try an alternative approach or report the issue briefly
- Never say "I apologize" or "I'm sorry" - just state facts and move forward
- Always remember the conversation context
- Present data in clear tables rather than long texts withh bullet points

## Tool Strategy

**AWS API (call_aws)** - Real-time infrastructure data:
- describe-instances, describe-volumes, list resources
- Fast response (< 1s)

**Cost Explorer** - Historical billing data:
- get_cost_and_usage, get_cost_forecast
- Data has 24-48h latency
- If cost data unavailable, proceed with what you have

**render_chart** - Create visualizations:
- Input: Vega-Lite JSON specification
- Always use complete, valid Vega-Lite specs
- Include: $schema, data, mark, encoding
- Use appropriate chart types: bar (comparisons), line (trends), pie (proportions)

## Chart Examples

For cost by service (bar chart):
```json
{
  "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
  "width": 400,
  "height": 300,
  "title": "AWS Costs by Service",
  "data": {"values": [{"service": "EC2", "cost": 150}, {"service": "RDS", "cost": 80}]},
  "mark": "bar",
  "encoding": {
    "x": {"field": "service", "type": "nominal", "title": "Service"},
    "y": {"field": "cost", "type": "quantitative", "title": "Cost ($)"},
    "color": {"field": "service", "type": "nominal", "legend": null}
  }
}
```

For cost trend over time (line chart):
```json
{
  "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
  "width": 500,
  "height": 300,
  "title": "Cost Trend",
  "data": {"values": [{"date": "2024-01", "cost": 100}, {"date": "2024-02", "cost": 120}]},
  "mark": {"type": "line", "point": true},
  "encoding": {
    "x": {"field": "date", "type": "temporal", "title": "Date"},
    "y": {"field": "cost", "type": "quantitative", "title": "Cost ($)"}
  }
}
```

## Response Style
- Start with action, not preamble
- If something fails, say "Could not retrieve X. Proceeding with available data."
- Never apologize - just fix or explain briefly
- End with clear next steps or recommendations

## Workflow
1. For inventory: Query AWS API, present in table
2. For costs: Use Cost Explorer with date range
3. For charts: Build proper Vega-Lite spec with real data
4. For modifications: Explain, wait for confirmation, execute, confirm completion"""
    def add_system_prompt(state):
        """Add system prompt to the state."""
        return [SystemMessage(content=system_prompt)] + state["messages"]
    
    model = get_chat_model(model_id=ModelId.ANTHROPIC_CLAUDE_3_5_SONNET_US.value)
    return create_react_agent(
        model, 
        tools,
        state_modifier=add_system_prompt
    )


def build_welcome_message(current_tools, mcp_tools, mcp_ready: bool) -> str:
    """Build a dynamic welcome message based on loaded tools."""
    lines = []
    lines.append("👋 Welcome to the **OptimNow FinOps Assistant**!")
    lines.append("")

    if not mcp_ready or not mcp_tools:
        lines.append("⚠️ MCP connection is not available. Running with local tools only.")
        lines.append("")
        lines.append("You can still ask questions, but AWS billing data access is limited.")
        return "\n".join(lines)

    mcp_tool_names = sorted({getattr(t, "name", str(t)) for t in mcp_tools})
    all_tool_names = sorted({getattr(t, "name", str(t)) for t in current_tools})
    local_tool_names = sorted(set(all_tool_names) - set(mcp_tool_names))

    lines.append("✅ MCP connection established.")
    lines.append(f"Loaded {len(mcp_tools)} MCP tools and {len(local_tool_names)} local tools.")
    lines.append("")

    lines.append("**MCP tools available:**")
    for name in mcp_tool_names:
        lines.append(f"- {name}")
    lines.append("")

    if local_tool_names:
        lines.append("**Local tools available:**")
        for name in local_tool_names:
            lines.append(f"- {name}")
        lines.append("")

    lines.append("You can now ask questions about your AWS costs and billing!")
    return "\n".join(lines)


@cl.on_chat_start
async def on_chat_start():
    """Initialize the chat session."""
    cl.user_session.set("chat_messages", [])

    await initialize_mcp()

    wrapped_mcp_tools = wrap_mcp_tools(_mcp_tools) if _mcp_tools else []
    
    current_tools = base_tools() + wrapped_mcp_tools
    logger.info(f"Building agent with {len(current_tools)} total tools ({len(_mcp_tools)} from MCP)")

    agent = build_agent(current_tools)
    cl.user_session.set("agent", agent)

    message = build_welcome_message(current_tools, _mcp_tools, _mcp_ready)
    await cl.Message(content=message).send()


@cl.on_message
async def on_message(message: cl.Message):
    """Handle incoming messages."""
    agent = cast(CompiledStateGraph, cl.user_session.get("agent"))
    chat_messages = cl.user_session.get("chat_messages", [])
    
    # Add the user message to history
    user_msg = HumanMessage(content=message.content)
    chat_messages.append(user_msg)
    
    msg = cl.Message(content="")
    await msg.send()
    
    config = RunnableConfig(
        callbacks=[cl.LangchainCallbackHandler()],
        recursion_limit=50,
        configurable={
            "thread_id": "default"
        }
    )
    
    # Collect the full response
    full_response = ""
    
    try:
        async for chunk in stream_to_chainlit(agent, message.content, chat_messages[:-1], config):
            full_response += chunk
            await msg.stream_token(chunk)
    except Exception as e:
        logger.exception("Error during agent execution")
        error_msg = f"\n\n❌ Error: {str(e)}"
        full_response += error_msg
        await msg.stream_token(error_msg)
    
    await msg.update()
    
    # Add the assistant response to history
    if full_response:
        assistant_msg = AIMessage(content=full_response)
        chat_messages.append(assistant_msg)
        cl.user_session.set("chat_messages", chat_messages)
        logger.info(f"💾 Chat history updated. Total messages: {len(chat_messages)}")


@cl.on_chat_end
async def on_chat_end():
    """Chat session ended."""
    logger.info("Chat session ended - MCP connections remain active for reuse")
