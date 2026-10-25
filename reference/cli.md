# CLI Reference

MCP Hangar provides a comprehensive command-line interface for managing MCP servers.

## Installation

```bash
pip install mcp-hangar
# or
uv pip install mcp-hangar
```

## Synopsis

```bash
mcp-hangar [OPTIONS] COMMAND [ARGS]...
```

## Global Options

These options go before the command name (`mcp-hangar --json status`):

| Option | Short | Type | Default | Env Variable | Description |
| -------- | ------- | ------ | --------- | -------------- | ------------- |
| `--config` | `-c` | PATH | - | `MCP_CONFIG` | Path to config.yaml file, for every command. A command's own flag wins over it, and it wins over `MCP_CONFIG`; see [Default Locations](#default-locations) |
| `--verbose` | `-v` | FLAG | false | - | Show verbose output including debug information |
| `--quiet` | `-q` | FLAG | false | - | Suppress non-essential output |
| `--json` | - | FLAG | false | - | Output in JSON format for scripting |
| `--version` | `-V` | FLAG | - | - | Show version and exit |
| `--install-completion` | - | FLAG | - | - | Install completion for the current shell |
| `--show-completion` | - | FLAG | - | - | Print completion for the current shell |
| `--help` | - | FLAG | - | - | Show help message and exit |

`serve`, `pin`, `config check` and the `approvals` subcommands take a path of
their own and fall back to the global `--config` when it is not given. `init`,
`status`, `add`, `remove` and `why` read the global `--config` (`init` also
takes `--config-path`). Only `auth bootstrap-admin` ignores the global
`--config`: it requires its own.

## Commands

