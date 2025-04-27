import chainlit as cl
import os
import sys
import traceback as tb
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
    model_id=ModelId.ANTHROPIC_CLAUDE_3_7_SONNET,
    inference_config=InferenceConfig(temperature=1, max_tokens=4096 * 8),
    thinking_config=ThinkingConfig(budget_tokens=1024),
    client=bedrock_client,
)


@cl.on_mcp_connect  # type: ignore
async def on_mcp(connection: McpConnection, session: ClientSession) -> None:
    """Called when an MCP connection is established."""
    await session.initialize()
    tools = await load_mcp_tools(session)
    agent = create_react_agent(
        chat_model,
        tools,
        prompt="You are a helpful assistant. You must use the tools provided to you to answer the user's question.",
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
        # Update the config to include callbacks
        config['callbacks'] = [cb]
        async for msg, metadata in agent.astream(
            {'messages': message.content},
            stream_mode='messages',
            config=config,
        ):
            # Handle AIMessageChunks with text content for streaming
            if isinstance(msg, AIMessageChunk) and msg.content:
                # If content is a string, stream it directly
                if isinstance(msg.content, str):
                    await response_message.stream_token(msg.content)
                # If content is a list with dictionaries that have text
                elif (
                    isinstance(msg.content, list)
                    and len(msg.content) > 0
                    and isinstance(msg.content[0], dict)
                    and msg.content[0].get('type') == 'text'
                    and 'text' in msg.content[0]
                ):
                    await response_message.stream_token(msg.content[0]['text'])

        # Send the complete message
        await response_message.send()

    except Exception as e:
        # Error handling
        err_msg = cl.Message(content=f'Error: {str(e)}')
        await err_msg.send()
        logger.error(tb.format_exc())
