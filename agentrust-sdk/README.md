# Agentrust SDK

Python SDK for the Agentrust Agent Identity and Permission System.

## Overview

Agentrust is a decentralized identity and permission system for AI agents based on certificate chains and capability tokens. This SDK allows agents to:

- Authenticate with the Agentrust CA service
- Execute protected operations with automatic token chain assembly
- Delegate capabilities to other agents with attenuation parameters
- Access Feishu (Lark) APIs through the Agentrust permission model

## Installation

```bash
pip install agentrust-sdk
```

Or install from source:

```bash
cd agentrust-sdk
pip install -e .
```

## Quick Start

### 1. Initialize Wallet

```python
from agentrust import AgentWallet

# Load private key from file
wallet = AgentWallet(private_key_path="./keys/agent_private.pem")

# Or load from PEM string
wallet = AgentWallet(private_key_pem="-----BEGIN EC PRIVATE KEY-----\n...")
```

### 2. Create Client and Authenticate

```python
from agentrust import AgentClient

client = AgentClient("http://localhost:8000/api/v1", wallet)
client.authenticate("agent-analyst", "cert-001")
```

### 3. Execute Operations

```python
# Read from a database
result = client.execute("read_database", "user_table")
print(result["data"])

# With parameters
result = client.execute("read_database", "user_table", params={"filter": "active"})
```

### 4. Delegate Capabilities

```python
# Delegate read_database to another agent with attenuation
delegation = client.delegate(
    to_agent_id="agent-reporter",
    capability="read_database",
    resource_scope="user_table",
    attenuations={"rows_limit": 100, "fields": ["name", "email"]},
    max_depth=1,
    validity_minutes=60
)
```

### 5. Use Feishu API

```python
from agentrust import FeishuClient

feishu = FeishuClient(client)

# Read a bitable
records = feishu.read_bitable("app_xxx", "tbl_xxx", fields=["name", "email"])

# Send a message
feishu.send_text_message("ou_xxx", "Hello!")

# Create a meeting
meeting = feishu.create_meeting(
    topic="Team Meeting",
    start_time="2025-04-20T10:00:00Z",
    end_time="2025-04-20T11:00:00Z"
)
```

## Core Concepts

### AgentWallet

The `AgentWallet` manages an agent's identity materials:

- **Private key**: Never leaves the wallet
- **Certificates**: Issued by the CA
- **Capability tokens**: Grant specific permissions
- **Delegation tokens**: Received from other agents

### AgentClient

The `AgentClient` handles communication with the Agentrust API:

- **authenticate()**: Challenge-response authentication
- **execute()**: Execute protected operations
- **delegate()**: Create delegation tokens

### Token Chain

Operations require a token chain proving permission:

```
[Certificate] → [Capability Token] → [Delegation Token] → ...
```

The SDK automatically builds this chain from the wallet contents.

### Capability Attenuation

When delegating, you can attenuate (restrict) the capability:

- `rows_limit`: Maximum rows to access
- `fields`: Specific fields to return
- `time_window`: Allowed time range

## Exception Handling

```python
from agentrust import (
    AgentClient,
    AuthenticationError,
    PermissionDeniedError,
    TokenExpiredError,
)

try:
    client.authenticate("agent-analyst", "cert-001")
    result = client.execute("read_database", "user_table")
except AuthenticationError:
    print("Authentication failed")
except PermissionDeniedError as e:
    print(f"Permission denied: {e.message}")
except TokenExpiredError:
    print("Token expired, please re-authenticate")
```

## API Reference

### AgentWallet

```python
wallet = AgentWallet(private_key_path="./keys/private.pem")

# Load certificate from registration response
wallet.load_certificate(cert_data)

# Add capability tokens
wallet.add_capability_token(token_data)

# Add delegation tokens received from other agents
wallet.add_delegation_token(delegation_data)

# Sign data (private key never leaves wallet)
signature = wallet.sign({"data": "to sign"})

# List all available capabilities
caps = wallet.list_capabilities()
```

### AgentClient

```python
client = AgentClient(base_url, wallet)

# Authenticate
client.authenticate(agent_id, cert_id)

# Check authentication status
if client.is_authenticated:
    print("Ready to execute")

# Execute operation
result = client.execute(action, resource, params)

# Delegate
delegation = client.delegate(
    to_agent_id, capability, resource_scope,
    attenuations, max_depth, validity_minutes
)

# Revoke certificate (requires manage_agents)
client.revoke_certificate(cert_id, reason)

# Query tokens
tokens = client.get_agent_tokens(agent_id)
```

### FeishuClient

```python
feishu = FeishuClient(client)

# Bitable operations
records = feishu.read_bitable(app_token, table_id, fields, page_size)
feishu.write_bitable(app_token, table_id, records)

# Messaging
feishu.send_message(receive_id, content, msg_type, receive_id_type)
feishu.send_text_message(receive_id, text)

# Documents
content = feishu.read_doc(document_id)
feishu.write_doc(document_id, content, block_id)

# Calendar
events = feishu.read_calendar(calendar_id, start_time, end_time)
meeting = feishu.create_meeting(topic, start_time, end_time, attendees)

# Database (generic)
result = feishu.read_database(table_name, fields, rows_limit)
feishu.write_database(table_name, data)
```

## Demo Scenario

See `examples/demo.py` for a complete demonstration of:

1. Agent registration and certificate issuance
2. Challenge-response authentication
3. Protected resource access
4. Capability delegation with attenuation
5. Cross-agent operation using delegation tokens

## Requirements

- Python 3.9+
- httpx
- cryptography

## License

MIT License
