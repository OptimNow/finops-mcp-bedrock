from enum import Enum
from pydantic import BaseModel, Field


class ThinkingType(str, Enum):
    """Type of thinking for the model."""

    ENABLED = 'enabled'


class ThinkingConfig(BaseModel):
    """Configuration for model thinking."""

    type: ThinkingType = Field(default=ThinkingType.ENABLED)
    budget_tokens: int = Field(default=1024, ge=1024, le=6524)


BOTO3_CLIENT_WARNING = Warning('Boto3 kwargs will be ignored if client is specified')


class InferenceConfig(BaseModel):
    """Inference config."""

    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    max_tokens: int


class ModelId(str, Enum):
    """Model IDs for Bedrock."""

    ANTHROPIC_CLAUDE_3_7_SONNET = 'anthropic.claude-3-7-sonnet-20250219-v1:0'
