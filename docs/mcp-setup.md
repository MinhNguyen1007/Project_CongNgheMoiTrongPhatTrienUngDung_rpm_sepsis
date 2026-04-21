# MCP Setup (Model Context Protocol)

MCP cho phép Claude Code truy cập tài nguyên ngoài (filesystem, GitHub, DB) qua giao thức chuẩn. Dùng khi muốn Claude:

- List issue/PR GitHub mà không cần gọi `gh` qua shell.
- Query DB trực tiếp (debug alerts table, MLflow runs).
- Truy cập filesystem ngoài workspace (vd dataset lưu ở `D:/datasets/`).

## Cài đặt

### 1. Copy file example

```bash
cp .claude/mcp.example.json .claude/mcp.json
```

File `.claude/mcp.json` **không commit** (đã có trong `.gitignore`).

### 2. Enable từng server

#### Filesystem

Mặc định bật, trỏ vào project root. Đổi path nếu cần.

#### GitHub

1. Tạo Personal Access Token ở https://github.com/settings/tokens
2. Scope cần: `repo` (PR/issue), `read:org` (nếu repo ở org).
3. Paste token vào `env.GITHUB_PERSONAL_ACCESS_TOKEN`.

#### Postgres

1. Đảm bảo `docker-compose up -d postgres` đã chạy.
2. Đổi connection string thành user/password thật trong `docker-compose.yml`.
3. Chỉ expose read-only user để Claude không accidentally DROP.

#### SQLite (MLflow offline)

Nếu dùng MLflow với SQLite backend, trỏ `--db-path` tới `./data/mlflow.db`.

### 3. Restart Claude Code

MCP config load khi Claude Code khởi động. Sau khi sửa `mcp.json`, restart IDE extension hoặc CLI.

### 4. Verify

Trong Claude Code:

```
/mcp list
```

Phải thấy các server status `connected`.

## Security

- **Không commit** `mcp.json` — chứa token.
- Postgres: dùng read-only user cho MCP.
- GitHub PAT: expire 90 ngày, không scope `delete_repo`.
- Filesystem: restrict path, không set `/` hoặc home dir.

## Troubleshooting

| Lỗi                                   | Nguyên nhân                  | Fix                             |
| ------------------------------------- | ---------------------------- | ------------------------------- |
| `MCP server 'github' failed to start` | PAT sai hoặc hết hạn         | Gen PAT mới                     |
| `ECONNREFUSED postgres:5432`          | Postgres container chưa chạy | `docker-compose up -d postgres` |
| `npx command not found`               | Node chưa cài                | Cài Node 20 LTS                 |
| `Permission denied: .claude/mcp.json` | File bị track git + readonly | `chmod 600 .claude/mcp.json`    |

## Alternative MCP servers đáng thử

- `@modelcontextprotocol/server-slack` — list channel, post message (dùng cho alerting)
- `@modelcontextprotocol/server-brave-search` — web search (replace WebSearch khi cần)
- `@modelcontextprotocol/server-memory` — persistent memory graph (thay file memory)
- Custom MCP: viết server riêng cho MLflow API nếu cần (Python SDK dễ)

Đây là bonus, không bắt buộc cho đồ án. Team có thể bỏ qua ở giai đoạn đầu.
