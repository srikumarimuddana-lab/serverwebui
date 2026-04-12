# Server WebUI — Design Specification

## Overview

A multi-server management platform with a web-based UI for browsing files, running commands via an embedded terminal, viewing live system stats, tailing logs, and managing services. Supports both Linux and Windows servers with two operational modes.

## Operational Modes

### Mode 1: Linux Fleet (Centralized)

A single **Master API** on one Linux server coordinates multiple Linux **Agents**. The Next.js frontend communicates only with the master, which proxies requests to agents over mTLS.

```
Next.js (Vercel) ──HTTPS──► Master API (Linux) ──mTLS──► Agent (Linux 1)
                                                 ──mTLS──► Agent (Linux 2)
                                                 ──mTLS──► Agent (Linux N)
```

### Mode 2: Windows Independent (Standalone)

Each Windows server runs **both master and agent** as a single process. It manages only itself. The Next.js frontend contacts each Windows server directly.

```
Next.js (Vercel) ──HTTPS──► Windows Server 1 (Master+Agent)
                 ──HTTPS──► Windows Server 2 (Master+Agent)
```

### Unified Frontend

The dashboard shows all servers (Linux + Windows) in one view. A routing layer in the frontend directs API calls to the Linux master or directly to independent Windows servers based on the server's configured mode.

---

## Agent Design

Each agent is a lightweight FastAPI service running as a **systemd service** (Linux) or **Windows Service** (Windows). It exposes a uniform REST/WebSocket API regardless of OS.

### Agent API Endpoints

| Category | Endpoint | Description |
|----------|----------|-------------|
| **Files** | `GET /files/{path}` | List directory or download file |
| | `POST /files/{path}` | Upload file |
| | `DELETE /files/{path}` | Delete file/directory |
| | `PUT /files/{path}` | Move/rename |
| **Terminal** | `WS /terminal/open` | Open new PTY session |
| | `WS /terminal/{session_id}` | Attach to session (stdin/stdout) |
| | `POST /terminal/{session_id}/resize` | Resize terminal |
| | `DELETE /terminal/{session_id}` | Kill session |
| **System** | `GET /stats` | CPU, RAM, disk, network usage |
| | `WS /stats/stream` | Live stats via WebSocket |
| **Logs** | `GET /logs/{path}` | Read log file (paginated) |
| | `WS /logs/{path}/tail` | Tail log file in real-time |
| **Services** | `GET /services` | List all services + status |
| | `POST /services/{name}/{action}` | Start/stop/restart a service |
| **Health** | `GET /health` | Agent heartbeat + version |

### Platform Abstraction Layer

The agent detects OS at startup and loads the correct implementation:

