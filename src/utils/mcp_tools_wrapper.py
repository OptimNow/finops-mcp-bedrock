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
    logger.info(f"🔍 Checking mutation for tool: {tool_name}")
    logger.info(f"🔍 Tool arguments: {arguments}")
    
    # AWS API MCP tool
    if tool_name == "call_aws":
        # Try multiple possible parameter names
        cli_command = (
            arguments.get("cli_command", "") or 
            arguments.get("command", "") or
            arguments.get("aws_command", "") or
            ""
        )
        
        logger.info(f"🔍 Extracted CLI command: {cli_command}")
        
        cli_lower = cli_command.lower()
        
        # IMPORTANT: Check read-only operations FIRST
        readonly_keywords = [
            "describe", "list", "get", "show", "head"
        ]
        
        for keyword in readonly_keywords:
            if keyword in cli_lower:
                logger.info(f"🟢 Read-only operation detected (keyword: {keyword})")
                return False, ""
        
        # Then check for mutation keywords
        mutation_keywords = [
            "create", "delete", "modify", "update", "put", "terminate",
            "stop", "start", "reboot", "attach", "detach", "associate",
            "disassociate", "enable", "disable", "configure", "run",
            "allocate", "release", "copy", "import", "export"
        ]
        
        for keyword in mutation_keywords:
            if keyword in cli_lower:
                logger.info(f"🔴 Mutation operation detected (keyword: {keyword})")
                return True, cli_command
        
        # Default: assume read-only if no mutation keyword found
        logger.info(f"🟢 No mutation keywords found, treating as read-only")
        return False, ""
    
    # For other tools, default to no consent needed
    logger.info(f"🟢 Non-AWS API tool ({tool_name}), no consent needed")
    return False, ""


def wrap_mcp_tools(mcp_tools: list) -> list:
    """
    Wrap all MCP tools to add consent management.
    
    Args:
        mcp_tools: List of MCP tools from langchain-mcp-adapters
        
    Returns:
        List of wrapped tools with consent management
    """
    wrapped_tools = []
    
    for tool in mcp_tools:
        tool_name = tool.name
        original_tool = tool
        
        # Create the wrapped async function
        async def wrapped_invoke(original_t=original_tool, t_name=tool_name, **kwargs):
            """Wrapped tool function with consent management."""
            
            # Check if this is a mutation operation
            is_mutation, operation_desc = is_mutation_operation(t_name, kwargs)
            
            if is_mutation:
                logger.info(f"🔐 Mutation detected for {t_name}: {operation_desc}")
                
                # Request consent
                consent_granted = await request_user_consent(t_name, operation_desc)
                
                if not consent_granted:
                    error_msg = f"Operation '{operation_desc}' was denied by user"
                    logger.warning(f"❌ {error_msg}")
                    return f"❌ {error_msg}. The operation was cancelled and no changes were made to AWS infrastructure."
            
            # Execute the original tool
            try:
                result = await original_t.ainvoke(kwargs)
                logger.info(f"✅ Tool {t_name} executed successfully")
                return result
            except Exception as e:
                error_msg = str(e)
                logger.error(f"❌ Tool {t_name} failed: {error_msg}")
                
                # Check if it's a permission error
                if "UnauthorizedOperation" in error_msg or "not authorized" in error_msg.lower():
                    return f"❌ Permission Error: The current IAM role does not have permission to perform this operation. Error: {error_msg}"
                else:
                    return f"❌ Error executing {t_name}: {error_msg}"
        
        # Create a new StructuredTool with the wrapped function
        wrapped_tool = StructuredTool.from_function(
            coroutine=wrapped_invoke,
            name=tool.name,
            description=tool.description,
            args_schema=getattr(tool, 'args_schema', None),
        )
        
        wrapped_tools.append(wrapped_tool)
        logger.debug(f"✅ Wrapped tool: {tool_name}")
    
    logger.info(f"✅ Wrapped {len(wrapped_tools)} MCP tools with consent management")
    return wrapped_tools
