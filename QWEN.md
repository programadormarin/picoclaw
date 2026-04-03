# PicoClaw - Project Context

## Project Overview

**PicoClaw** is an ultra-lightweight personal AI assistant written in Go, inspired by [nanobot](https://github.com/HKUDS/nanobot). It's designed to run on minimal hardware ($10 boards, <10MB RAM) while providing intelligent AI assistance across multiple channels (Telegram, WhatsApp, Discord, Feishu, LINE, WeCom, QQ, DingTalk, Slack).

### Key Characteristics

- **Ultra-Lightweight**: <10MB memory footprint (99% smaller than Clawdbot)
- **Minimal Cost**: Runs on $10 hardware (98% cheaper than Mac mini)
- **Lightning Fast**: 1-second boot time even on 0.6GHz single-core
- **True Portability**: Single self-contained binary across RISC-V, ARM, and x86
- **AI-Bootstrapped**: 95% agent-generated core with human-in-the-loop refinement

### Architecture

The project follows a modular Go architecture with clear separation of concerns:

```
cmd/picoclaw/          # CLI entry point (Cobra-based)
  internal/            # Internal CLI commands
    agent/             # Agent command (one-shot queries)
    gateway/           # Gateway command (long-running bot)
    onboard/           # Initial setup wizard
    cron/              # Scheduled jobs
    skills/            # Skill management
    auth/              # Authentication
    migrate/           # Configuration migrations
    status/            # Status display
    version/           # Version info

pkg/                   # Reusable packages
  agent/               # Core agent logic and context management
  channels/            # Chat channel integrations (Telegram, Discord, WhatsApp, etc.)
  config/              # Configuration management with env var overrides
  providers/           # LLM provider implementations (OpenAI, Anthropic, Ollama, etc.)
  tools/               # Tool implementations (file ops, shell, web search, etc.)
  skills/              # Skills system (modular capability extensions)
  session/             # Session and conversation management
  memory/              # Long-term memory system
  cron/                # Scheduled task execution
  mcp/                 # Model Context Protocol support
  voice/               # Voice transcription (Groq Whisper)
  devices/             # Device management (USB, etc.)
  heartbeat/           # Periodic task execution
```

## Building and Running

### Prerequisites

- Go 1.25+
- Make
- golangci-lint (for linting)

### Build Commands

```bash
# Download dependencies
make deps

# Build for current platform
make build

# Build for all platforms
make build-all

# Build for specific platforms
make build-linux-arm      # Linux ARMv7 (32-bit)
make build-linux-arm64    # Linux ARM64
make build-pi-zero        # Both ARM variants for Pi Zero 2 W

# Build with WhatsApp native support
make build-whatsapp-native

# Build and install to ~/.local/bin
make install
```

### Run Commands

```bash
# Initialize (first-time setup)
picoclaw onboard

# Run agent (one-shot query)
picoclaw agent -m "What is 2+2?"

# Run gateway (long-running bot)
picoclaw gateway

# Docker (minimal Alpine image)
make docker-build         # Build Docker image
make docker-run           # Run gateway
make docker-run-agent     # Run agent interactively
make docker-run-full      # Run with full MCP support (Node.js)

# Docker Compose directly
docker compose -f docker/docker-compose.yml --profile gateway up
docker compose -f docker/docker-compose.yml run --rm picoclaw-agent -m "Hello"
```

### Testing and Linting

```bash
# Run tests
make test

# Run linter
make lint

# Fix linting issues
make fix

# Format code
make fmt

# Run all checks (deps + fmt + vet + test)
make check
```

### Clean and Uninstall

```bash
make clean                # Remove build artifacts
make uninstall            # Remove from ~/.local/bin
make uninstall-all        # Remove all data
make docker-clean         # Clean Docker images and volumes
```

## Configuration

### Config File Location

- Default: `~/.picoclaw/config.json`
- Override: `PICOCLAW_CONFIG=/path/to/config.json`
- Home override: `PICOCLAW_HOME=/path/to/picoclaw` (default: `~/.picoclaw`)

### Key Configuration Sections

```json
{
  "agents": {
    "defaults": {
      "workspace": "~/.picoclaw/workspace",
      "model_name": "gpt4",
      "max_tokens": 8192,
      "temperature": 0.7,
      "max_tool_iterations": 20
    }
  },
  "model_list": [
    {
      "model_name": "gpt4",
      "model": "openai/gpt-5.2",
      "api_key": "your-api-key"
    }
  ],
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "YOUR_BOT_TOKEN",
      "allow_from": ["YOUR_USER_ID"]
    }
  },
  "tools": {
    "web": {
      "brave": { "enabled": false, "api_key": "..." },
      "tavily": { "enabled": false, "api_key": "..." },
      "duckduckgo": { "enabled": true }
    }
  }
}
```

### Environment Variables (Docker)

For Docker deployments, use these environment variables instead of editing config.json:

```yaml
# Ollama
- PICOCLAW_PROVIDERS_OLLAMA_API_BASE=http://host.docker.internal:11434
- PICOCLAW_AGENTS_DEFAULTS_MODEL_NAME=ollama/llama3.2
- PICOCLAW_AGENTS_DEFAULTS_PROVIDER=ollama

# OpenAI
- OPENAI_API_KEY=sk-xxx
- PICOCLAW_AGENTS_DEFAULTS_MODEL_NAME=openai/gpt-4o
- PICOCLAW_AGENTS_DEFAULTS_PROVIDER=openai
```

## Workspace Layout

```
~/.picoclaw/workspace/
├── sessions/          # Conversation sessions and history
├── memory/            # Long-term memory (MEMORY.md)
├── state/             # Persistent state (last channel, etc.)
├── cron/              # Scheduled jobs database
├── skills/            # Custom skills
├── AGENT.md           # Agent behavior guide
├── HEARTBEAT.md       # Periodic task prompts (checked every 30 min)
├── IDENTITY.md        # Agent identity
├── SOUL.md            # Agent soul
├── TOOLS.md           # Tool descriptions
└── USER.md            # User preferences
```

## Skills System

Skills are modular, self-contained packages that extend the agent's capabilities. They consist of:

```
skill-name/
├── SKILL.md           # Required: Frontmatter + instructions
├── scripts/           # Optional: Executable code (Python/Bash)
├── references/        # Optional: Documentation for context loading
└── assets/            # Optional: Files used in output (templates, icons)
```

### Installed Skills

- **github** - Interact with GitHub using `gh` CLI
- **google-drive** - Manage Google Drive files, folders, and documents
- **hardware** - Hardware-specific knowledge (board pinouts, devices)
- **skill-creator** - Create or update AgentSkills
- **summarize** - Summarization capabilities
- **tmux** - tmux session management
- **weather** - Weather information

### Skill Management Rule

**Important**: When adding or configuring skills in the PicoClaw project, always check and update files in the `docker/data/workspace/` folder hierarchy. Before creating new skills, verify existing sub-folders in `docker/data/workspace/skills/` to avoid duplications and prevent overwhelming other skills. This includes updating `IDENTITY.md` to reflect new capabilities and ensuring skill documentation is consistent across the workspace.

## Development Conventions

### Code Style

- Go standard formatting (gofmt)
- Type hints and modern Go 1.25+ syntax
- Consistent error handling with actionable messages
- Structured logging with timestamps
- JSON output mode for programmatic consumption (`--json` flag)

### Testing Practices

- Unit tests in `_test.go` files alongside source
- Table-driven tests for multiple scenarios
- Mock external dependencies (LLM providers, channels)
- Integration tests for critical paths

### Git Workflow

- Feature branches for new functionality
- PRs for all changes (even small ones)
- Conventional commit messages
- Review required before merge

### Security

- Credential files must have restrictive permissions (0o600)
- No credentials committed to git (enforced by .gitignore)
- Workspace sandboxing by default (`restrict_to_workspace: true`)
- Environment variable-based credential management (no hardcoded secrets)
- OAuth2 token files written with secure permissions

## Docker Deployment

### Dockerfile Structure

Two-stage build:
1. **Builder**: golang:1.25-alpine → compile binary
2. **Runtime**: alpine:3.23 → minimal image with openssh-client, git, github-cli

### Docker Compose Services

- **picoclaw-agent**: One-shot queries (interactive or with `-m` flag)
- **picoclaw-gateway**: Long-running bot with webhook support

### Volumes

- `./data:/root/.picoclaw` - Persistent data (config, workspace, skills)
- `~/.ssh/id_ed25519_github:/root/.ssh/id_ed25519_github:ro` - GitHub SSH key (read-only)

## Key Files

| File | Purpose |
|------|---------|
| `Makefile` | Build, test, install, Docker commands |
| `go.mod` | Go module dependencies |
| `docker/Dockerfile` | Minimal Alpine-based Docker image |
| `docker/docker-compose.yml` | Docker Compose configuration |
| `docker/data/workspace/` | Default workspace with skills and config |
| `.env.example` | Environment variable template |
| `ROADMAP.md` | Project roadmap and volunteer roles |
| `CONTRIBUTING.md` | Contribution guidelines |

## Useful Links

- **Website**: https://picoclaw.io
- **GitHub**: https://github.com/sipeed/picoclaw
- **Issues**: https://github.com/sipeed/picoclaw/issues
- **Discussions**: https://github.com/sipeed/picoclaw/discussions
- **Discord**: https://discord.gg/V4sAZ9XWpN
- **License**: MIT
