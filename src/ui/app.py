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

# Global MCP connection - initialize once at startup
_mcp_client_context = None
_mcp_session_context = None
_mcp_session = None
_mcp_tools = []
_mcp_ready = False


async def initialize_mcp():
    """Initialize MCP connection once at startup."""
    global _mcp_client_context, _mcp_session_context, _mcp_session, _mcp_tools, _mcp_ready
    
    if _mcp_session is not None:
        return  # Already initialized
    
    try:
        logger.info("🔌 Initializing MCP connection...")
        
        server_params = StdioServerParameters(
            command="uvx",
            args=["--from", "awslabs-cost-explorer-mcp-server", "awslabs.cost-explorer-mcp-server"],
            env={"AWS_REGION": os.getenv("AWS_REGION", "us-east-1")}
        )
        
        # Create and enter context managers
        _mcp_client_context = stdio_client(server_params)
        read, write = await _mcp_client_context.__aenter__()
        
        _mcp_session_context = ClientSession(read, write)
        _mcp_session = await _mcp_session_context.__aenter__()
        
        await _mcp_session.initialize()
        _mcp_tools = await load_mcp_tools(_mcp_session)
        _mcp_ready = True
        
        logger.info(f"✅ MCP ready! Loaded {len(_mcp_tools)} tools")
        for tool in _mcp_tools:
            logger.info(f"  - {tool.name}")
            
    except Exception as e:
        logger.exception("❌ MCP initialization failed")
        _mcp_ready = False


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
    
    # Send welcome message
    if _mcp_ready:
        message = f"👋 Welcome to the **OptimNow FinOps Assistant**!\n\n✅ Connected to AWS Billing MCP with {len(_mcp_tools)} tools.\n\nYou can now ask questions about your AWS costs!"
    else:
        message = "👋 Welcome to the **OptimNow FinOps Assistant**!\n\n⚠️ MCP connection failed. Running with visualization tools only."
    
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
