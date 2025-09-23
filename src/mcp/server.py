from mcp.server.fastmcp import FastMCP
from pydantic import Field


mcp = FastMCP(instructions='This is a server that can do basic math and arithmetic operations.')


@mcp.tool()
async def add(
    a: int | float = Field(description='The first number to add.'),
    b: int | float = Field(description='The second number to add.'),
) -> int | float:
    """Use this tool to add two numbers together."""
    return a + b


@mcp.tool()
async def subtract(
    a: int | float = Field(description='The number to subtract from.'),
    b: int | float = Field(description='The number to subtract.'),
) -> int | float:
    """Use this tool to subtract one number from another."""
    return a - b


@mcp.tool()
async def multiply(
    a: int | float = Field(description='The first number to multiply.'),
    b: int | float = Field(description='The second number to multiply.'),
) -> int | float:
    """Use this tool to multiply two numbers together."""
    return a * b


@mcp.tool()
async def divide(
    a: int | float = Field(description='The number to divide.'),
    b: int | float = Field(description='The number to divide by.'),
) -> float:
    """Use this tool to divide one number by another.

    Returns the result rounded to 9 decimal places.
    Raises ValueError if attempting to divide by zero.
    """
    if b == 0:
        raise ValueError('Cannot divide by zero')

    result = a / b
    return round(result, 9)


def main():
    """Entry point for the MCP server."""
    mcp.run()


if __name__ == '__main__':
    main()
