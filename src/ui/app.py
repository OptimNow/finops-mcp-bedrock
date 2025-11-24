from dotenv import load_dotenv
load_dotenv()

import asyncio
import json
import os
import chainlit as cl
from loguru import logger
from typing import cast
from langchain.tools import StructuredTool
from langchain_core.runnables import RunnableConfig
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

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
# Global MCP state - DÉCLARATION UNIQUE ICI
# ============================================================================
_mcp_tools = []
_mcp_ready = False
_mcp_connections = []  # Liste pour stocker les connexions actives


async def initialize_mcp():
    """
    Initialize MCP tools from all servers defined in CHAINLIT_MCP_CONFIG.
    Creates a separate session for each MCP server and keeps connections alive.
    """
    global _mcp_tools, _mcp_ready, _mcp_connections

    # If already initialized, skip
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

    # Load MCP configuration file
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

    # Load each MCP server
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
            # Create server parameters
            server_params = StdioServerParameters(
                command=command,
                args=args,
                env=env
            )
            
            # Create MCP client connection
            client_context = stdio_client(server_params)
            read, write = await client_context.__aenter__()
            
            # Create and initialize session
            session_context = ClientSession(read, write)
            session = await session_context.__aenter__()
            await session.initialize()
            
            # Load tools from this session
            server_tools = await load_mcp_tools(session)

            # Store connection to keep it alive (IMPORTANT!)
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
    """Build the LangGraph agent with provided tools."""
    model = get_chat_model(model_id=ModelId.ANTHROPIC_CLAUDE_3_5_SONNET)
    return create_react_agent(model, tools)


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

    # MCP is ready - show available tools
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
    cl.user_session.set("chat_messages", [])

    # Initialize MCP on first connection
    await initialize_mcp()

    # Build agent with all available tools
    current_tools = base_tools() + _mcp_tools
    logger.info(f"Building agent with {len(current_tools)} total tools ({len(_mcp_tools)} from MCP)")

    agent = build_agent(current_tools)
    cl.user_session.set("agent", agent)

    # Send dynamic welcome message
    message = build_welcome_message(current_tools, _mcp_tools, _mcp_ready)
    await cl.Message(content=message).send()


@cl.on_message
async def on_message(message: cl.Message):
    agent = cast(CompiledStateGraph, cl.user_session.get("agent"))
    chat_messages = cl.user_session.get("chat_messages", [])
    
    msg = cl.Message(content="")
    await msg.send()
    
    config = RunnableConfig(callbacks=[cl.LangchainCallbackHandler()])
    
    try:
        async for chunk in stream_to_chainlit(agent, message.content, chat_messages, config):
            await msg.stream_token(chunk)
    except Exception as e:
        logger.exception("Error during agent execution")
        await msg.stream_token(f"\n\n❌ Error: {str(e)}")
    
    await msg.update()


@cl.on_chat_end
async def on_chat_end():
    """Clean up MCP connections when chat ends."""
    await cleanup_mcp()
