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
from src.utils.stream_handler import StreamHandler
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

    handler = StreamHandler()
    stream = None

    try:
        # Create the stream
        logger.debug(f'Creating stream for message: {message.content}')
        stream = agent.astream(
            {'messages': message.content}, stream_mode='messages', config=config
        )

        # Process messages from the stream
        async for msg, metadata in stream:
            # Debug print to see the raw message structure
            # print(f"Message received: {msg}")

            # Check for end turn in response metadata (only for non-string objects)
            if (
                not isinstance(msg, str)
                and hasattr(msg, 'response_metadata')
                and msg.response_metadata
            ):
                if msg.response_metadata.get('stopReason') == 'end_turn':
                    await handler.handle_end_turn()

            # Handle direct tool output (content is a string and name is present)
            if (
                not isinstance(msg, str)
                and hasattr(msg, 'content')
                and isinstance(msg.content, str)
                and hasattr(msg, 'name')
                and msg.name
            ):
                logger.debug(f'Tool output detected: {msg.content} from tool {msg.name}')

                # Find the index for this tool name
                tool_index = None
                for idx, name in handler.current_tool_names.items():
                    if name == msg.name:
                        tool_index = idx
                        break

                if tool_index is not None:
                    # Set the current index to the tool index
                    handler.current_index = tool_index
                    logger.debug(f'Setting current_index to {tool_index} for tool output')
                    await handler.handle_tool_output(msg.content)
                else:
                    logger.debug(f'Warning: Could not find index for tool {msg.name}')
                    # Fall back to current index
                    await handler.handle_tool_output(msg.content)
            # Handle string content (typically tool output without name)
            elif (
                not isinstance(msg, str)
                and hasattr(msg, 'content')
                and isinstance(msg.content, str)
            ):
                logger.debug(f'Tool output detected (no name): {msg.content}')
                await handler.handle_tool_output(msg.content)

            # Handle AIMessageChunks with structured content
            if (
                isinstance(msg, AIMessageChunk)
                and hasattr(msg, 'content')
                and isinstance(msg.content, list)
                and len(msg.content) > 0
                and isinstance(msg.content[0], dict)
            ):
                try:
                    content_item = msg.content[0]
                    content_type = content_item.get('type')
                    index = content_item.get('index')

                    # Handle index change if needed
                    if index is not None:
                        await handler.handle_index_change(index)

                    # Process different content types
                    if content_type == 'reasoning_content':
                        await handler.handle_reasoning_content(content_item)

                    elif content_type == 'text' and 'text' in content_item:
                        await handler.handle_text_content(index, content_item['text'])

                    elif content_type == 'tool_use':
                        # Store or retrieve the tool name
                        if 'name' in content_item and content_item['name']:
                            tool_name = content_item['name']
                            # Store the tool name for this index
                            handler.current_tool_names[index] = tool_name
                            logger.debug(f"Stored tool name '{tool_name}' for index {index}")
                        elif index in handler.current_tool_names:
                            # Use the previously stored tool name
                            tool_name = handler.current_tool_names[index]
                            logger.debug(f"Using stored tool name '{tool_name}' for index {index}")
                        else:
                            # Log the issue with the missing name key
                            logger.debug(
                                f"Warning: Tool use content item missing 'name' key and no stored name: {content_item}"
                            )
                            continue

                        # Handle tool input if present
                        if content_item.get('input'):
                            await handler.handle_tool_input(
                                index, tool_name, content_item['input']
                            )
                except KeyError as key_error:
                    logger.error(
                        f'KeyError processing content item: {key_error} in {msg.content[0]}'
                    )
                except Exception as inner_error:
                    logger.error(f'Error processing message content: {inner_error}')

    except GeneratorExit:
        # Properly handle generator exit (e.g., when client disconnects)
        logger.debug('Stream generator closed')
    except Exception as e:
        # Error handling
        err_msg = cl.Message(content=f'Error: {str(e)}')
        await err_msg.send()
        logger.error(tb.format_exc())
    finally:
        # Let GC handle the stream cleanup
        # No need to explicitly close as AsyncIterator doesn't have aclose
        if stream is not None:
            stream = None  # Release reference to help garbage collection
