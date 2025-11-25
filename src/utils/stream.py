"""
Streaming utilities for agent responses to Chainlit with token counting.
"""
from typing import AsyncGenerator, List
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph.state import CompiledStateGraph
from langchain_core.runnables import RunnableConfig
from loguru import logger

# Approximate pricing for Claude 3.5 Sonnet (us-east-1)
# Input: $0.003 per 1K tokens, Output: $0.015 per 1K tokens
PRICE_INPUT_PER_1K = 0.003
PRICE_OUTPUT_PER_1K = 0.015


async def stream_to_chainlit(
    agent: CompiledStateGraph,
    user_message: str,
    chat_messages: List[BaseMessage],
    config: RunnableConfig
) -> AsyncGenerator[str, None]:
    """
    Stream agent responses to Chainlit with token counting.
    
    Args:
        agent: The compiled agent graph
        user_message: User's input message
        chat_messages: Previous chat history
        config: Runnable configuration
        
    Yields:
        Text chunks to be streamed to Chainlit
    """
    logger.info(f"🔄 Starting agent stream for message: {user_message[:50]}...")
    
    output_token_count = 0
    input_token_count = 0
    final_output_received = False
    last_message = None
    
    # Estimate input tokens (rough: 1 token ≈ 4 chars)
    input_text = user_message
    for msg in chat_messages:
        if hasattr(msg, 'content'):
            input_text += str(msg.content)
    estimated_input_tokens = len(input_text) // 4
    
    # Build input
    input_messages = chat_messages + [HumanMessage(content=user_message)]
    
    try:
        async for event in agent.astream_events(
            {"messages": input_messages},
            config=config,
            version="v2"
        ):
            kind = event.get("event")
            
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
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text = block.get("text", "")
                                if text:
                                    output_token_count += 1
                                    yield text
                    elif isinstance(content, str):
                        output_token_count += 1
                        yield content
                
                # Try to extract usage metadata if available
                if hasattr(chunk, 'usage_metadata') and chunk.usage_metadata:
                    usage = chunk.usage_metadata
                    if hasattr(usage, 'input_tokens'):
                        input_token_count = usage.input_tokens
                    if hasattr(usage, 'output_tokens'):
                        output_token_count = usage.output_tokens
            
            # Track final output and extract usage
            elif kind == "on_chat_model_end":
                output = event.get("data", {}).get("output", {})
                
                # Try to get usage metadata from the final output
                if hasattr(output, 'usage_metadata') and output.usage_metadata:
                    usage = output.usage_metadata
                    if hasattr(usage, 'input_tokens') and usage.input_tokens:
                        input_token_count = usage.input_tokens
                    if hasattr(usage, 'output_tokens') and usage.output_tokens:
                        output_token_count = usage.output_tokens
                
                # Also check response_metadata
                if hasattr(output, 'response_metadata'):
                    meta = output.response_metadata
                    if isinstance(meta, dict) and 'usage' in meta:
                        usage = meta['usage']
                        input_token_count = usage.get('input_tokens', input_token_count)
                        output_token_count = usage.get('output_tokens', output_token_count)
            
            elif kind == "on_chain_end":
                final_output_received = True
                output = event.get("data", {}).get("output", {})
                
                if isinstance(output, dict) and "messages" in output:
                    messages = output["messages"]
                    if messages and len(messages) > 0:
                        last_msg = messages[-1]
                        if isinstance(last_msg, AIMessage):
                            last_message = last_msg
                            
                            # Extract usage from AIMessage
                            if hasattr(last_msg, 'usage_metadata') and last_msg.usage_metadata:
                                usage = last_msg.usage_metadata
                                if hasattr(usage, 'input_tokens') and usage.input_tokens:
                                    input_token_count = usage.input_tokens
                                if hasattr(usage, 'output_tokens') and usage.output_tokens:
                                    output_token_count = usage.output_tokens
        
        # If no tokens streamed but we have a final message
        if output_token_count == 0 and last_message and last_message.content:
            logger.warning(f"⚠️ No tokens streamed, yielding final message...")
            
            if isinstance(last_message.content, str):
                yield last_message.content
                output_token_count = len(last_message.content) // 4
            elif isinstance(last_message.content, list):
                for block in last_message.content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "")
                        yield text
                        output_token_count += len(text) // 4
                    elif isinstance(block, str):
                        yield block
                        output_token_count += len(block) // 4
        
        # Use estimated input if we didn't get actual count
        if input_token_count == 0:
            input_token_count = estimated_input_tokens
        
        # Calculate costs
        input_cost = (input_token_count / 1000) * PRICE_INPUT_PER_1K
        output_cost = (output_token_count / 1000) * PRICE_OUTPUT_PER_1K
        total_cost = input_cost + output_cost
        
        # Log token usage and cost
        logger.info("=" * 50)
        logger.info("📊 TOKEN USAGE & COST")
        logger.info("=" * 50)
        logger.info(f"   Input tokens:  {input_token_count:,}")
        logger.info(f"   Output tokens: {output_token_count:,}")
        logger.info(f"   Total tokens:  {input_token_count + output_token_count:,}")
        logger.info("-" * 50)
        logger.info(f"   Input cost:    ${input_cost:.6f}")
        logger.info(f"   Output cost:   ${output_cost:.6f}")
        logger.info(f"   💰 TOTAL COST: ${total_cost:.6f}")
        logger.info("=" * 50)
        
    except Exception as e:
        logger.exception(f"❌ Error during streaming: {str(e)}")
        yield f"\n\n❌ Error: {str(e)}"
