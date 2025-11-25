"""
MCP Consent Handler - Manages user consent for AWS mutations via Chainlit UI.
"""
import chainlit as cl
from loguru import logger
from typing import Optional


class ConsentManager:
    """Manages user consent for MCP tool operations."""
    
    @staticmethod
    async def request_consent(operation: str, details: str) -> bool:
        """
        Request user consent for a potentially destructive operation.
        
        Args:
            operation: The operation being requested (e.g., "ec2 modify-volume")
            details: Additional details about the operation
            
        Returns:
            bool: True if user consents, False otherwise
        """
        logger.info(f"🔐 Requesting consent for operation: {operation}")
        
        # Format the consent request message
        consent_message = f"""
⚠️ **Confirmation Required**

**Operation:** `{operation}`

**Details:**
```
{details}
```

This operation will modify your AWS infrastructure.

**Reply with "yes" to approve or "no" to deny.**
        """
        
        try:
            # Send the consent request
            await cl.Message(content=consent_message).send()
            
            # Wait for user response with AskUserMessage
            res = await cl.AskUserMessage(
                content="Do you approve this operation? (yes/no)",
                timeout=60
            ).send()
            
            if res:
                user_response = res.get("output", "").strip().lower()
                if user_response in ["yes", "y", "approve", "ok"]:
                    logger.info(f"✅ User approved operation: {operation}")
                    await cl.Message(content="✅ Operation approved. Proceeding...").send()
                    return True
                else:
                    logger.info(f"❌ User denied operation: {operation}")
                    await cl.Message(content="❌ Operation cancelled by user.").send()
                    return False
            else:
                logger.warning(f"⏱️ Timeout waiting for consent: {operation}")
                await cl.Message(content="⏱️ Consent request timed out. Operation cancelled.").send()
                return False
                
        except Exception as e:
            logger.error(f"Error requesting consent: {e}")
            # Default to deny on error
            await cl.Message(content=f"❌ Consent request failed: {str(e)}. Operation cancelled.").send()
            return False


def is_mutation_operation(tool_name: str, tool_input: dict) -> bool:
    """
    Determine if a tool call is a mutation operation.
    
    Mutation operations modify AWS infrastructure (create, modify, delete, stop, start).
    Read-only operations (describe, list, get) do NOT require consent.
    """
    logger.info(f"🔍 Checking mutation for tool: {tool_name}")
    logger.info(f"🔍 Tool input: {tool_input}")
    
    # AWS CLI commands that are mutations
    mutation_keywords = [
        'create', 'delete', 'modify', 'update', 'put', 'attach', 'detach',
        'start', 'stop', 'terminate', 'reboot', 'associate', 'disassociate',
        'enable', 'disable', 'register', 'deregister'
    ]
    
    # Read-only operations - explicitly allowed without consent
    readonly_keywords = [
        'describe', 'list', 'get', 'show'
    ]
    
    # Check if it's a call_aws operation
    if tool_name == "call_aws":
        # Try different possible keys for the command
        command = (
            tool_input.get("command", "") or 
            tool_input.get("aws_command", "") or
            tool_input.get("cli_command", "") or
            str(tool_input)
        ).lower()
        
        logger.info(f"🔍 Extracted command: {command}")
        
        # First check if it's explicitly read-only
        for keyword in readonly_keywords:
            if keyword in command:
                logger.info(f"🟢 Read-only operation detected (keyword: {keyword})")
                return False
        
        # Then check if it's a mutation
        for keyword in mutation_keywords:
            if keyword in command:
                logger.info(f"🔴 Mutation operation detected (keyword: {keyword})")
                return True
        
        # If no mutation keywords found, assume read-only
        logger.info(f"🟢 No mutation keywords found, treating as read-only")
        return False
    
    # For non-AWS operations, default to no consent needed
    logger.info(f"🟢 Non-AWS operation, no consent needed")
    return False
