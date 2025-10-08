"""Streaming utilities for LangGraph agent responses."""

from typing import AsyncGenerator
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph


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
    
    # Track if we've seen the final output
    final_output_received = False
    
    # Stream agent response
    async for event in agent.astream_events(
        {"messages": chat_messages},
        config=config,
        version="v2"
    ):
        kind = event.get("event")
        
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
                                yield text
                # Handle string format
                elif isinstance(chunk_content, str) and chunk_content:
                    yield chunk_content
        
        # Capture final output with complete message history
        elif kind == "on_chain_end" and not final_output_received:
            output = event.get("data", {}).get("output", {})
            if isinstance(output, dict) and "messages" in output:
                # Replace chat history with the complete history from agent
                # This includes all AIMessages, ToolMessages, etc.
                new_messages = output["messages"]
                if new_messages and len(new_messages) > len(chat_messages):
                    # Clear and update with complete history
                    chat_messages.clear()
                    chat_messages.extend(new_messages)
                    final_output_received = True
