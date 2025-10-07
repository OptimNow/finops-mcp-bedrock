import asyncio
import os
from mcp import StdioServerParameters, ClientSession
from mcp.client.stdio import stdio_client
from langchain_mcp_adapters.tools import load_mcp_tools

async def test_mcp():
    server_params = StdioServerParameters(
        command="uvx",
        args=["--from", "awslabs-cost-explorer-mcp-server", "awslabs.cost-explorer-mcp-server"],
        env={"AWS_REGION": "us-east-1"}
    )
    
    print("Connecting to MCP server...")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("✅ Connected!")
            
            tools = await load_mcp_tools(session)
            print(f"✅ Loaded {len(tools)} tools:")
            for tool in tools:
                print(f"  - {tool.name}")

if __name__ == "__main__":
    asyncio.run(test_mcp())
