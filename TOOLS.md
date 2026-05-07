# OpenCode Tool Ecosystem

## Standard
OpenAI Function Calling format adopted by most providers. Each tool has:
- `name`: Tool identifier
- `description`: What it does  
- `parameters`: JSON Schema object with properties

The Vercel AI SDK normalizes these across providers (OpenAI, Anthropic, Google, etc.)

## Built-in Tools

### Filesystem
- **read** - `filePath`, `offset`, `limit` - Read files/directories
- **write** - `filePath`, `content` - Write files
- **edit** - `filePath`, `oldString`, `newString` - Edit by replacement
- **glob** - `pattern`, `path` - Find files by pattern
- **grep** - `pattern`, `path`, `include` - Search file contents

### Shell
- **shell** (bash) - `command`, `description`, `workdir`, `timeout` - Execute shell commands

### Web
- **webfetch** - `url`, `format`, `timeout` - Fetch URL content
- **websearch** - `query`, `numResults`, `livecrawl`, `type`, `contextMaxCharacters` - Web search

### Agent
- **task** - `description`, `prompt`, `subagent_type`, `task_id` - Run sub-agent tasks
- **skill** - `name` - Load specialized skills

### Utility
- **todowrite** - `todos` - Manage todo lists
- **patch** - Apply code patches via diff format
- **question** - Ask user questions during execution
- **lsp** - Language Server Protocol integration
- **plan** - Create implementation plans without executing
- **invalid** - Catch malformed tool calls

## Custom Tools
Plugins can define additional tools via `Tool.define()` with Zod schemas.