| Feature | Linux | Windows |
|---------|-------|---------|
| Runs as | systemd service | Windows Service (NSSM/pywin32) |
| Terminal PTY | `pty` module (built-in) | ConPTY (Windows 10 1809+) |
| Default shell | `bash` | `powershell` |
| System stats | `psutil` | `psutil` |
| Service management | `systemctl` | `sc.exe` / `Get-Service` |
| Cert storage | `/etc/server-agent/certs/` | `C:\ProgramData\server-agent\certs\` |
| Config location | `/etc/server-agent/config.yaml` | `C:\ProgramData\server-agent\config.yaml` |

Agent code structure:

```
agent/
├── platforms/
│   ├── base.py          # Abstract interface
│   ├── linux.py         # Linux implementations
│   └── windows.py       # Windows implementations
├── services/
│   ├── file_manager.py  # Uses platform layer
│   ├── terminal.py      # PTY management (xterm.js backend)
│   ├── stats.py         # psutil (cross-platform)
│   ├── service_mgr.py   # Uses platform layer
│   └── log_reader.py    # File reading with tail
```

---

## Master API Design

Runs on one Linux server. Coordinates the Linux agent fleet and serves as the API backend for the frontend.

### Master API Endpoints

| Category | Endpoint | Description |
|----------|----------|-------------|
| **Auth** | `POST /auth/login` | Login, returns JWT |
| | `POST /auth/refresh` | Refresh token |
| | `POST /auth/logout` | Invalidate session |
| **Users** | `GET /users` | List users (admin only) |
| | `POST /users` | Create user |
| | `PUT /users/{id}/role` | Assign role |
| **Agents** | `GET /agents` | List all agents + status |
| | `POST /agents/register` | Agent registration (one-time token) |
| | `DELETE /agents/{id}` | Revoke agent |
| | `GET /agents/{id}/health` | Check agent health |
| **Proxy** | `* /agents/{id}/files/**` | Proxy file operations to agent |
| | `WS /agents/{id}/terminal` | Proxy terminal WebSocket to agent |
| | `* /agents/{id}/stats/**` | Proxy stats to agent |
| | `* /agents/{id}/logs/**` | Proxy log operations to agent |
| | `* /agents/{id}/services/**` | Proxy service operations to agent |
| **Audit** | `GET /audit` | Query audit log |

### User Roles

- **Admin** — full access: manage users, register/revoke agents, all server operations
- **Operator** — can use terminal, browse files, manage services
- **Viewer** — read-only: view stats, logs, file listings (no terminal, no modifications)

### Database (SQLite initially, PostgreSQL for scale)

Tables:
- `users` — credentials (hashed), roles
- `agents` — hostname, IP, port, certificate fingerprint, status, last_seen
- `registration_tokens` — one-time tokens for agent onboarding
- `audit_logs` — timestamp, user_id, agent_id, action, details

### Windows Standalone Mode

On Windows, the master and agent run as a single combined process. The master API endpoints still exist but only manage the local agent. No agent registry or proxy — all operations are local. Auth and audit still apply.

---

## Security Architecture

### Layer 1 — Frontend to Master (Internet-facing)

- HTTPS only (TLS 1.3)
- JWT access tokens: short-lived (15 min) + refresh tokens (HTTP-only cookie, 7 days)
- CORS locked to the Vercel domain only
- Rate limiting on all endpoints (login: 5 attempts, 15 min lockout)
- CSRF protection via SameSite cookies

### Layer 2 — Master to Agents (Internal network)

- Mutual TLS on every connection
- Private CA generated during setup, signs all certificates
- Certificate revocation from the UI
- Agents only accept connections from the master's certificate

### Layer 3 — Agent Registration Flow

1. Admin generates a one-time registration token from the Web UI
2. Agent is installed and configured with the token
3. Agent presents token to master
4. Master validates token, issues a TLS client certificate to the agent
5. All subsequent communication uses mutual TLS
6. Token is invalidated after use

### Layer 4 — Agent Self-Protection

- **Path whitelist** — configurable allowed directories for file browsing
- **Terminal audit** — every session recorded (user, timestamp, full I/O)
- **Idle timeout** — terminal sessions auto-close after 30 min inactivity
- **Max concurrent sessions** — cap per agent to prevent resource exhaustion
- **Bind to internal IP** — agent listens only on internal network interface

### Layer 5 — Application Level

- Role-based access control (Admin/Operator/Viewer)
- Per-agent user permissions (restrict which users access which servers)
- All actions logged to audit table
- Session invalidation on role change
- Secrets in environment variables only

### Layer 6 — Operational Security

- Agent health monitoring — master pings every 60s, alerts on failure
- All secrets in environment variables, never in code
- Database encryption at rest for audit logs

---

## Frontend Design (Next.js)

### Dashboard

- Server cards: hostname, OS icon (Linux/Windows), status badge, CPU/RAM sparkline
- Color-coded: green = healthy, yellow = high load, red = offline
- Click server → enters server management view

### Server Management View

Tabbed interface, identical for Linux fleet and Windows standalone:

- **Terminal** — xterm.js embedded terminal (PuTTY-like experience), multiple tabs per server
- **Files** — file browser with breadcrumb nav, upload/download, create/delete
- **Stats** — live CPU, RAM, disk, network charts (real-time via WebSocket)
- **Logs** — log file browser with live tail
- **Services** — service list with start/stop/restart and status indicators

### Frontend Routing Logic

```
When user interacts with a server:
  if server.mode == "linux-fleet":
    API base = LINUX_MASTER_URL + /agents/{id}
  if server.mode == "windows-independent":
    API base = WINDOWS_SERVER_URL (direct)
```

UI components are identical — only the API base URL changes.

### Server Configuration

A settings page in the UI where admins add/remove servers, set mode (fleet/independent), and configure connection details.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14+, React, TypeScript, Tailwind CSS |
| Terminal | xterm.js, xterm-addon-fit, xterm-addon-web-links |
| Charts | Recharts or Tremor |
| Frontend deploy | Vercel |
| Master API | Python 3.11+, FastAPI, Uvicorn |
| Agent API | Python 3.11+, FastAPI, Uvicorn |
| Database | SQLite (start), PostgreSQL (scale) |
| ORM | SQLAlchemy |
| System stats | psutil |
| Terminal PTY | pty (Linux), ConPTY (Windows) |
| TLS/Certs | cryptography (Python) for private CA |
| Auth | python-jose (JWT), passlib (password hashing) |
| WebSocket | FastAPI native WebSocket |
| Agent install | systemd (Linux), NSSM/pywin32 (Windows) |

---

## Project Structure

```
server-webui/
├── frontend/                  # Next.js app (Vercel)
│   ├── src/
│   │   ├── app/               # Next.js app router
│   │   ├── components/
│   │   │   ├── dashboard/     # Server cards, status overview
│   │   │   ├── terminal/      # xterm.js terminal component
│   │   │   ├── files/         # File browser
│   │   │   ├── stats/         # Live charts
│   │   │   ├── logs/          # Log viewer
│   │   │   └── services/      # Service manager
│   │   ├── lib/
│   │   │   ├── api.ts         # API client with mode routing
│   │   │   └── auth.ts        # JWT handling
│   │   └── hooks/             # React hooks (WebSocket, etc.)
│   └── package.json
│
├── master/                    # FastAPI master (Linux only)
│   ├── app/
│   │   ├── api/               # Route handlers
│   │   ├── core/              # Auth, config, security
│   │   ├── models/            # DB models (SQLAlchemy)
│   │   ├── services/          # Business logic
│   │   └── websocket/         # WS proxy for terminal/stats
│   ├── certs/                 # Private CA + master certs
│   └── requirements.txt
│
├── agent/                     # Runs on all managed servers
│   ├── app/
│   │   ├── api/               # Agent endpoints
│   │   ├── platforms/         # OS abstraction (base, linux, windows)
│   │   ├── services/          # file_manager, terminal, stats, etc.
│   │   └── core/              # Config, security, mTLS
│   ├── install_linux.sh       # Linux installer (systemd)
│   ├── install_windows.ps1    # Windows installer (Win Service)
│   └── requirements.txt
│
└── docs/
```
