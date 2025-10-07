from dotenv import load_dotenv
load_dotenv()

import asyncio
import json
import os
import chainlit as cl
from loguru import logger
from typing import cast
from langchain.tools import StructuredTool
from langchain_core.messages import AIMessageChunk
from langchain_core.runnables import RunnableConfig
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent
from mcp import ClientSession

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

# Global MCP connection management
_mcp_tools = []
_mcp_ready = False
_mcp_task = None


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


async def initialize_mcp_background():
    """Initialize MCP connection in background."""
    global _mcp_tools, _mcp_ready
    
    try:
        logger.info("🔌 Initializing MCP connection in background...")
        from mcp import StdioServerParameters
        from mcp.client.stdio import stdio_client
        
        server_params = StdioServerParameters(
            command="uvx",
            args=["--from", "awslabs-cost-explorer-mcp-server", "awslabs.cost-explorer-mcp-server"],
            env={"AWS_REGION": os.getenv("AWS_REGION", "us-east-1")}
        )
        
        async with asyncio.timeout(60):
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    _mcp_tools = await load_mcp_tools(session)
                    _mcp_ready = True
                    
                    logger.info(f"✅ MCP ready! Loaded {len(_mcp_tools)} tools")
                    for tool in _mcp_tools:
                        logger.info(f"  - {tool.name}")
                    
                    # Keep session alive
                    await asyncio.Event().wait()
        
    except asyncio.TimeoutError:
        logger.error("❌ MCP initialization timed out")
        _mcp_ready = False
    except Exception as e:
        logger.exception("❌ MCP initialization failed")
        _mcp_ready = False


@cl.on_chat_start
async def on_chat_start():
    global _mcp_task
    
    cl.user_session.set("chat_messages", [])
    
    # Start MCP initialization in background if not started
    if _mcp_task is None:
        _mcp_task = asyncio.create_task(initialize_mcp_background())
        logger.info("⏳ MCP initialization started in background...")
    
    # Use whatever tools are available
    current_tools = base_tools() + _mcp_tools
    agent = build_agent(current_tools)
    cl.user_session.set("agent", agent)
    
    # Send welcome message
    if _mcp_ready:
        message = f"👋 Welcome to the **OptimNow FinOps Assistant**!\n\n✅ Connected to AWS Billing MCP with {len(_mcp_tools)} tools."
    elif _mcp_task.done():
        message = "👋 Welcome to the **OptimNow FinOps Assistant**!\n\n⚠️ MCP connection failed. Running with basic tools only."
    else:
        message = "👋 Welcome to the **OptimNow FinOps Assistant**!\n\n⏳ Connecting to AWS Billing MCP... Cost queries will be available shortly."
    
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
