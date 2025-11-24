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
    
    @staticmethod
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
                    return True, f"AWS CLI: {cli_command}"
            
            return False, ""
        
        # Add other MCP tools that might need consent here
        return False, ""