| Command | Description |
| --------- | ------------- |
| [`init`](#init) | Interactive setup wizard |
| [`status`](#status) | Show MCP server health dashboard |
| [`add`](#add) | Add MCP server from registry |
| [`remove`](#remove) | Remove MCP server from configuration |
| [`serve`](#serve) | Start the MCP server |
| [`pin`](#pin) | Compute, write and check tool digest pins |
| [`why`](#why) | Show why calls were refused, from the event store |
| [`approvals`](#approvals) | List, approve and deny calls held for approval |
| [`completion`](#completion) | Generate shell completion scripts |
| [`auth`](#auth) | Manage authentication (bootstrap the initial admin) |
| [`config`](#config) | Validate `config.yaml` without starting a gateway |

---

## init

Interactive setup wizard for MCP Hangar. Guides you through MCP server selection and configuration in under 5 minutes.

### Synopsis

```bash
mcp-hangar init [OPTIONS]
```

### Options

| Option | Short | Type | Default | Description |
| -------- | ------- | ------ | --------- | ------------- |
| `--non-interactive` | `-y` | FLAG | false | Run without prompts, using defaults |
| `--bundle` | `-b` | TEXT | - | MCP server bundle to install: `starter` or `developer` |
| `--servers` | - | TEXT | - | Comma-separated list of MCP servers (alias: `--mcp_servers`) |
| `--config-path` | - | PATH | [the shared rule](#default-locations) | Custom path for config file. Without it, the global `--config`, then `MCP_CONFIG`, then `./config.yaml` if present, then `~/.config/mcp-hangar/config.yaml` |
| `--client` | - | TEXT | detected | Client to point at Hangar; repeatable. `claude-code`, `claude-code-project`, `cursor`, `cursor-project`, `claude-desktop`, `all` |
| `--claude-config` | - | PATH | - | Write this exact client config file instead of the detected ones |
| `--skip-clients` | - | FLAG | false | Do not modify any MCP client config (alias: `--skip-claude`) |
| `--skip-test` | - | FLAG | false | Skip the smoke test. No digest pins are written either — they come from that run |
| `--reset` | - | FLAG | false | Reset existing configuration |
| `--undo` | - | FLAG | false | Put every MCP client config back as it was before `init` first changed it, and stop |
| `--force` | - | FLAG | false | With `--undo`: restore even the files edited since `init` wrote them. Without `--undo` it exits 2 |

### MCP Server Bundles

| Bundle | MCP servers | Use Case |
| -------- | ----------- | ---------- |
| `starter` | filesystem, fetch, memory | General use, getting started |
| `developer` | filesystem, fetch, memory, git | Software development |

### Examples

```bash
# Interactive setup
mcp-hangar init

# Install starter bundle
mcp-hangar init --bundle starter

# Install specific mcp_servers
mcp-hangar init --servers filesystem,fetch,git

# Non-interactive with developer bundle
mcp-hangar init -y --bundle developer

# Custom config location
mcp-hangar init --config-path ~/my-config.yaml

# Point one client, or every detected one, at Hangar
mcp-hangar init -y --client claude-code
mcp-hangar init -y --client all

# Touch no client config
mcp-hangar init --skip-clients

# Put the client configs back as they were before init
mcp-hangar init --undo
```

### What It Does

1. Detects available runtimes (`uvx`, `npx`, container engines)
2. Detects the MCP clients on this machine (Claude Code, Cursor, Claude Desktop)
3. Presents MCP server categories for selection
4. Collects required configuration (API keys, paths)
5. Generates `config.yaml` — with `tool_access.mode: front_door` and an
   `auth.stdio.principal` block
6. Starts each MCP server once to verify it, and **records a digest pin for
   every tool it serves** while it is up, under that server's
   `tool_projection` with `digest_enforcement: block`
7. Writes the Hangar entry into the selected clients, merging it into their
   existing `mcpServers` rather than replacing them
8. Shows what was written, what was tested and what was pinned

With `--skip-test`, step 6 writes no pins — an unverified pin would refuse every
call to a tool nobody digested — and the summary says so instead of reporting a
pass. Run [`pin --write`](#pin) afterwards to add them.

The smoke test starts the servers one after another. Each gets 60 seconds
divided by the number of servers, and never less than 30 seconds.

With `-y`, nothing is asked: servers that need a path or a token are written
without one, and an existing config file is copied to
`config.backup.<timestamp>.yaml` beside it and overwritten. Without
`--bundle` or `--servers`, and when the detected clients list no servers of
their own (those are moved behind Hangar instead), `-y` installs the `starter`
bundle, minus any server whose runtime (`npx` or `uvx`) is missing. Its
`filesystem` server needs a directory: it is written as
`[npx, -y, "@modelcontextprotocol/server-filesystem"]` with none, so its smoke
test fails and the summary reports one server failed. Add the directory to the
end of its `command` and run [`pin --write`](#pin), or pick servers with
`--servers fetch,memory,git`.

### Undo

`init` keeps a copy of each MCP client config it changes, taken before the first
change, under `$XDG_STATE_HOME/mcp-hangar/init-backups` (by default
`~/.local/state/mcp-hangar/init-backups`), with the original file's mode.
`init --undo` writes those copies back, removes the client files `init`
created, and changes nothing else; the Hangar `config.yaml` stays. If a client
file changed since `init` wrote it, `--undo` restores nothing, lists the
changed files and exits 1; `--undo --force` restores them anyway. With nothing to
undo it says so and exits 0.

---

## status

Display health dashboard of all configured MCP servers with real-time updates.

### Synopsis

```bash
mcp-hangar status [OPTIONS] [SERVER]
```

### Arguments

| Argument | Required | Description |
| ---------- | ---------- | ------------- |
| `SERVER` | No | Show detailed status for specific MCP server |

### Options

| Option | Short | Type | Default | Description |
| -------- | ------- | ------ | --------- | ------------- |
| `--watch` | `-w` | FLAG | false | Continuously update the display |
| `--interval` | `-i` | FLOAT | 2.0 | Update interval in seconds (with --watch) |
| `--details` | `-d` | FLAG | false | Show additional columns (mode, memory, uptime) |

### MCP Server States

| State | Indicator | Description |
| ------- | ----------- | ------------- |
| READY | `OK` (green) | MCP Server is running and healthy |
| COLD | `--` (dim) | MCP Server not started |
| INITIALIZING | `..` (cyan) | MCP Server starting up |
| DEGRADED | `!!` (yellow) | MCP Server has issues |
| DEAD | `XX` (red) | MCP Server failed/crashed |

### Examples

```bash
# Show all mcp_servers
mcp-hangar status

# Watch mode with live updates
mcp-hangar status --watch

# Faster refresh rate
mcp-hangar status -w -i 0.5

# Show detailed information
mcp-hangar status --details

# Single mcp_server details
mcp-hangar status fetch

# JSON output for scripting
mcp-hangar --json status
```

### Output Columns

**Standard view:**

- MCP Server name
- State indicator
- Health
- Tools count

**Detailed view (`--details`)** adds:

- Mode (subprocess/docker/remote)
- Memory usage
- Uptime
- Last used

---

## add

Add a MCP server from the MCP Registry to your configuration.

### Synopsis

```bash
mcp-hangar add [OPTIONS] NAME
```

### Arguments

| Argument | Required | Description |
| ---------- | ---------- | ------------- |
| `NAME` | Yes | MCP Server name or search query |

### Options

| Option | Short | Type | Default | Description |
| -------- | ------- | ------ | --------- | ------------- |
| `--search` | `-s` | FLAG | false | Search registry instead of exact match |
| `--yes` | `-y` | FLAG | false | Skip confirmation prompts |
| `--no-reload` | - | FLAG | false | Don't hot-reload running server |
| `--replace` | - | FLAG | false | Replace a server the config already has, dropping what the registry entry lacks (pins, `env`, args) |

### Available MCP servers

| MCP Server | Package | Description | Requires Config |
| ---------- | ------- | ------------- | ----------------- |
| `filesystem` | `@modelcontextprotocol/server-filesystem` (npx) | Read and write local files | Yes (a directory) |
| `fetch` | `mcp-server-fetch` (uvx) | Make HTTP requests to fetch web content | No |
| `memory` | `@modelcontextprotocol/server-memory` (npx) | Persistent key-value storage for context | No |
| `git` | `mcp-server-git` (uvx) | Local git operations | No |

The registry is a fixed list of these four. `github`, `postgres`, `slack`,
`puppeteer`, `brave-search`, `google-maps` and `sqlite` were removed because
their packages are no longer maintained or are not published by the project
they are named after; see [The official MCP servers](../guides/OFFICIAL_SERVERS.md).
A name that is not in the list installs nothing and exits 1. For anything
outside the list, add the server to `config.yaml` yourself.

### Adding a server the config already has

*Since 2.34.2* `add` does not overwrite an entry the file already has:

- if the entry is exactly what `add` would write, it says so and exits 0, so a
  script can run `add` again safely;
- otherwise it exits 1 and lists the keys the replacement would drop or change.

`--replace` writes the registry entry over the existing one, dropping its pins,
policy, args and `env`. Before 2.34.2 every `add` did that, without a word.

### Examples

```bash
# Add by exact name
mcp-hangar add git

# Search names and descriptions
mcp-hangar add --search fetch

# Skip confirmation
mcp-hangar add filesystem -y

# Add without hot-reload
mcp-hangar add memory --no-reload

# Overwrite an entry the config already has
mcp-hangar add git --replace
```

### Configuration Prompts

When adding a MCP server that requires configuration, you'll be prompted for:

- **Secrets** (API keys, tokens): Hidden input. From core 2.29.0 the value is not written to the config file: the entry holds a `${NAME}` reference, `add` says which variable to set, and the file is created with mode `0600`. Before 2.29.0 the typed value was written into the file in clear text.
- **Paths** (directories, files): Path validation
- **Text** (URLs, names): Standard input

If the variable a server reads is already set in the environment, you are
asked whether to use it instead. None of the four entries in today's registry
takes a secret; `filesystem` asks for a directory.

With `-y` no prompt is shown, so a server that needs configuration is added
without it. `add` rewrites the config file through PyYAML, which keeps values
but not comments.

---

## remove

Remove a MCP server from your configuration.

### Synopsis

```bash
mcp-hangar remove [OPTIONS] NAME
```

### Arguments

| Argument | Required | Description |
| ---------- | ---------- | ------------- |
| `NAME` | Yes | MCP Server name to remove |

### Options

| Option | Short | Type | Default | Description |
| -------- | ------- | ------ | --------- | ------------- |
| `--yes` | `-y` | FLAG | false | Skip confirmation prompt |
| `--keep-running` | - | FLAG | false | Don't stop running MCP server instance |

### Examples

```bash
# Remove with confirmation
mcp-hangar remove git

# Remove without confirmation
mcp-hangar remove filesystem -y

# Remove from config but keep running
mcp-hangar remove memory --keep-running
```

### Behavior

1. Validates MCP server exists in configuration
2. Prompts for confirmation (unless `-y`)
3. Stops running instance (unless `--keep-running`)
4. Removes from config.yaml

---

## serve

Start the MCP Hangar server. This is the default command when no subcommand is specified.

### Synopsis

```bash
mcp-hangar serve [OPTIONS]
# or simply:
mcp-hangar [OPTIONS]
```

Bare `mcp-hangar` accepts only the [global options](#global-options); pass
`--http`, `--port` and the rest to `mcp-hangar serve`.

### Options

| Option | Short | Type | Default | Env Variable | Description |
| -------- | ------- | ------ | --------- | -------------- | ------------- |
| `--config` | `-c` | PATH | [the shared rule](#default-locations) | - | Path to config.yaml file. Overrides the global `--config`, which overrides `MCP_CONFIG` |
| `--http` | - | FLAG | false | `MCP_MODE=http` | Run in HTTP mode |
| `--host` | - | TEXT | 127.0.0.1 | `MCP_HTTP_HOST` | HTTP server host. A non-loopback host needs authentication |
| `--port` | `-p` | INT | 8000 | `MCP_HTTP_PORT` | HTTP server port |
| `--log-file` | - | PATH | - | - | Path to log file |
| `--log-level` | - | TEXT | INFO | `MCP_LOG_LEVEL` | Log level |
| `--json-logs` | - | FLAG | false | `MCP_JSON_LOGS` | Format logs as JSON |
| `--unsafe-no-auth` | - | FLAG | false | - | Allow non-loopback HTTP binding without authentication (unsafe) |

### Transport Modes

**stdio (default)**

JSON-RPC over stdin/stdout. Used by Claude Desktop and similar clients.

```bash
mcp-hangar serve
mcp-hangar --config config.yaml serve
```

**HTTP**

HTTP server with Streamable HTTP transport. Used by LM Studio and web clients.

```bash
mcp-hangar serve --http
mcp-hangar serve --http --port 9000
mcp-hangar serve --http --host 127.0.0.1 --port 8080
```

> **Binding a non-loopback host requires authentication.** The default host is
> `127.0.0.1` (since 2.29.0; it was `0.0.0.0` before). When `--host` is set to anything other than a loopback address
> (for example `0.0.0.0`), Hangar refuses to start, exiting 1 with
> `http_auth_required_for_non_loopback`, unless authentication is configured
> (`auth`) or the `--unsafe-no-auth` flag is passed to explicitly accept an
> unauthenticated listener. A loopback bind, the default, is exempt. This prevents
> accidentally exposing an unauthenticated gateway on a routable interface.

### HTTP Endpoints

When running in HTTP mode:

| Endpoint | Method | Description |
| ---------- | -------- | ------------- |
| `/mcp` | POST/GET | MCP protocol endpoint (`GET` is served with `tool_access.mode: front_door`; otherwise it answers 405) |
| `/health/live` | GET | Liveness probe |
| `/health/ready` | GET | Readiness probe |
| `/health/startup` | GET | Startup probe |
| `/metrics` | GET | Prometheus metrics |

### Log Levels

- `DEBUG` - Detailed debugging information
- `INFO` - General operational information (default)
- `WARNING` - Warning messages
- `ERROR` - Error messages only
- `CRITICAL` - Critical errors only

### Examples

```bash
# stdio mode (for Claude Desktop)
mcp-hangar serve

# HTTP mode on default port
mcp-hangar serve --http

# HTTP mode with custom port
mcp-hangar serve --http -p 9000

# With debug logging
mcp-hangar serve --log-level DEBUG

# With log file
mcp-hangar serve --log-file /var/log/mcp-hangar.log

# JSON logs for log aggregation
mcp-hangar serve --json-logs

# Full production setup (a non-loopback host needs auth configured)
mcp-hangar serve --http --host 0.0.0.0 --port 8000 \
  --log-level INFO --json-logs --log-file /var/log/mcp.log
```

---

## pin

Compute the digest of every tool your MCP servers serve, write those digests
into the configuration, or check the configuration against what the servers
serve right now.

A pin is the SHA-256 of a tool's `name`, `description`, `inputSchema` and
`outputSchema`, canonicalized per RFC 8785. When `digest_enforcement` is `block`
(the default), a tool whose digest no longer matches its pin is refused before
the upstream is asked. What the client sees depends on the tool surface:

- With `tool_access.mode: front_door`, the configuration `init` writes, the tool
  is withheld from `tools/list`, and a call to it answers the same error as a
  name that does not exist:

  ```text
  Tool 'fetch' not found
  ```

- Through `hangar_call`, the call answers
  `Tool 'fetch' schema does not match its pinned digest`.

Either way the refusal is recorded in the event store with both digests, and
[`mcp-hangar why`](#why) shows it.

Because the description is part of the digest, a poisoned description that
changes no parameter is caught.

### Synopsis

```bash
mcp-hangar pin [OPTIONS]
```

### Options

| Option | Short | Type | Default | Description |
| -------- | ------- | ------ | --------- | ------------- |
| `--config` | `-c` | PATH | [the shared rule](#default-locations) | Configuration to read (and, with `--write`, to update) |
| `--server` | `-s` | TEXT | every server | Only this MCP server. Repeatable |
| `--write` | - | FLAG | false | Merge the observed digests into `mcp_servers.<id>.tool_projection.pins`. Never into a group |
| `--check` | - | FLAG | false | Exit 1 when a configured pin disagrees with what the server serves |
| `--json` | - | FLAG | false | Machine-readable output |
| `--log-level` | - | TEXT | INFO | Log level; overrides the config file's `logging.level`. Env: `MCP_LOG_LEVEL` |
| `--quiet` | `-q` | FLAG | false | Log errors only, and print only digests, drift and failures |

`--write` and `--check` ask different questions; pass one or neither.
`pin` reads its own `--config`, then the global one, so `mcp-hangar --config X pin`
and `mcp-hangar pin --config X` read the same file. Before 2.25.0 `pin` ignored
the global `--config`
([mcp-hangar#1682](https://github.com/mcp-hangar/mcp-hangar/issues/1682)).

### Exit Codes

| Code | Meaning |
| ------ | --------- |
| 0 | The pins and the servers agree, or the write succeeded |
| 1 | Drift: at least one pinned tool no longer matches (`--check` only) |
| 2 | The question could not be answered — no such config, unreadable YAML, unknown `--server`, or a server that never started |

### Examples

```bash
# What would I pin?
mcp-hangar pin

# Pin everything, in place
mcp-hangar pin --write

# Pin one server only
mcp-hangar pin --server fetch --write

# Has anything changed since? (exit 1 if yes)
mcp-hangar pin --check

# In a script
mcp-hangar pin --check --json
```

### In CI or a pre-commit hook

```yaml
# .pre-commit-config.yaml
- repo: local
  hooks:
    - id: mcp-hangar-pin-check
      name: MCP tool schemas have not drifted
      entry: mcp-hangar pin --check
      language: system
      pass_filenames: false
```

### Notes

- `pin` starts the servers your configuration describes, asks each for its
  tools, and stops it again. A tool list is what a server answers, not something
  the configuration knows.
- `--write` rewrites the configuration file through PyYAML, which preserves
  values but **not comments or key order**. The previous file is kept beside it
  as `<config>.bak`, with the configuration file's mode. Bare `mcp-hangar pin`
  prints the same digests if you would rather paste them into a file you
  maintain by hand.
- Only the all-tenants `tool_projection.pins` block is written and checked. Pins
  under `tenant_overrides` are left alone.
- A `mode: group` entry is never started; its members are asked instead.
  *Since 2.34.2* `--check` holds the pins a group declares under its own
  `tool_projection.pins` against every member that serves the tool, and reports
  a mismatch as `drift <group>.<tool> (member <id>)`; `--json` adds a `member`
  key to such an entry. A pinned tool no member serves is drift. `--write` does
  not write pins into a group: a group pin holds for every member, so refresh it
  by hand. `--server <group>` asks that group's members; `--server <member>`
  checks only that member's own pins. Before 2.34.2 any configuration with a
  group made every `pin` run exit 2.
- A tool that is served but not pinned is not drift — `pins` is a subset by
  design. A pinned tool that is no longer served **is**.

---

## why

Show why calls were refused: the gate, the reason and, for a digest mismatch,
both digests. It reads the SQLite event store without writing to it, so it works
while a gateway your client started has the store open.

### Synopsis

```bash
mcp-hangar why [OPTIONS] [EVENT_ID]
```

### Arguments

| Argument | Required | Description |
| ---------- | ---------- | ------------- |
| `EVENT_ID` | No | Show one refusal in full. The first characters of the id are enough |

### Options

| Option | Short | Type | Default | Description |
| -------- | ------- | ------ | --------- | ------------- |
| `--last` | `-n` | INT | 10 | How many of the latest refusals to show |
| `--server` | `-s` | TEXT | - | Only refusals for this server |
| `--tool` | `-t` | TEXT | - | Show the history of this tool's pin instead: each pin recorded or revoked |
| `--db` | - | PATH | - | Read this event store file instead of the one the config names |

`why` has no `--config` of its own: it reads the global one
(`mcp-hangar --config X why`), then follows
[the shared rule](#default-locations). The store is `--db` if given, else the
SQLite event store the configuration names (`event_store.path`, or
`persistence.sqlite` with `persistence.backend: sqlite`), else the one `init`
puts under `$XDG_STATE_HOME/mcp-hangar`.

It lists `ToolCallRefused`, `DigestMismatchEvent`, `ToolApprovalDenied`,
`ToolApprovalExpired` and `ToolApprovalCancelled` events, and a call refused
because an upstream presented a key its pin list does not hold. It exits 0, also
when nothing was refused, and 1 when the store cannot be read: a PostgreSQL
backend, a disabled or in-memory event store, or a file that is not YAML.

### Examples

```bash
# The latest ten refusals
mcp-hangar why

# The latest one, for one server
mcp-hangar why --last 1 --server filesystem

# One refusal in full
mcp-hangar why 3f2a9c1b

# Each pin recorded for a tool
mcp-hangar why --tool read_file
```

---

## approvals

List and resolve calls held by an `approval_list`, from a second process. A
stdio gateway serves no REST API, so this is how a hold on it is decided. The
command writes the decision to the approval store the gateway shares; the
waiting gateway reads it and releases or refuses the call.

### Synopsis

```bash
mcp-hangar approvals list [--state STATE] [--config PATH] [--db PATH]
mcp-hangar approvals approve APPROVAL_ID [--reason TEXT] [--config PATH] [--db PATH]
mcp-hangar approvals deny APPROVAL_ID [--reason TEXT] [--config PATH] [--db PATH]
```

### Options

| Option | Short | Type | Default | Description |
| -------- | ------- | ------ | --------- | ------------- |
| `--config` | `-c` | PATH | [the shared rule](#default-locations) | The gateway's `config.yaml`. Falls back to the global `--config` |
| `--db` | - | PATH | - | Use this SQLite approval store instead of the configuration's |
| `--state` | - | TEXT | `pending` | `list` only: `pending`, `approved`, `denied`, `expired` or `cancelled` |
| `--reason` | `-r` | TEXT | - | `approve`/`deny` only: why, recorded with the decision |

`APPROVAL_ID` is the full id or a unique prefix of a pending one.

### Who decides

The approver is the configuration's `auth.stdio.principal`, and nobody else.
A configuration without one is refused. Its declared roles decide whether auth
is on or off: they must hold `approval:resolve` (`provider-admin` or `admin`).
`viewer`, the role `init` declares, does not, so resolving with the
configuration `init` wrote is refused until you add one of those roles. The
listing shows approvals with no tenant and those of the principal's tenant.

### Where the store is

`--db` if given; with `persistence.backend: sqlite`, the database under
`persistence.sqlite`; with `persistence.backend: postgresql`, that backend;
otherwise `mcp_hangar.db` in the directory of `event_store.path`. That path
must be absolute, as `init` writes it: a relative one would resolve against the
gateway's working directory, which this command cannot know, so it is refused.

The command exits 0 on success and 1 on any refusal: no principal, a role
without `approval:resolve`, no store, an unknown or ambiguous id, or an approval
that already expired or was decided.

---

## completion

Generate shell completion scripts for tab-completion support.

### Synopsis

```bash
mcp-hangar completion COMMAND
```

### Subcommands

| Command | Description |
| --------- | ------------- |
| `bash` | Generate bash completion script |
| `zsh` | Generate zsh completion script |
| `fish` | Generate fish completion script |
| `install` | Auto-install completion for detected shell |

### Installation

**Bash**

```bash
# System-wide
mcp-hangar completion bash | sudo tee /etc/bash_completion.d/mcp-hangar

# User-only
mcp-hangar completion bash >> ~/.bashrc
```

**Zsh**

```bash
# Add to fpath
mcp-hangar completion zsh > ~/.zfunc/_mcp-hangar

# Add to .zshrc if not already present:
# fpath=(~/.zfunc $fpath)
# autoload -Uz compinit && compinit
```

**Fish**

```bash
mcp-hangar completion fish > ~/.config/fish/completions/mcp-hangar.fish
```

**Auto-install**

```bash
# Detect shell and install
mcp-hangar completion install

# Specify shell
mcp-hangar completion install zsh
```

---

## auth

Authentication management. Currently exposes a one-time administrator bootstrap.

### auth bootstrap-admin

Grant the one-time global `admin` role to an existing principal, using the
server's own durable auth backend. Solves the chicken-and-egg problem where a
fresh durable auth store with anonymous access disabled cannot create its first
administrator through the protected API. Added in 1.5.0.

The claim also mints an API key for that principal. Whether its secret is
printed is `--show-key`'s decision, and the claim succeeds exactly once, so it
is a decision to make before running the command rather than after.

#### Synopsis

```
mcp-hangar auth bootstrap-admin --config PATH --principal PRINCIPAL [OPTIONS]
```

#### Options

| Option | Description |
| -------- | ------------- |
| `--config PATH`, `-c` | Required. Path to the server `config.yaml` whose durable auth backend to bootstrap. |
| `--principal PRINCIPAL` | Required. Existing external principal to grant global admin (e.g. `user:admin`). |
| `--key-name NAME` | Human-readable label recorded for the bootstrap key. Default: `initial admin`. |
| `--show-key` | Print the minted API key's secret. Required when API keys are the only authenticator. Off by default. *Since 2.5.0.* |

#### Behavior

- Uses the same durable backend the server uses (never an in-memory store); the
  claim is a single atomic operation.
- **Fails closed** when `auth.enabled` is false, `allow_anonymous` is true, or the
  storage driver is non-durable (`memory` / `event_sourcing`).
- A second run is refused without mutating storage — exactly one bootstrap
  succeeds.
- Grants a global `admin` role to the principal, and mints an API key for it as
  part of the same claim. The key is stored hashed; its secret is printed only
  with `--show-key`, and is not recoverable afterwards. The grant is auditable.
- *Since 2.5.0:* **omitting `--show-key` is refused when no OIDC issuer is
  configured**, before the claim is spent. API keys are then the only way in, so
  a run that withheld the secret would leave an admin nobody could present and a
  claim that cannot be made again. The refusal names the flag while re-running
  still works.
- *Since 2.5.0:* a configuration with no authenticator at all — API keys
  disabled and no trusted issuer — is refused on the same grounds.
- `--show-key` with `auth.api_key.enabled: false` is refused: no
  authenticator would accept the printed secret.

#### Example

An OIDC deployment: the principal authenticates on its own identity, so no
secret is needed.

```bash
mcp-hangar auth bootstrap-admin --config /etc/mcp-hangar/config.yaml --principal user:alice@example.com
```

A deployment authenticated by API keys. Capture the secret from this run — there
is no second one:

```bash
mcp-hangar auth bootstrap-admin --config /etc/mcp-hangar/config.yaml \
  --principal service:my-app --show-key
```

---

## config

Answer "is this configuration valid" without starting a gateway.

### `config check`

```bash
mcp-hangar config check [PATH]
```

Reports every key that Hangar does not read, and every value the boot would
refuse. A key it does not read is kept and ignored, so the setting simply does
not apply -- which is why a misspelling surfaces as a server that will not
start, or as authentication that is quietly off, rather than as a configuration
error.

`PATH` wins; without it the command reads the global `--config`, then follows
[the shared rule](#default-locations). Before 2.25.0 the global `--config` was
not read here.

| exit code | meaning |
| --- | --- |
| `0` | every key is one Hangar reads and every checked value is accepted |
| `1` | at least one key is not, or a value the boot refuses |
| `2` | the file is missing, is not YAML, or is not a mapping |

```console
$ mcp-hangar config check config.yaml
FAIL config.yaml: 2 key(s) nothing reads:

  auth has unknown key(s) ['enabledd']; allowed keys: ['allow_anonymous',
  'api_key', 'enabled', 'oidc', 'opa', 'rate_limit', 'role_assignments', 'stdio',
  'storage']
  mcp_servers.math has unknown key(s) ['commandd']; allowed keys: [...]
```

The command is always strict. Loading a config only **warns** about an unknown
key today -- see [Unknown keys](configuration.md#unknown-keys) for what changes
in 3.0.0 -- but this command exists to be asked the question directly, so it
answers it. That makes it the thing to run in CI, and before a rollout.

Keys checked: top-level section names, the direct keys of each section, and the
keys of an `mcp_servers.<id>` spec. Not checked: anything deeper.

*Since 2.28.0, widened in 2.29.0,* values are checked too, by the checks the boot and a reload run
without starting anything: `pin_recheck_interval_s`, the process-wide sections,
each server's `max_consecutive_failures`, and the `mcp_servers` section built as
a reload builds it. A value the loader only warns about and replaces with a
default is not reported. A refused value is listed under its own heading:

```console
$ mcp-hangar config check config.yaml
FAIL config.yaml: 1 value(s) the gateway refuses at boot:

  mcp_server 'mock': max_consecutive_failures 500: MaxConsecutiveFailures cannot exceed 100 (allowed 1-100)
```

---

## Configuration File

### Default Locations

*Since 2.25.0* `init`, `status`, `add`, `remove`, `pin`, `serve`, a bare
`mcp-hangar`, `config check` and `python -m mcp_hangar.server` find the
configuration file by one rule, highest first
([mcp-hangar#1657](https://github.com/mcp-hangar/mcp-hangar/issues/1657)):

1. a path on the command line -- the command's own flag or argument
   (`serve --config`, `pin --config`, `approvals ... --config`,
   `init --config-path`, `config check PATH`), then the global `--config`;
2. `$MCP_CONFIG`;
3. `./config.yaml`, if the working directory has one;
4. `~/.config/mcp-hangar/config.yaml`, the file `init` writes.

`auth bootstrap-admin` takes its own required `--config`.

So a bare `mcp-hangar serve` after `init` serves the file `init` wrote, unless
the working directory has a `config.yaml` of its own -- and then `init`, `add`
and `remove` there use that file too: `add` and `remove` edit it in place, and
`init -y` backs it up and replaces it. Run them where `config.yaml` is
Hangar's, or name the file (`--config ~/.config/mcp-hangar/config.yaml`, or
`init --config-path`) to keep the old target. A gateway started without `--config` reloads the
file it booted from. If no rule finds a file, `serve` refuses to start and tells
you to run `mcp-hangar init` *(2.25.0)*. A path named by a flag or by
`MCP_CONFIG` that does not exist, is a directory or is not readable is refused
the same way, with the path and where it came from on stderr, for example:

```text
Error: Configuration file /etc/hangar/confg.yaml (named on the command line) does not exist. Nothing is served without the configuration that was asked for.
```

Before 2.25.0 every one of those cases booted a built-in demo configuration
(`math_subprocess` and every `hangar_*` tool, with none of your pins, policies
or auth) and logged only `config_not_found_using_default` at INFO.

Before 2.25.0 each command picked its own default: `serve`, `pin` and
`config check` read `./config.yaml`, `init`, `add` and `remove` wrote
`~/.config/mcp-hangar/config.yaml`, `MCP_CONFIG` beat a global `--config` on
`serve`, and a gateway started without a path could not reload.

### Example Configuration

```yaml
mcp_servers:
  filesystem:
    mode: subprocess
    command:
      - npx
      - -y
      - "@modelcontextprotocol/server-filesystem"
      - "/home/user/documents"

  git:
    mode: subprocess
    command:
      - uvx
      - mcp-server-git

  my-api:
    mode: remote
    endpoint: https://api.example.com/mcp

logging:
  level: INFO
  json_format: false

event_store:
  enabled: true
  driver: sqlite
  path: data/events.db
```

---

## Environment Variables

| Variable | Description | Default |
| ---------- | ------------- | --------- |
| `MCP_CONFIG` | Path to configuration file | - |
| `MCP_MODE` | Server mode (`stdio` or `http`) | `stdio` |
| `MCP_HTTP_HOST` | HTTP server host | `127.0.0.1` |
| `MCP_HTTP_PORT` | HTTP server port | `8000` |
| `MCP_LOG_LEVEL` | Log level | `INFO` |
| `MCP_JSON_LOGS` | Enable JSON logging | `false` |

---

## Exit Codes

| Code | Meaning |
| ------ | --------- |
| 0 | Success |
| 1 | User error (invalid input, missing file, permission denied), or a refusal |
| 2 | System error (network failure, MCP server crash), or a usage error (unknown command or option) |
| 130 | Interrupted by user (Ctrl+C) |

Some commands use these codes more narrowly; their own sections say how:

- `pin` and `config check` exit 1 for drift or an invalid configuration, and 2
  when the question cannot be answered, a missing configuration file included.
- `serve` exits 1 when the configuration file it was asked for is missing.
- `init --force` without `--undo` exits 2.
- `status <server>` for a server that is not configured prints
  `MCP server '<server>' not found` and exits 0.

---

## See Also

- [Quick Start Guide](../getting-started/quickstart.md)
- [HTTP Transport Guide](../guides/HTTP_TRANSPORT.md)
