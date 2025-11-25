"""
Streaming utilities for agent responses to Chainlit.
"""
from typing import AsyncGenerator, List
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph.state import CompiledStateGraph
from langchain_core.runnables import RunnableConfig
from loguru import logger


async def stream_to_chainlit(
    agent: CompiledStateGraph,
    user_message: str,
    chat_messages: List[BaseMessage],
    config: RunnableConfig
) -> AsyncGenerator[str, None]:
    """
    Stream agent responses to Chainlit with improved text extraction.
    
    Args:
        agent: The compiled agent graph
        user_message: User's input message
        chat_messages: Previous chat history
        config: Runnable configuration
        
    Yields:
        Text chunks to be streamed to Chainlit
    """
    logger.info(f"🔄 Starting agent stream for message: {user_message[:50]}...")
    
    token_count = 0
    final_output_received = False
    last_message = None
    
    # Build input
    input_messages = chat_messages + [HumanMessage(content=user_message)]
    
    try:
        async for event in agent.astream_events(
            {"messages": input_messages},
            config=config,
            version="v2"
        ):
            kind = event.get("event")
            logger.debug(f"Event: {kind}")
            
            # Handle token streaming
            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk", {})
                
                # Extract content from chunk
                content = None
                if hasattr(chunk, 'content'):
                    content = chunk.content
                elif isinstance(chunk, dict):
                    content = chunk.get('content')
                
                # Handle different content formats
                if content:
                    # If content is a list of blocks (Claude's format)
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text = block.get("text", "")
                                if text:
                                    token_count += 1
                                    if token_count % 50 == 0:
                                        logger.debug(f"📝 Streamed {token_count} tokens so far...")
                                    yield text
                    # If content is a simple string
                    elif isinstance(content, str):
                        token_count += 1
                        if token_count % 50 == 0:
                            logger.debug(f"📝 Streamed {token_count} tokens so far...")
                        yield content
            
            # Track final output
            elif kind == "on_chain_end":
                final_output_received = True
                output = event.get("data", {}).get("output", {})
                logger.info(f"Chain ended, final_output_received={final_output_received}")
                logger.info(f"Output type: {type(output)}, has messages: {hasattr(output, 'get') and 'messages' in output if isinstance(output, dict) else 'N/A'}")
                
                # Extract final message if available
                if isinstance(output, dict) and "messages" in output:
                    messages = output["messages"]
                    if messages and len(messages) > 0:
                        last_msg = messages[-1]
                        if isinstance(last_msg, AIMessage):
                            last_message = last_msg
                            logger.info(f"✅ Got final AI message: {str(last_msg.content)[:200]}...")
        
        # CRITICAL: If no tokens were streamed but we have a final message, yield it now
        if token_count == 0 and last_message and last_message.content:
            logger.warning(f"⚠️ No tokens streamed but final message exists ({len(str(last_message.content))} chars), yielding now...")
            
            # Extract text from content
            if isinstance(last_message.content, str):
                yield last_message.content
            elif isinstance(last_message.content, list):
                # Handle list of content blocks
                for block in last_message.content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        yield block.get("text", "")
                    elif isinstance(block, str):
                        yield block
        
        logger.info(f"✅ Stream complete. Total tokens: {token_count}, Final output received: {final_output_received}")
        
    except Exception as e:
        logger.exception(f"❌ Error during streaming: {str(e)}")
        yield f"\n\n❌ Error: {str(e)}"
