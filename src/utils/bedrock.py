import boto3
import warnings
from botocore.config import Config
from langchain_aws.chat_models import ChatBedrockConverse
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


def get_bedrock_client(region_name: str = 'us-west-2') -> BedrockRuntimeClient:
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
    model_id: ModelId,
    inference_config: InferenceConfig | None = None,
    client: BedrockRuntimeClient | None = None,
    boto3_kwargs: dict[str, Any] | None = None,
    cross_region: bool = True,
    thinking_config: Optional[ThinkingConfig] = None,
) -> ChatBedrockConverse:
    """Get a ChatBedrockConverse model.

    Args:
        model_id (ModelId): Model ID
        inference_config (InferenceConfig | None): Inference config
        client (BedrockRuntimeClient | None): Bedrock client
        boto3_kwargs (dict[str, Any] | None): Keyword arguments for boto3
        cross_region (bool): Whether to use cross-region inference (default: True)
        thinking_config (ThinkingConfig | None): Thinking config

    Returns:
        ChatBedrockConverse: ChatBedrockConverse model
    """
    # Add cross-region prefix if necessary and convert Enum to string
    _model_id = f'us.{model_id.value}' if cross_region else model_id.value
    if client and boto3_kwargs:
        warnings.warn(BOTO3_CLIENT_WARNING)
    _client = client or get_bedrock_client(**(boto3_kwargs or {}))

    additional_model_request_fields = {}
    # Add thinking config if provided
    if thinking_config:
        additional_model_request_fields['thinking'] = thinking_config.model_dump()

    # Create the ChatBedrockConverse with appropriate parameters
    if inference_config is None:
        return ChatBedrockConverse(
            model=_model_id,
            client=_client,
            additional_model_request_fields=additional_model_request_fields,
        )

    # If inference_config is provided, include temperature and max_tokens
    return ChatBedrockConverse(
        model=_model_id,
        client=_client,
        temperature=inference_config.temperature,
        max_tokens=inference_config.max_tokens,
        additional_model_request_fields=additional_model_request_fields,
    )
