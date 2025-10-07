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
    
    # Stream agent response
    async for event in agent.astream_events(
        {"messages": chat_messages},
        config=config,
        version="v2"
    ):
        # Extract text chunks from the stream
        kind = event.get("event")
        
        if kind == "on_chat_model_stream":
            content = event.get("data", {}).get("chunk", {})
            if hasattr(content, "content") and content.content:
                yield content.content
        
        elif kind == "on_chain_end":
            # Get final message
            output = event.get("data", {}).get("output", {})
            if isinstance(output, dict) and "messages" in output:
                messages = output["messages"]
                if messages:
                    last_message = messages[-1]
                    if isinstance(last_message, AIMessage):
                        # Add final message to history
                        chat_messages.append(last_message)
