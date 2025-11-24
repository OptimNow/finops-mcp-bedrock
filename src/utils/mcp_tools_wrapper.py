"""
MCP Tools Wrapper - Wraps MCP tools to add consent management.
"""
from langchain.tools import StructuredTool
from loguru import logger
from typing import Any
import chainlit as cl


class ConsentDeniedError(Exception):
    """Raised when user denies consent for an operation."""
    pass


async def request_user_consent(operation: str, details: str) -> bool:
    """
    Request user consent via Chainlit without blocking the agent flow.
    
    Args:
        operation: The operation being requested
        details: Additional details about the operation
        
    Returns:
        bool: True if user consents, False otherwise
    """
    logger.info(f"🔐 Requesting consent for operation: {operation}")
    
    try:
        # Use AskUserMessage for simple yes/no
        res = await cl.AskUserMessage(
            content=f"⚠️ **Confirmation Required**\n\n**Operation:** `{operation}`\n\n**Details:**\n```\n{details}\n```\n\nThis will modify your AWS infrastructure. Type 'yes' to approve or 'no' to deny.",
            timeout=60
        ).send()
        
        if res:
            user_response = res.get("output", "").strip().lower()
            
            if user_response in ["yes", "y", "approve", "ok"]:
                logger.info(f"✅ User approved operation: {operation}")
                return True
            else:
                logger.info(f"❌ User denied operation: {operation}")
                return False
        else:
            logger.warning(f"⏱️ Timeout waiting for consent: {operation}")
            return False
            
    except Exception as e:
        logger.error(f"Error requesting consent: {e}")
        return False


def is_mutation_operation(tool_name: str, arguments: dict) -> tuple[bool, str]:
    """
    Check if a tool operation is a mutation (write/modify operation).
    
    Args:
        tool_name: Name of the MCP tool
        arguments: Arguments being passed to the tool
        
    Returns:
        tuple: (is_mutation: bool, operation_description: str)
    """
    # AWS API MCP tool
    if tool_name == "call_aws":
        cli_command = arguments.get("cli_command", "")
        
        # List of AWS CLI commands that are mutations
        mutation_keywords = [
            "create", "delete", "modify", "update", "put", "terminate",
            "stop", "start", "reboot", "attach", "detach", "associate",
            "disassociate", "enable", "disable", "configure"
        ]
        
        cli_lower = cli_command.lower()
        for keyword in mutation_keywords:
            if keyword in cli_lower:
                return True, cli_command
        
        return False, ""
    
    return False, ""


async def wrap_mcp_tool_with_consent(original_tool, tool_name: str, **kwargs) -> Any:
    """
    Wrapper function that adds consent management to MCP tools.
    
    Args:
        original_tool: The original MCP tool
        tool_name: Name of the tool
        **kwargs: Arguments for the tool
        
    Returns:
        Result from the original tool or error message if consent denied
    """
    # Check if this is a mutation operation
    is_mutation, operation_desc = is_mutation_operation(tool_name, kwargs)
    
    if is_mutation:
        logger.info(f"🔐 Mutation detected: {operation_desc}")
        
        # Request consent
        consent_granted = await request_user_consent(tool_name, operation_desc)
        
        if not consent_granted:
            error_msg = f"Operation '{operation_desc}' was denied by user"
            logger.warning(f"❌ {error_msg}")
            # Return error as string so agent can process it
            return f"❌ {error_msg}. The operation was cancelled and no changes were made to AWS infrastructure."
    
    # Execute the original tool
    try:
        logger.info(f"▶️ Executing tool: {tool_name}")
        
        # Call the original tool's invoke method
        if hasattr(original_tool, 'ainvoke'):
            result = await original_tool.ainvoke(kwargs)
        elif hasattr(original_tool, 'invoke'):
            result = original_tool.invoke(kwargs)
        else:
            # Direct async call
            result = await original_tool.func(**kwargs)
        
        logger.info(f"✅ Tool {tool_name} executed successfully")
        return result
        
    except Exception as e:
        logger.error(f"❌ Error executing tool {tool_name}: {e}")
        return f"❌ Error executing {tool_name}: {str(e)}"


def wrap_mcp_tools(mcp_tools: list) -> list:
    """
    Wrap all MCP tools to add consent management.
    
    Args:
        mcp_tools: List of MCP tools from langchain-mcp-adapters
        
    Returns:
        List of wrapped tools
    """
    wrapped_tools = []
    
    for tool in mcp_tools:
        tool_name = tool.name
        original_tool = tool
        
        # Create wrapped async function
        async def make_wrapped_func(t_name, orig_tool):
            async def wrapped(**kwargs):
                return await wrap_mcp_tool_with_consent(orig_tool, t_name, **kwargs)
            return wrapped
        
        # Import asyncio to create the wrapped function
        import asyncio
        try:
            # Try to get or create event loop
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        wrapped_func = loop.run_until_complete(make_wrapped_func(tool_name, original_tool))
        
        # Create a new StructuredTool with the wrapped function
        wrapped_tool = StructuredTool.from_function(
            coroutine=wrapped_func,
            name=tool.name,
            description=tool.description,
            args_schema=getattr(tool, 'args_schema', None),
        )
        
        wrapped_tools.append(wrapped_tool)
        logger.debug(f"Wrapped tool: {tool_name}")
    
    logger.info(f"✅ Wrapped {len(wrapped_tools)} MCP tools with consent management")
    return wrapped_tools
