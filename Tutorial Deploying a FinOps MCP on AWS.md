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

- **Enable Bedrock** in the chosen region: in the bedrock menu scroll down to model access and request access to all Anthropic models. (video)

- Create an **IAM policy** "MCPBedrockPolicy" with 

  - Permissions for Bedrock (InvokeModel, ListFoundationModels, …),
  - Permissions for Billing/Cost Explorer/Budgets/Pricing/Compute Optimizer, etc.,
  - (Optional) CloudWatch Logs, Storage Lens/Athena.
  - check the inline policy here that you can load in the json.

- Create an IAM AWS **Service Role**  "MCPBedrockRole" for the EC2 instance:

  - You want the **role to be assumed by an EC2 instance**.
  - So when you create it in the console, choose **“Trusted entity type = AWS service”**, then **“Use case = EC2”**.
  - That makes it an **EC2 service role** (an IAM role that EC2 instances can assume automatically when attached).
  - ![](C:\Users\jlati\AppData\Roaming\Typora\typora-user-images\image-20250917151508981.png)

- Attach the custom FinOps MCP policy to the role. then, when you launch the instance, select this role under IAM instance profile.

  ![image-20250917151838187](C:\Users\jlati\AppData\Roaming\Typora\typora-user-images\image-20250917151838187.png)

- Create a **Security Group** "MCPBedrockSG" opening port 22 for ssh and 8000 for chainlit. 

  🔑 Why do we need port 8000? By default, the **Chainlit UI** (the chat interface in your sample) runs on **TCP port 8000**. If you want to open that UI in a browser from your laptop (outside AWS), the EC2 instance must accept inbound traffic on port 8000. Without opening it, you could only connect *from inside* the instance (e.g., with `curl localhost:8000`). 

  So: opening **8000/tcp inbound** makes the Chainlit web app accessible.

  - When creating the SG, we can select our default VPC, unless you want a custom network topology). 
  - In Inbound Rules, Add 2 rules type "Custom TCP Rule", first one for port Range 8000, second on port range 22, Source: for testing/demo, enter your IP, or 0.0.0.0/0 if you want access from anywhere -but not recommended for production.
  - In Outbound rules: leave default (All traffic allowed) — needed for the EC2 to reach AWS APIs (Bedrock, Cost Explorer, etc.).

- Create a **Key Pair** "MCPBedrockKP" or plan to use **Session Manager** for access:

  - **Key pair type** → **RSA**

    - RSA is the default and broadly supported by OpenSSH and Amazon Linux.
    - ED25519 also works, but RSA is safest for compatibility.

    **Private key file format** → **.pem**

    - `.pem` is the standard format used by OpenSSH clients and AWS tutorials.
    - You’ll use this file with `ssh -i mykey.pem ec2-user@...` to log in.
    - Keep it safe and **chmod 400 mykey.pem** before using, otherwise SSH will complain about permissions.





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
