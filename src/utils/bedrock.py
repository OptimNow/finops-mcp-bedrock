import boto3
import os
import warnings
from botocore.config import Config
from langchain_aws.chat_models import ChatBedrockConverse
from loguru import logger
from src.utils.models import (
    BOTO3_CLIENT_WARNING,
    InferenceConfig,
    ModelId,
    ThinkingConfig,
)
from typing import TYPE_CHECKING, Any, Optional


if TYPE_CHECKING:
    from mypy_boto3_bedrock_runtime import BedrockRuntimeClient
else:
    BedrockRuntimeClient = object


def get_bedrock_client(region_name: str = 'us-east-1') -> BedrockRuntimeClient:
    """Get a Bedrock client.

    Uses a custom config with retries and read timeout.

    Config is used to set the following:
    - retries: max_attempts=5, mode='adaptive'
    - read_timeout=60

    Returns:
        BedrockRuntimeClient: Bedrock client
    """
    return boto3.client(
        'bedrock-runtime',
        region_name=region_name,
        config=Config(
            retries={'max_attempts': 10, 'mode': 'adaptive'},
            read_timeout=60,
        ),
    )


def get_chat_model(
    model_id: str = ModelId.ANTHROPIC_CLAUDE_SONNET_4_5,
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> ChatBedrockConverse:
    """
    Get a ChatBedrockConverse model instance.
    For Claude 4.x models, use inference profiles (global.anthropic.*).
    
    Args:
        model_id: The model ID or inference profile ID to use
        temperature: Sampling temperature (0.0 = deterministic)
        max_tokens: Maximum tokens in response
        
    Returns:
        Configured ChatBedrockConverse instance
    """
    import boto3
    
    # Resolve model_id if it's still a class attribute reference
    if hasattr(model_id, '__class__') and 'ModelId' in str(model_id.__class__):
        logger.error(f"❌ model_id is not resolved: {model_id}")
        raise ValueError(f"model_id must be a string, got: {type(model_id)}")
    
    # Inference profiles must use us-east-1 endpoint
    bedrock_runtime = boto3.client(
        service_name="bedrock-runtime",
        region_name="us-east-1",
    )
    
    logger.info(f"🤖 Using model: {model_id}")
    logger.info(f"   Temperature: {temperature}, Max tokens: {max_tokens}")
    
    return ChatBedrockConverse(
        client=bedrock_runtime,
        model=model_id,
        temperature=temperature,
        max_tokens=max_tokens,
    )
