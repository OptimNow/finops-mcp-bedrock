# Cloud FinOps Assistant (MCP + Bedrock + Chainlit)



This project is a **FinOps assistant** built on top of **AWS Bedrock**, **LangChain**, and the **Model Context Protocol (MCP)**.  

It connects to external MCP servers (such as **AWS Billing & Cost Management**, Azure, and GCP) to query cloud costs and enrich the assistant with live data and tools.  

The UI is powered by **Chainlit**, giving you a chat interface where you can:
- Analyze AWS costs and usage through the AWS Billing MCP server , using Claude 3.5 Sonnet.
- Generate charts and graphs from cost data (Vega-Lite renderer)  
- Create diagrams or images (Mermaid + Amazon Titan Image Generator v2)  
- Extend the assistant with more
- MCP servers (Azure, GCP, etc.)  



---

## Features

- **AWS Cost Analysis**: Query and analyze AWS costs through the AWS Billing MCP server
- **Data Visualization**: Generate charts and graphs from cost data using Vega-Lite renderer
- **Image Generation**: Create diagrams with Mermaid or generate images using Amazon Titan Image Generator v2
- **Multi-Cloud Ready**: Extend with additional MCP servers for Azure and GCP cost analysis
- **Interactive Chat Interface**: User-friendly Chainlit UI for natural language queries

## 🔥 Multi-MCP Integration with Intelligent Consent Management

### What's New

This FinOps assistant integrates **two MCP servers simultaneously** to provide comprehensive AWS cost analysis:

- **AWS Cost Explorer MCP**: Historical billing data (24-48h latency)
- **AWS API MCP**: Real-time infrastructure state (< 1s latency)

### Smart Orchestration

The agent intelligently orchestrates both MCPs:
```
User: "Analyze my EBS situation"
├─ Step 1: AWS API → describe-volumes (current inventory)
├─ Step 2: Cost Explorer → get_cost_and_usage (historical costs)
└─ Step 3: Reconcile & recommend optimizations
```

### Consent Management

**Read-only operations** (describe, list, get) execute automatically:
- ✅ No confirmation needed for analysis queries
- ✅ Fast, friction-free cost exploration

**Mutation operations** (modify, delete, stop, start) require explicit user approval:
- ⚠️ Chainlit prompts user with operation details
- 🔐 User types "yes" or "no" to approve/deny
- 📝 All decisions logged for audit trail

### Quick Start
```bash
# 1. Configure MCP servers
cp .chainlit/mcp.json.example .chainlit/mcp.json

# 2. Ensure IAM permissions (see below)

# 3. Run the assistant
CHAINLIT_MCP_CONFIG=.chainlit/mcp.json chainlit run src/ui/app.py --host 0.0.0.0 --port 8000
```

### Required IAM Permissions

Your EC2 instance role needs:

**For Cost Analysis (read-only)**:
- `ce:GetCostAndUsage`
- `ce:GetCostForecast`
- `ec2:DescribeVolumes`
- `ec2:DescribeInstances`

**For Infrastructure Modifications (optional)**:
- `ec2:ModifyVolume` (EBS type changes)
- `ec2:StopInstances` / `ec2:StartInstances` (instance control)

See `MCPBedrockPolicy.json` for complete policy.

### Example Queries
```
"What were my AWS costs last month?"
"Analyze my EBS volumes and suggest optimizations"
"Compare my costs between September and October"
"Stop the Dev and Integration instances"  # Requires consent
```

### Architecture
```
┌─────────────────────────────────────────────┐
│  Chainlit UI (User Interface)               │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│  LangGraph Agent (Claude 3.5 Sonnet)        │
│  - Smart MCP orchestration                  │
│  - Consent management                       │
│  - Response streaming                       │
└──────────────┬────────────────┬─────────────┘
               │                │
     ┌─────────▼──────┐  ┌─────▼──────────┐
     │ AWS Cost       │  │ AWS API MCP    │
     │ Explorer MCP   │  │ (Real-time)    │
     │ (Historical)   │  │                │
     └────────────────┘  └────────────────┘
```

## Security & Guardrails

This application implements AWS Bedrock Guardrails to ensure secure and appropriate interactions:

