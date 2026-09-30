# Banking MCP Server

A teaching-oriented banking system built with Python, PostgreSQL, SQLAlchemy, and
the MCP Python SDK.

The project deliberately separates read and write capabilities:

```text
MCP Client
├── FastMCP Read Server
└── Low-Level Write Server
        │
        └── Shared Services → Shared Repositories → PostgreSQL
```

The LLM is not part of either server. An MCP client discovers tools, sends
typed arguments, and returns structured results to the LLM application.

The optional Ollama integration adds the LLM above the MCP client:

```text
Mistral 7B via Ollama
    ↓ chooses tools
Ollama agent / MCP client
    ↓
Read and write MCP servers
```

## SDK Version

The project targets `mcp>=1.30,<2.0`.

The current MCP SDK v2 line renamed `FastMCP` to `MCPServer`. This project
keeps the v1 compatibility line because the read server is intentionally built
with `FastMCP`, while the write server uses the low-level `Server` API.

## Project Layers

```text
servers/
    read_server.py       Safe read-only FastMCP tools
    write_server.py      Explicit low-level write handlers

services/
    *_service.py         Business rules and application errors
    write_service.py     Transactional mutations and audit records

repositories/
    *_repository.py      SQLAlchemy data access only

database/
    models.py            Customers, accounts, transactions, audit logs
    connection.py        PostgreSQL engine and environment configuration
    initialize.py        Excel-to-PostgreSQL import, one table per sheet

security/
    authentication.py    Process-level write authentication adapter
    authorization.py     Role and confirmation checks

audit/
    audit_logger.py      Structured mutation audit records
```

## Setup

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in the PostgreSQL fields. The `.env`
file is ignored by Git and loaded automatically at startup. PostgreSQL is used
when `DATABASE_URL` or `POSTGRES_PASSWORD` is configured; without either, the
test/dev fallback is the ignored local SQLite file.

The original workbook is located at:

```text
dataset/banking_dataset_final.xlsx
```

Initialize or refresh the PostgreSQL database:

```powershell
python -m database.initialize
```

This imports 50 customers, 75 accounts, and 4,500 transactions. `Sheet01`,
`Sheet02`, and `Sheet3` are imported into separate `customers`, `accounts`, and
`transactions` tables. The import replaces those three tables’ rows inside one
transaction, so use it for initial dataset loading or deliberate dataset
refreshes, not as a production migration mechanism.

## Run the Read Server

The read server uses MCP `stdio` transport. Do not run it in an interactive
PowerShell window and type into it: it expects JSON-RPC messages from an MCP
client on stdin. Use the dual client below or configure this module in an MCP
host/Inspector.

```powershell
python -m servers.read_server
```

This command is the server process command an MCP host should launch. The read
server exposes customer, account, transaction, and summary tools. It does not
mutate data.

## Run the Write Server

Configure the authorization role first. Do not commit real secrets. Every
write tool call must also include the admin `email` and `password`; these are
checked against the `Admin_details` table on every request.

```powershell
$env:BANKING_WRITE_ROLE="writer"
python -m servers.write_server
```

The write server also uses `stdio`; launch it through an MCP client or host,
not as an interactive command that receives ordinary text.

When using the Ollama agent, set these variables in the same PowerShell window
before starting the agent. The MCP write subprocess inherits that environment:

```powershell
$env:BANKING_WRITE_ROLE="writer"
python -m llm.ollama_agent
```

The current write surface supports creating, updating, and deleting
transactions. It does not currently expose an account-balance update tool.

Roles:

- `writer`: create and update transactions
- `admin`: create, update, and delete transactions

Deletion requires the exact confirmation value `CONFIRM_DELETE`.

The write authentication query matches `Admin_details.email` and verifies the
provided password against `Admin_details.password`. Use hashed passwords in
production and protect the MCP transport; credentials are never written to
audit logs.

## Run the Dual Client Demo

```powershell
python -m clients.dual_client
```

The demo starts both MCP servers as separate subprocesses, initializes two
independent MCP sessions, discovers their tools, and calls the read server's
`get_account_summary` tool.

## Run Mistral with Ollama

Install and start Ollama, then download the local model:

```powershell
ollama serve
ollama pull mistral:latest
The default model tag is `mistral:latest`, which is the tag used by the local
installation in this project. Override it with `OLLAMA_MODEL` when needed.
```

In another PowerShell window, ask a banking question:

```powershell
python -m llm.ollama_agent
```

The agent sends MCP tool schemas to Mistral, executes the selected tool through
the appropriate MCP server, and sends the structured result back to Mistral.
Mistral never receives direct database access. Set `OLLAMA_HOST` only when the
Ollama service is running somewhere other than `http://localhost:11434`.

For write requests, configure the write-server environment variables described
above. Destructive operations still require the server's explicit confirmation
value; the model is not a security boundary.

## Test

```powershell
pytest -q
```

The tests cover:

- Repository reads
- Service summaries and validation
- FastMCP tool registration and read errors
- Low-level write authentication, authorization, confirmation, rollback, and audit logging
- Dual-server MCP client discovery and calls

## Database Model

```text
customers 1 ─── N accounts 1 ─── N transactions

audit_logs records successful and failed write attempts.
```

Primary keys are `customer_id`, `account_id`, and `transaction_id`. Foreign
keys are enforced by PostgreSQL. Monetary values are stored as fixed-scale numeric
values and serialized as decimal strings at the MCP boundary to avoid floating
point precision loss.

## Important Boundaries

- Repositories do not contain business decisions.
- Services do not know about MCP transport details.
- MCP tools do not execute arbitrary SQL.
- The read server cannot call write operations.
- The write service commits the mutation and success audit record together.
- Failed mutations are rolled back and recorded as failed audit attempts when
  an authenticated principal is available.