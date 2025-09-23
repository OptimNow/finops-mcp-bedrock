import chainlit as cl
import os
import sys
import traceback as tb
from langchain.tools import StructuredTool
from src.tools.visual import titan_image_generate, render_vega_lite_png
from chainlit.mcp import McpConnection
from langchain_core.messages import (
    AIMessageChunk,
)
from langchain_core.runnables import RunnableConfig
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent
from loguru import logger
from mcp import ClientSession
from src.utils.bedrock import get_bedrock_client, get_chat_model
from src.utils.models import InferenceConfig, ModelId, ThinkingConfig
from typing import cast


logger.remove()
logger.add(sys.stderr, level=os.getenv('LOG_LEVEL', 'ERROR'))

bedrock_client = get_bedrock_client()
chat_model = get_chat_model(
    model_id=ModelId.ANTHROPIC_CLAUDE_3_5_SONNET,
    inference_config=InferenceConfig(temperature=0.3, max_tokens=2048),
    thinking_config=None,
    client=bedrock_client,
)


@cl.on_mcp_connect  # type: ignore
async def on_mcp(connection: McpConnection, session: ClientSession) -> None:
    """Called when an MCP connection is established."""
    await session.initialize()
    tools = await load_mcp_tools(session)
    # ---- Local tools (image gen + vega-lite renderer) ----
    tools += [
        StructuredTool.from_function(
            func=titan_image_generate,
            name="titan_image_generate",
            description=(
                "Generate an image with Amazon Titan Image Generator v2. "
                "Inputs: prompt (str), width (int, default 1024), height (int, default 1024), "
                "cfg_scale (float, default 7.5), steps (int, default 30), negative_prompt (str, optional). "
                "Returns a local PNG file path."
            )
        ),
        StructuredTool.from_function(
            func=render_vega_lite_png,
            name="render_vega_lite_png",
            description=(
                "Render a Vega-Lite spec (JSON object) to a PNG and return the file path. "
                "Use this for charts/graphs instead of image-generation models."
            )
        )
    ]
    agent = create_react_agent(
        chat_model,
        tools,
        prompt=(
           "You are a helpful Cloud FinOps assistant.\n"
           "- For image UNDERSTANDING: describe/answer directly from the user-provided image.\n"
           "- For image GENERATION (illustrations, thumbnails): call the tool titan_image_generate.\n"
           "- For CHARTS/GRAPHS: output a minimal Vega-Lite JSON spec and then call render_vega_lite_png with that spec.\n"
           "- For ARCHITECTURE/DIAGRAMS: output Markdown with a fenced code block using ```mermaid ... ```.\n"
           "Never ask the user to run tools manually; select and call them yourself."
               )
    )

    cl.user_session.set('agent', agent)
    cl.user_session.set('mcp_session', session)
    cl.user_session.set('mcp_tools', tools)


@cl.on_mcp_disconnect  # type: ignore
async def on_mcp_disconnect(name: str, session: ClientSession) -> None:
    """Called when an MCP connection is terminated."""
    if isinstance(cl.user_session.get('mcp_session'), ClientSession):
        await session.__aexit__(None, None, None)
        cl.user_session.set('mcp_session', None)
        cl.user_session.set('mcp_name', None)
        cl.user_session.set('mcp_tools', {})
        logger.debug(f'Disconnected from MCP server: {name}')


@cl.on_chat_start
async def on_chat_start():
    """Initialize the chat session."""
    cl.user_session.set('chat_messages', [])


@cl.on_message
async def on_message(message: cl.Message):
    """Process user messages and generate responses using the Bedrock model."""
    config = RunnableConfig(configurable={'thread_id': cl.context.session.id})
    agent = cast(CompiledStateGraph, cl.user_session.get('agent'))
    if not agent:
        await cl.Message(content='Error: Chat model not initialized.').send()
        return

    cb = cl.AsyncLangchainCallbackHandler()

    try:
        # Create a message for streaming
        response_message = cl.Message(content='')

        # Stream the response using the LangChain callback handler
        config['callbacks'] = [cb]
        async for msg, metadata in agent.astream(
            {'messages': message.content},
            stream_mode='messages',
            config=config,
        ):
            if isinstance(msg, AIMessageChunk) and msg.content:
                if isinstance(msg.content, str):
                    await response_message.stream_token(msg.content)
                elif (
                    isinstance(msg.content, list)
                    and len(msg.content) > 0
                    and isinstance(msg.content[0], dict)
                    and msg.content[0].get('type') == 'text'
                    and 'text' in msg.content[0]
                ):
                    await response_message.stream_token(msg.content[0]['text'])

        # --- NEW: check if response contains an outputs/*.png path ---
        text = response_message.content or ""
        if isinstance(text, str) and "outputs/" in text and text.strip().endswith(".png"):
            import os
            try:
                await cl.Image(
                    path=text.strip(),
                    name=os.path.basename(text.strip()),
                    display="inline"
                ).send()
            except Exception:
                pass

        # Send the complete message
        await response_message.send()

    except Exception as e:
        err_msg = cl.Message(content=f'Error: {str(e)}')
        await err_msg.send()
        logger.error(tb.format_exc())
