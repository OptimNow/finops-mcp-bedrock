"""Streaming utilities for LangGraph agent responses."""

from typing import AsyncGenerator
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from loguru import logger


async def stream_to_chainlit(
    agent: CompiledStateGraph,
    user_message: str,
    chat_messages: list,
    config: RunnableConfig
) -> AsyncGenerator[str, None]:
    """
    Stream agent responses to Chainlit.
    
    Args:
        agent: The compiled LangGraph agent
        user_message: The user's input message
        chat_messages: History of chat messages
        config: Runnable config with callbacks
    
    Yields:
        str: Tokens from the agent's response
    """
    # Add user message to history
    chat_messages.append(HumanMessage(content=user_message))
    
    logger.info(f"🔄 Starting agent stream for message: {user_message[:50]}...")
    
    # Track if we've seen the final output
    final_output_received = False
    token_count = 0
    
    # Stream agent response
    async for event in agent.astream_events(
        {"messages": chat_messages},
        config=config,
        version="v2"
    ):
        kind = event.get("event")
        logger.debug(f"Event: {kind}")
        
        # Stream text tokens
        if kind == "on_chat_model_stream":
            content = event.get("data", {}).get("chunk", {})
            
            if hasattr(content, "content"):
                chunk_content = content.content
                
                # Handle list format
                if isinstance(chunk_content, list):
                    for item in chunk_content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            text = item.get("text", "")
                            if text:
                                token_count += 1
                                yield text
                # Handle string format
                elif isinstance(chunk_content, str) and chunk_content:
                    token_count += 1
                    yield chunk_content
        
        # Capture final output with complete message history
        elif kind == "on_chain_end":
            logger.info(f"Chain ended, final_output_received={final_output_received}")
            if not final_output_received:
                output = event.get("data", {}).get("output", {})
                logger.info(f"Output type: {type(output)}, has messages: {'messages' in output if isinstance(output, dict) else 'N/A'}")
                
                if isinstance(output, dict) and "messages" in output:
                    # Replace chat history with the complete history from agent
                    new_messages = output["messages"]
                    if new_messages and len(new_messages) > len(chat_messages):
                        # Get the last AI message
                        last_message = new_messages[-1]
                        if isinstance(last_message, AIMessage):
                            logger.info(f"✅ Got final AI message: {last_message.content[:100]}...")
                            
                            # If no tokens were streamed, yield the complete message now
                            if token_count == 0 and last_message.content:
                                logger.warning("⚠️ No tokens streamed, yielding complete message")
                                yield last_message.content
                        
                        # Update chat history
                        chat_messages.clear()
                        chat_messages.extend(new_messages)
                        final_output_received = True
    
    logger.info(f"✅ Stream complete. Total tokens: {token_count}, Final output received: {final_output_received}")