- **Content Filtering**: Blocks harmful content including hate speech, violence, and inappropriate material
- **Prompt Injection Protection**: Defends against prompt attack attempts at high threshold
- **PII Protection**: Automatically filters sensitive information (credentials, SSNs, API keys)
- **Topic Restrictions**: Keeps conversations focused on cloud cost management and FinOps
- **Scope Limitation**: Restricts operations to read-only billing and cost analysis APIs

All conversations are monitored through Bedrock Guardrails to maintain professional, secure, and purpose-focused interactions. The guardrail configuration can be customized based on your organization's security requirements.

For detailed guardrail setup instructions, see [INSTALL.md](INSTALL.md#section-9-configure-bedrock-guardrails-optional).



---

## Prerequisites

Before installing, ensure you have:

- **AWS Account** with access to Amazon Bedrock (Titan and Claude Sonnet 3.5 models)

- **Python 3.13+** installed

- **AWS IAM permissions** for:
  - Amazon Bedrock model invocation
  - AWS Cost Explorer / Billing data access
  
- **uv package manager**: Install [`uv`](https://github.com/astral-sh/uv) which provides the `uvx` executable needed to launch MCP servers. Follow the [upstream installation instructions](https://github.com/astral-sh/uv) for your platform.

  

## Tutorial / Installation



### Deploy

Follow the step-by-step tutorial: [INSTALL](INSTALL.md)

It explains how to:

1. Prepare the Python environment  

2. Install dependencies from `requirements.txt`  

3. Configure `.env` with your AWS credentials and region  

4. Run the AWS Billing MCP server  

5. Start Chainlit and connect to the assistant  

   

---

## Usage

From your EC2 instance:
```bash
source .venv/bin/activate
CHAINLIT_MCP_CONFIG=.chainlit/mcp.json chainlit run src/ui/app.py --host 0.0.0.0 --port 8000
```

Then open the app in your browser at:

http://<your-ec2-public-ip>:8000

**Note:** For detailed configuration of `.env` and `.chainlit/mcp.json`, see the [Tutorial](Tutorial Deploying a FinOps MCP on AWS.md).




## Architecture

### How It Works

This project uses **LangGraph** to create a ReAct agent that follows this workflow:

1. User submits a query through the Chainlit chat interface
2. The LangGraph agent analyzes the query and determines which MCP tools to use
3. The agent calls AWS Billing MCP server tools to retrieve cost data
4. Results are processed and returned with visualizations or explanations

The ReAct agent is created using `langgraph.prebuilt.create_react_agent()`, which orchestrates the reasoning and tool-use process.



### MCP Integration

The `langchain-mcp-adapters` package bridges LangChain and the Model Context Protocol:

- `load_mcp_tools()` converts MCP tools into LangChain-compatible format
- Tools are dynamically loaded and provided to the LangGraph agent
- Enables seamless integration between Amazon Bedrock models (Titan and Claude sonnet 3.5) and AWS Billing MCP server

This adapter pattern allows easy addition of MCP servers for Azure, GCP, or custom tools.



## Project Structure

├── src/ 

│   ├── ui/ 

│   │   └── app.py              # Chainlit application with LangGraph integration 

│   └── utils/                  # Bedrock integration and streaming utilities 

├── .chainlit/ 

│   └── mcp.json                # MCP server configuration 

├── .env                        # AWS credentials and region configuration 

├── requirements.txt            # Python dependencies 

└── INSTALL.md

- **Key files:**
  - **`app.py`**: Main Chainlit application with LangGraph ReAct agent
  - **`mcp.json`**: Defines external MCP servers (AWS Billing, Azure, GCP)
  - **`.env`**: AWS configuration (region, profile, credentials)




## Extending to Multi-Cloud

To add Azure or GCP cost analysis, update `.chainlit/mcp.json` with additional MCP servers:
```json
{
  "mcpServers": {
    "aws-billing": {
      "command": "uvx",
      "args": ["--from", "awslabs-cost-explorer-mcp-server", "awslabs.cost-explorer-mcp-server"],
      "env": {
        "AWS_REGION": "us-east-1"
      }
    }
  }
}
```

The LangGraph agent will automatically discover and use tools from all configured MCP servers.



## Troubleshooting

- If you encounter issues connecting to Bedrock, check your AWS credentials and ensure you have the necessary permissions.
- Check the logs in the terminal running the Chainlit application for detailed error messages. You can set the `LOG_LEVEL` environment variable to `DEBUG` to get more detailed logs.
