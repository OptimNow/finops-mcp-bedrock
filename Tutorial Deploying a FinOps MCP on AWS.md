# Tutorial: Deploying a FinOps MCP on AWS



# Tutorial: Deploy a FinOps Chatbot on AWS EC2



# Tutorial: Deploy a FinOps Chatbot on AWS EC2

## 1. Introduction

### What You'll Build

In this tutorial, you'll deploy an AI-powered FinOps assistant that allows you to analyze AWS costs using natural language. By the end, you'll have:

- A **Chainlit chat interface** running on an EC2 instance
- Integration with **Amazon Bedrock** (using Titan and Nova models)
- Connection to the **AWS Billing & Cost Management MCP server** for cost analysis
- **Data visualization capabilities** - generate charts, graphs, and diagrams from your cost data
- A working chatbot that can answer questions like:
  - "What were my AWS costs last month?"
  - "Show me EC2 spending trends as a graph"
  - "What are my top 5 cost drivers?"
  - "Create a diagram showing my cost breakdown by service"



### Why This Architecture?

This tutorial uses:

- **EC2 instance**: Provides a self-contained environment where all processing happens within your AWS boundaries - no data leaves your infrastructure
- **Model Context Protocol (MCP)**: Enables the LLM to securely access AWS cost data through standardized tools
- **Amazon Bedrock**: Provides managed access to foundation models (Titan, Nova) without using public LLMs or sending data to third-party services
- **Chainlit**: Offers a ready-to-use chat interface without building a custom UI

**Key security benefit**: Your billing data never leaves your EC2 instance. The LLM runs in Bedrock (within AWS), the MCP server runs locally on EC2, and all cost data stays within your AWS account boundaries.

**Extensibility**: You can easily add more MCP servers to extend functionality:
- Additional AWS services (Compute Optimizer, Trusted Advisor, CloudWatch)
- Multi-cloud cost analysis (Azure Cost Management, GCP Billing)
- Custom MCP servers for your specific FinOps workflows



### Prerequisites

Before starting, ensure you have:

- **AWS Account** with billing data available
- **AWS Console access** with permissions to:
  - Launch EC2 instances
  - Create IAM roles and policies
  - Enable Bedrock model access
- **SSH client** installed (Windows: PowerShell or PuTTY, Mac/Linux: built-in terminal)

💡 **Don't worry if you're not familiar with command-line tools** - you can use AI assistants like Claude or ChatGPT to help you navigate Linux commands as you follow this tutorial.



### Time & Cost Estimate

- **Setup time**: 45-90 minutes (depending on your experience level)
- **Monthly cost** (if instance runs 24/7):
  - EC2 t3.small: ~$15-20/month
  - Bedrock API usage: ~$5-10/month (depends on usage)
  - Total: ~$20-30/month

💡 **Cost-saving tip**: Stop the EC2 instance when not in use to reduce costs to ~$5-10/month.

---



## 2. AWS Preparation

This section covers the AWS resources you need to create before launching your EC2 instance. Complete these steps in order.

### Step 2.1: Enable Bedrock Model Access

