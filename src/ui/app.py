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

# Global MCP connections - we now support multiple servers
_mcp_connections = {}  # Dict to store multiple server connections
_mcp_tools = []
_mcp_ready = False


async def load_mcp_server(server_name: str, server_config: dict) -> list:
    """
    Load a single MCP server and return its tools.
    
    Args:
        server_name: Name of the MCP server (e.g., 'aws-billing')
        server_config: Configuration dict with 'command', 'args', 'env'
    
    Returns:
        List of tools from this server
    """
    try:
        logger.info(f"📡 Loading MCP server '{server_name}'...")
        logger.info(f"   Command: {server_config['command']}")
        logger.info(f"   Args: {server_config['args']}")
        
        # Create server parameters
        server_params = StdioServerParameters(
            command=server_config['command'],
            args=server_config['args'],
            env=server_config.get('env', {})
        )
        
        # Create and enter context managers
        client_context = stdio_client(server_params)
        read, write = await client_context.__aenter__()
        
        session_context = ClientSession(read, write)
        session = await session_context.__aenter__()
        
        # Initialize session
        await session.initialize()
        
        # Load tools from this server
        tools = await load_mcp_tools(session)
        
        # Store connection info for cleanup later
        _mcp_connections[server_name] = {
            'client_context': client_context,
            'session_context': session_context,
            'session': session,
            'tools': tools
        }
        
        logger.info(f"✅ Server '{server_name}' loaded with {len(tools)} tools:")
        for tool in tools:
            logger.info(f"   - {tool.name}")
        
        return tools
        
    except Exception as e:
        logger.error(f"❌ Failed to load server '{server_name}': {str(e)}")
        logger.exception("Full error:")
        return []


async def initialize_mcp():
    """Initialize all MCP servers from config file."""
    global _mcp_tools, _mcp_ready
    
    # Check if already initialized
    if _mcp_connections:
        logger.info("MCP already initialized, skipping...")
        return
    
    try:
        logger.info("=" * 60)
        logger.info("🔌 Initializing MCP servers...")
        logger.info("=" * 60)
        
        # Load MCP configuration
        mcp_config_path = os.getenv('CHAINLIT_MCP_CONFIG', '.chainlit/mcp.json')
        
        if not os.path.exists(mcp_config_path):
            logger.error(f"❌ MCP config file not found: {mcp_config_path}")
            _mcp_ready = False
            return
        
        with open(mcp_config_path) as f:
            mcp_config = json.load(f)
        
        servers = mcp_config.get('mcpServers', {})
        logger.info(f"Found {len(servers)} MCP server(s) in config")
        
        # Load each server
        all_tools = []
        for server_name, server_config in servers.items():
            tools = await load_mcp_server(server_name, server_config)
            all_tools.extend(tools)
        
        _mcp_tools = all_tools
        _mcp_ready = len(all_tools) > 0
        
        logger.info("=" * 60)
        logger.info(f"✅ MCP initialization complete!")
        logger.info(f"   Total servers: {len(_mcp_connections)}")
        logger.info(f"   Total tools: {len(_mcp_tools)}")
        logger.info("=" * 60)
        
        if not _mcp_ready:
            logger.warning("⚠️  No MCP tools loaded successfully")
            
    except Exception as e:
        logger.exception("❌ MCP initialization failed")
        _mcp_ready = False


async def cleanup_mcp():
    """Clean up all MCP connections on shutdown."""
    logger.info("🔌 Cleaning up MCP connections...")
    
    for server_name, connection in _mcp_connections.items():
        try:
            # Exit context managers in reverse order
            await connection['session_context'].__aexit__(None, None, None)
            await connection['client_context'].__aexit__(None, None, None)
            logger.info(f"✅ Closed connection to '{server_name}'")
        except Exception as e:
            logger.error(f"❌ Error closing '{server_name}': {e}")
    
    _mcp_connections.clear()

async def initialize_mcp():
    """
    Initialize MCP tools from all servers defined in the CHAINLIT_MCP_CONFIG (.chainlit/mcp.json).

    This version loads ALL servers declared under "mcpServers" (e.g. aws-billing, aws-api),
    instead of only one.
    """
    global _mcp_tools, _mcp_ready

    # If already initialized, do nothing
    if _mcp_ready:
        return

    if not ENABLE_MCP:
        logger.info("MCP is disabled via configuration. Skipping MCP initialization.")
        _mcp_tools = []
        _mcp_ready = False
        return

    logger.info("🔌 Initializing MCP connection...")

    # 1) Lire le chemin de config MCP
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
        logger.warning("No 'mcpServers' section found in MCP config. No MCP tools will be loaded.")
        _mcp_tools = []
        _mcp_ready = False
        return

    all_tools = []

    # 2) Boucler sur TOUS les serveurs MCP
    for server_name, server_cfg in servers.items():
        command = server_cfg.get("command")
        args = server_cfg.get("args", [])
        env = server_cfg.get("env", {})
        transport = server_cfg.get("transport", "stdio")  # défaut raisonnable

        logger.info(
            f"Loading MCP server '{server_name}' with command '{command}' and args {args}"
        )

        if not command:
            logger.warning(
                f"Skipping MCP server '{server_name}' because 'command' is missing."
            )
            continue

        try:
            # Import du bon module
            from langchain_mcp_adapters.tools import load_mcp_tools

            # Construire la "Connection" attendue par langchain_mcp_adapters
            connection = {
                "transport": transport,
                "command": command,
                "args": args,
            }
            if env:
                connection["env"] = env

            # On laisse load_mcp_tools créer la session à partir de connection
            server_tools = await load_mcp_tools(
                session=None,
                connection=connection,
                server_name=server_name,
            )

            logger.info(
                f"Loaded {len(server_tools)} tools from MCP server '{server_name}'"
            )
            all_tools.extend(server_tools)

        except Exception as e:
            logger.error(f"Error loading MCP server '{server_name}': {e}")

    _mcp_tools = all_tools
    _mcp_ready = True if _mcp_tools else False

    logger.info(f"✅ MCP ready! Loaded {len(_mcp_tools)} tools from {len(servers)} server(s)")

    # Log détaillé des tools chargés
    if not _mcp_tools:
        logger.warning("No MCP tools loaded successfully.")
        return

    logger.info("MCP tools loaded (name | first 80 chars of description):")
    for t in _mcp_tools:
        name = getattr(t, "name", str(t))
        desc = getattr(t, "description", "") or ""
        logger.info(f"  - {name} | {desc[:80]}")



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
    """
    Build a dynamic welcome message based on the tools that are actually loaded.
    - current_tools: all tools available to the agent (local + MCP)
    - mcp_tools: only the tools coming from MCP servers
    - mcp_ready: whether MCP initialization succeeded
    """
    lines = []
    lines.append("Welcome to the **OptimNow FinOps Assistant**!")
    lines.append("")

    if not mcp_ready or not mcp_tools:
        # MCP not available or no MCP tools loaded
        lines.append("⚠️ MCP connection is not available. Running with local tools only.")
        lines.append("")
        lines.append("You can still ask questions, but resource level actions and live billing data may be limited.")
        return "\n".join(lines)

    # MCP is ready
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

    lines.append("You can now ask questions about your AWS costs,")
    lines.append("and run safe FinOps automation workflows like EBS gp2→gp3 optimization.")
    return "\n".join(lines)


@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("chat_messages", [])

    # Initialize MCP on first connection
    await initialize_mcp()

    # Build agent with all available tools
    current_tools = base_tools() + _mcp_tools
    logger.info(
        f"Building agent with {len(current_tools)} total tools ({len(_mcp_tools)} from MCP)"
    )

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
