from dotenv import load_dotenv
load_dotenv()  # loads AWS keys and other vars from .env

import os
import sys
import chainlit as cl
from loguru import logger
from typing import cast

from langchain.tools import StructuredTool
from langchain_core.messages import AIMessageChunk
from langchain_core.runnables import RunnableConfig
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent

from chainlit.mcp import McpConnection
# Explicitly enable MCP support (sometimes needed in custom apps)
cl.enable_mcp = True
from mcp import ClientSession

from src.tools.visual import titan_image_generate, render_vega_lite_png
from src.utils.bedrock import get_bedrock_client, get_chat_model
from src.utils.models import InferenceConfig, ModelId


# ----------------- Logging -----------------
logger.remove()
logger.add(sys.stderr, level=os.getenv("LOG_LEVEL", "DEBUG"))

# ----------------- Bedrock Client -----------------
bedrock_client = get_bedrock_client()
chat_model = get_chat_model(
    model_id=ModelId.ANTHROPIC_CLAUDE_3_5_SONNET,
    inference_config=InferenceConfig(temperature=0.3, max_tokens=2048),
    thinking_config=None,
    client=bedrock_client,
)


# ----------------- Helper -----------------
def build_agent(tools):
    """Create a React agent with given tools."""
    return create_react_agent(
        chat_model,
        tools,
        prompt=(
            "You are a helpful Cloud FinOps assistant.\n"
            "- For IMAGE GENERATION: use titan_image_generate.\n"
            "- For CHARTS/GRAPHS: use render_vega_lite_png.\n"
            "- For DIAGRAMS: output mermaid Markdown.\n"
            "Never ask the user to run tools manually."
        ),
    )


def base_tools():
    """Always-available local tools."""
    return [
        StructuredTool.from_function(
            func=titan_image_generate,
            name="titan_image_generate",
            description="Generate an image with Amazon Titan Image Generator v2.",
        ),
        StructuredTool.from_function(
            func=render_vega_lite_png,
            name="render_vega_lite_png",
            description="Render a Vega-Lite spec (JSON object) to a PNG file.",
        ),
    ]


# ----------------- Chat Lifecycle -----------------
@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("chat_messages", [])
    logger.info("🔌 MCP JSON loaded from .chainlit/mcp.json")

    # Initialize with base tools only
    agent = build_agent(base_tools())
    cl.user_session.set("agent", agent)

    await cl.Message(
        content="👋 Welcome to the **OptimNow FinOps Assistant**!"
    ).send()


@cl.on_mcp_connect  # type: ignore
async def on_mcp(connection: McpConnection, session: ClientSession) -> None:
    """Called when an MCP connection is established."""
    try:
        logger.debug("🚀 MCP connection established")
        await session.initialize()
        tools = await load_mcp_tools(session)

        if not tools:
            logger.error("No MCP tools loaded from session.")
        else:
            logger.info(f"Loaded {len(tools)} MCP tools.")

        # Add local tools too
        tools += base_tools()

        # Rebuild agent with MCP tools
        agent = build_agent(tools)
        cl.user_session.set("agent", agent)
        cl.user_session.set("mcp_session", session)
        cl.user_session.set("mcp_tools", tools)

    except Exception as e:
        logger.exception("Failed to initialize MCP session")
        await cl.Message(content=f"❌ MCP connection failed: {str(e)}").send()


@cl.on_mcp_disconnect  # type: ignore
async def on_mcp_disconnect(name: str, session: ClientSession) -> None:
    """Called when an MCP connection is terminated."""
    if isinstance(cl.user_session.get("mcp_session"), ClientSession):
        logger.debug(f"🔌 MCP disconnected: {name}")
        await session.__aexit__(None, None, None)
        cl.user_session.set("mcp_session", None)
        cl.user_session.set("mcp_name", None)
        cl.user_session.set("mcp_tools", {})


@cl.on_message
async def on_message(message: cl.Message):
    """Process user messages and generate responses using the Bedrock model."""
    config = RunnableConfig(configurable={"thread_id": cl.context.session.id})
    agent = cast(CompiledStateGraph, cl.user_session.get("agent"))

    if not agent:
        await cl.Message(content="❌ Error: Chat model not initialized.").send()
        return

    cb = cl.AsyncLangchainCallbackHandler()

    try:
        response_message = cl.Message(content="")
        config["callbacks"] = [cb]

        async for msg, metadata in agent.astream(
            {"messages": message.content},
            stream_mode="messages",
            config=config,
        ):
            if isinstance(msg, AIMessageChunk) and msg.content:
                if isinstance(msg.content, str):
                    await response_message.stream_token(msg.content)
                elif (
                    isinstance(msg.content, list)
                    and len(msg.content) > 0
                    and isinstance(msg.content[0], dict)
                    and msg.content[0].get("type") == "text"
                    and "text" in msg.content[0]
                ):
                    await response_message.stream_token(msg.content[0]["text"])

        text = response_message.content or ""

        # Handle images
        if isinstance(text, str) and text.strip().endswith(".png") and "outputs/" in text:
            if os.path.exists(text.strip()):
                await cl.Image(
                    path=text.strip(),
                    name=os.path.basename(text.strip()),
                    display="inline",
                ).send()
            else:
                await cl.Message(content=f"⚠️ Could not find generated image at {text.strip()}").send()
        else:
            if text.strip():
                await response_message.send()

    except Exception as e:
        import traceback as tb
        await cl.Message(content=f"❌ Error: {str(e)}\n{tb.format_exc()}").send()
