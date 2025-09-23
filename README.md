<<<<<<< HEAD
# finops-mcp-bedrock
GenAI FinOps accelerator in chainlit on EC2 with LLM in Bedrock
======= All below to be updated =====
# Amazon Bedrock and MCP Server integration, the easy way

This project demonstrates how to integrate foundation models on Amazon Bedrock with Chainlit and MCP (Model Context Protocol) servers to create an interactive chat interface with tool-enhanced capabilities.

## Project Overview

This sample application showcases:

- Integration with Amazon Bedrock using Anthropic Claude 3.5 Sonnet
- A Chainlit web interface for conversational AI interactions
- A custom Model Context Protocol (MCP) server that performs basic math operations
- Streaming responses for a smooth user experience
- LangChain integration with MCP adapters to connect external tools
- LangGraph for creating a ReAct (Reasoning and Acting) agent that orchestrates tool use

## Prerequisites

Before getting started, ensure you have:

- **AWS Account**: You'll need an AWS account with Bedrock access
- **Bedrock Access**: Ensure your AWS account has access to the Anthropic Claude 3.7 Sonnet model
- **AWS CLI**: Configured with appropriate credentials and permissions
- **Python 3.13+**: This project requires Python 3.13 or newer
- **UV**: For dependency management and building (install with `pip install uv`)

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/aws-samples/sample-bedrock-mcp.git
   cd sample-bedrock-chainlit-mcp
   ```

2. Create a virtual environment and install dependencies using UV:

   ```bash
   uv sync --all-groups
   ```

3. Configure AWS credentials (if not already done):

   ```bash
   aws configure
   ```

## Building from Source

To build the project from source using UV:

1. Build the package:

   ```bash
   uv build
   ```

This will create distribution files in the `dist/` directory, including the wheel file `dist/sample_bedrock_chainlit_mcp-0.1.0-py3-none-any.whl` that can be installed or used directly as the MCP server.

## Usage Guide

### Starting the Chainlit Application

To start the Chainlit application:

```bash
chainlit run src/ui/app.py
```

This will launch a web server (typically at <http://localhost:8000>) with the chat interface.

### Setting up the MCP Server

The Math MCP server needs to be connected to provide calculation capabilities:

1. In the Chainlit web interface, look for the small plug icon under the chat text input element
2. Click on it to open the MCP connection dialog
3. Enter the following details:
   - **Name**: `math`
   - **Command**: `uvx dist/sample_bedrock_chainlit_mcp-0.1.0-py3-none-any.whl`
   - **Type**: default (stdio)
4. Click "Confirm"

A successful connection will be indicated in the interface, and the math tools will become available to the Claude model.

### Example Usage

Once the Chainlit application is running and the MCP server is connected, you can ask mathematical questions like:

- "What's (3 + 5) x 12?"
- "Can you calculate 144 divided by 12?"
- "If I have 7 apples and get 9 more, then give 4 away, how many do I have left?"

The model will use the MCP tools to perform the calculations and return the results.

## Technical Implementation

### LangGraph Integration

This project uses LangGraph to create a ReAct agent that follows this workflow:

1. The agent receives user input via the Chainlit interface
2. It analyzes the input to determine if mathematical operations are needed
3. When math is required, it uses the MCP tools to perform calculations
4. Results are returned to the user with a detailed explanation

The ReAct agent is created using `langgraph.prebuilt.create_react_agent()`, which orchestrates the reasoning and tool-use process.

### LangChain MCP Adapters

The `langchain-mcp-adapters` package serves as a bridge between LangChain and MCP:

- `load_mcp_tools()` converts MCP tools into LangChain-compatible tools
- These tools are then provided to the LangGraph agent for use in the ReAct loop
- This enables seamless integration between the Claude model on Amazon Bedrock and the custom math tools

This adapter pattern allows the application to easily incorporate additional MCP servers with different capabilities in the future.

## MCP Server Details

This project includes a simple MCP server with the following arithmetic operations:

- **add**: Add two numbers together
- **subtract**: Subtract one number from another
- **multiply**: Multiply two numbers together
- **divide**: Divide one number by another

These operations are exposed as tools that the Claude model can use when prompted with mathematical questions.

## Development

The project structure includes:

- `src/mcp/server.py`: The MCP server implementation with math operations
- `src/ui/app.py`: The Chainlit application setup with LangGraph and MCP integration
- `src/utils/`: Utility modules for Bedrock integration and streaming

To modify the MCP server or add new capabilities, edit the `src/mcp/server.py` file and rebuild using `uv build`.

## Troubleshooting

- If you encounter issues connecting to Bedrock, check your AWS credentials and ensure you have the necessary permissions.
- For MCP connection issues, verify that the wheel file exists in the dist directory and that you're using the correct command in the Chainlit interface.
- Check the logs in the terminal running the Chainlit application for detailed error messages. You can set the `LOG_LEVEL` environment variable to `DEBUG` to get more detailed logs.
>>>>>>> 580c474 (init)
