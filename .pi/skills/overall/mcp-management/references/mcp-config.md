# MCP 配置参考

项目 MCP 配置位于 `.pi/mcp.json`，每个服务使用唯一名称。

## stdio 服务

```json
{
  "mcpServers": {
    "server-name": {
      "command": "/path/to/program",
      "args": ["/path/to/server.py"],
      "env": {
        "EXAMPLE_TOKEN": "由用户配置"
      }
    }
  }
}
```

检查 command、args 指向的程序和脚本是否存在。敏感值不要提交到 Git。

## HTTP 服务

```json
{
  "mcpServers": {
    "server-name": {
      "url": "https://example.com/mcp",
      "headers": {
        "Authorization": "由用户配置"
      }
    }
  }
}
```

检查 URL、请求头和连接所需的凭据。不要擅自替换远程服务地址。

## 修改原则

修改配置前先说明服务用途、影响和是否需要重启。修改后检查服务连接和工具发现，不要仅根据配置文件判断服务可用。