1. Navigate to the **Amazon Bedrock** console in your chosen region (we'll use **us-east-1** / North Virginia for this tutorial)
2. In the left menu, scroll down to **Model access**
3. Click **Manage model access** or **Request model access**
4. Enable access to:
   - **Amazon Titan** models (Titan Text, Titan Image Generator)
   - **Amazon Nova** models (Nova Pro, Nova Lite, Nova Micro)
5. Click **Save changes** and wait for approval (usually instant)

✅ **Verification**: The status should show "Access granted" for the models you selected.

---

### Step 2.2: Create IAM Policy for MCP & Bedrock

You need a custom IAM policy that grants permissions for Bedrock and AWS cost data access.

1. Download the policy file: [`MCPBedrockPolicy.json`](../MCPBedrockPolicy.json) from the repository root
2. In the **IAM Console**, go to **Policies** → **Create policy**
3. Click the **JSON** tab
4. Copy and paste the content from `MCPBedrockPolicy.json`
5. Click **Next**
6. Name it: **`MCPBedrockPolicy`**
7. Add description: `Permissions for FinOps MCP chatbot to access Bedrock and billing data`
8. Click **Create policy**

**What this policy grants:**
- Bedrock model invocation (InvokeModel, ListFoundationModels)
- Cost Explorer and Billing data access
- (Optional) CloudWatch Logs, Compute Optimizer

✅ **Verification**: You should see "MCPBedrockPolicy" in your IAM policies list.

---

### Step 2.3: Create IAM Role for EC2

Now create an IAM role that your EC2 instance will use to access AWS services.

1. In the **IAM Console**, go to **Roles** → **Create role**
2. Select **Trusted entity type**: **AWS service**
3. Select **Use case**: **EC2**
4. Click **Next**

![Select EC2 as the trusted entity](assets/21.png)

5. In **Permissions**, search for and select: **`MCPBedrockPolicy`** (the policy you just created)
6. Click **Next**
7. Name the role: **`MCPBedrockRole`**
8. Add description: `EC2 service role for FinOps MCP chatbot`
9. Click **Create role**

![Attach the MCPBedrockPolicy to the role](assets/22.png)

**Why an EC2 service role?**
This allows the EC2 instance to automatically assume this role without storing credentials on the instance. It's more secure than using access keys.

✅ **Verification**: You should see "MCPBedrockRole" in your IAM roles list with "MCPBedrockPolicy" attached.

---

### Step 2.4: Create Security Group

Create a security group to control network access to your EC2 instance.

1. In the **EC2 Console**, go to **Security Groups** → **Create security group**
2. Name: **`MCPBedrockSG`**
3. Description: `Security group for FinOps MCP chatbot`
4. VPC: Select your **default VPC** (or custom VPC if you have one)

**Inbound Rules** - Add two rules:

| Type       | Protocol | Port Range | Source | Description        |
| ---------- | -------- | ---------- | ------ | ------------------ |
| SSH        | TCP      | 22         | My IP  | SSH access         |
| Custom TCP | TCP      | 8000       | My IP  | Chainlit UI access |

**Source IP recommendations:**
- **For testing**: Use "My IP" (your current public IP)
- **For team access**: Use your office IP range (e.g., 203.0.113.0/24)
- **Not recommended**: 0.0.0.0/0 (allows access from anywhere - security risk)

**Outbound Rules**: Leave default (All traffic allowed) - needed for the EC2 instance to reach AWS APIs (Bedrock, Cost Explorer, etc.)

🔒 **Security note**: Port 8000 is needed to access the Chainlit web interface from your browser. Without it, you can only access the UI from within the EC2 instance itself.

✅ **Verification**: You should see "MCPBedrockSG" in your security groups list with the two inbound rules.

---

### Step 2.5: Create or Select SSH Key Pair

You need an SSH key pair to connect to your EC2 instance.

**If you already have a key pair**, you can skip this step and use your existing one.

**To create a new key pair:**

1. In the **EC2 Console**, go to **Key Pairs** → **Create key pair**
2. Name: **`MCPBedrockKP`**
3. Key pair type: **RSA** (better compatibility)
4. Private key file format: **.pem** (for OpenSSH)
5. Click **Create key pair** - the file will download automatically

**Important**: 
- Save the `.pem` file in a secure location
- On Mac/Linux, set proper permissions: `chmod 400 MCPBedrockKP.pem`
- On Windows, Windows will handle permissions automatically

✅ **Verification**: You should have the `.pem` file downloaded and know where it's saved.

---

### Preparation Complete ✅

You've now created:
- ✅ Bedrock model access enabled
- ✅ IAM policy: `MCPBedrockPolicy`
- ✅ IAM role: `MCPBedrockRole`
- ✅ Security group: `MCPBedrockSG`
- ✅ Key pair: `MCPBedrockKP.pem`

Next, you'll use these to launch your EC2 instance.

---

------

## 3. Launching the EC2 Instance

- To run the Chainlit UI and MCP server, we need a small **Amazon Linux 2023** intstance, type `t3.small` (or larger), and a disk EBS of 20-30 GiB gp3 is sufficient.
- Attach the **Key Pair**,  **IAM Role** and the **Security Group**.
- Verify that the instance runs in the same region where Bedrock is enabled. (we will be using North Virginia all along this tutorial)



------

## 4. Preparing the Environment

- Open a Powershell and connect to your instance:

  ``ssh -i /path/to/your-key.pem ec2-user@<EC2-Public-IP>``

- Update the system and install basic packages (git, python, pip, tmux).

  - ``sudo dnf update -y``
  - ``sudo dnf install -y git python3-pip tmux``

- Install **uv** (recommended Python package manager). 

  - ``curl -LsSf https://astral.sh/uv/install.sh | sh``

- Clone the **sample-bedrock-mcp** repository.

  - ``git clone https://github.com/aws-samples/sample-bedrock-mcp.git``
    ``cd sample-bedrock-mcp``

- Install dependencies with `uv sync --all-groups`. That will:

  - Download the right Python (3.13 if available),
  - Create `.venv` inside the project folder,
  - Install all dependencies.

- Activate the environment: ``source .venv/bin/activate``

------

## 5. Testing the Sample Bedrock MCP

- **Export the AWS region** environment variable.

  - Run:

    ```
    export AWS_REGION=us-east-1
    ```

    Check it:

    ```
    echo $AWS_REGION
    ```

    That will return `us-east-1`.

- Make sure your **role + permissions + Bedrock region are aligned**: after you’ve exported the region run:

  ```
  aws bedrock list-foundation-models --region $AWS_REGION
  ```

  If everything is wired correctly, you’ll see a JSON list of available models (Anthropic Claude, Amazon Titan, etc.).

- Launch **Chainlit** to start the UI:

  - Make sure you are in the project folder

    ​	Inside your EC2 session:

  ```powershell
  		cd ~/sample-bedrock-mcp
  ```

  ​		And ensure your virtual environment is active:

  ```powershell
  		source .venv/bin/activate
  ```

  ​		Your prompt should now show `(.venv)` at the start.

  - Start the UI server on port 8000:

  ```
  chainlit run src/ui/app.py -h 0.0.0.0 -p 8000
  ```

  ​	Explanation:

  `-h 0.0.0.0` → listens on all network interfaces (so you can access from your laptop).

  `-p 8000` → port 8000, matching your Security Group rule.

- **Access the UI in the browser** on port 8000 :

  - Open your browser and go to:

  ```
  http://<EC2-Public-IP>:8000
  ```

  Replace `<EC2-Public-IP>` with the **Public IPv4 address** of your instance.

  If your Security Group inbound rules are correct, you should see the Chainlit chat UI.

  

  ⚠️ If the browser doesn’t connect:

  - Double-check your **Security Group inbound rule** for TCP 8000.
  - Make sure you’re using the **public IP** (not the private `172.x.x.x`).

  

  ![image-20250918163315029](C:\Users\jlati\AppData\Roaming\Typora\typora-user-images\image-20250918163315029.png)

- Test the default agent with the sample “Math” MCP server.

------

## 6. Connecting the FinOps MCP Server

- In the Chainlit UI (plug icon), add the FinOps MCP server:
  - Command: run the Billing & Cost Management MCP server,
  - Type: stdio,
  - Environment: AWS region and other variables if required.
- Verify that the FinOps tools appear in the tool list.
- Test with a simple query, e.g. *“Show me my AWS costs for the last month.”*

------

## 7. Automation with systemd

- Create a systemd service for **Chainlit** so it starts automatically and restarts on failure.
- Verify its status.
- (Optional) do the same for the FinOps MCP server.

------

## 8. Practical FinOps Scenarios

- Query **cost by service** using Cost Explorer.
- Ask for a **cost forecast**.
- Retrieve **Compute Optimizer recommendations**.
- Check **Savings Plans/RI coverage**.
- (Optional) Enable Storage Lens and analyze S3 storage costs.

------

## 9. FinOps & Security Best Practices

- Do not expose port 8000 to the internet in production (use internal ALB, SSM port-forwarding).
- Restrict **IAM permissions** to the minimum required.
- Monitor **EC2 costs** (t3.small ~ $20–25/month if always running).
- (Optional) stop the EC2 instance outside of test sessions.

------

## 10. Conclusion & Next Steps

- Recap the architecture: **UI (Chainlit)** ↔ **Agent** ↔ **FinOps MCP server** ↔ **AWS Billing APIs** ↔ **Bedrock**.
- Possible extensions:
  - Add a custom MCP server (e.g. CloudWatch or Trusted Advisor).
  - Expose the UI via an ALB + Cognito.
  - Automate installation with Terraform + Ansible.
