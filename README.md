# Gemini Business API OpenAI Gateway

一个基于 FastAPI 的 OpenAI 兼容网关，用于访问 Google Gemini Business API。该项目允许您通过标准的 OpenAI API 接口与 Gemini 模型进行交互，支持文本对话、多模态输入（图片）、流式响应等功能。

## 功能特性

- ✅ OpenAI 兼容 API 接口
- ✅ 支持多种 Gemini 模型（gemini-2.5-flash, gemini-2.5-pro, gemini-3-pro-preview）
- ✅ 多模态输入支持（文本 + 图片）
- ✅ 流式和非流式响应
- ✅ 自动 JWT 令牌管理
- ✅ 负载均衡（多账户轮询）
- ✅ 图片生成和下载
- ✅ 代理支持

## 项目结构

```
gemini-business-api/
├── src/                    # 源代码目录
│   ├── __init__.py
│   ├── auth.py            # 认证相关
│   ├── chat.py            # 聊天处理
│   ├── config.py          # 配置管理
│   ├── gemini.py          # 主入口
│   ├── main.py            # FastAPI应用
│   ├── models.py          # 数据模型
│   ├── session.py         # 会话管理
│   └── utils.py           # 工具函数
├── config/                # 配置文件目录
│   ├── app.json           # 应用配置（proxy, host, port, base_url）
│   ├── config.json        # 生产配置
│   └── config.test.json   # 测试配置
├── generated_images/      # 生成的图片存储目录
├── requirements.txt       # Python依赖
└── README.md             # 项目文档
```

## 快速开始

### 1. 环境准备

确保您已安装 Python 3.8+：

```bash
python --version
```

### 2. 配置应用

创建 `config/app.json` 应用配置文件：

```json
{
  "proxy": "http://127.0.0.1:10808",
  "host": "0.0.0.0",
  "port": 8000,
  "base_url": "http://localhost:8000"
}
```

**配置说明：**

- `proxy`: 代理服务器地址，用于网络请求
- `host`: 服务器监听地址，`0.0.0.0` 表示监听所有接口
- `port`: 服务器监听端口
- `base_url`: 基础URL，用于生成图片链接等

### 3. 配置账户

创建 `config/config.json` 配置文件：

```json
{
  "accounts": [
    {
      "name": "account1",
      "config_id": "your-config-id",
      "cookies": "__Secure-C_SES=your-session-cookie; __Host-C_OSES=your-host-cookie",
      "csesidx": "your-csesidx",
      "project_id": "your-project-id"
    }
  ]
}
```

**获取配置参数的步骤：**

1. 访问 [https://business.gemini.google](https://business.gemini.google)
2. 登录您的 Google Business 账户
3. 打开浏览器开发者工具 (F12)
4. 在 Network 标签页中刷新页面
5. 查找包含 `getoxsrf` 的请求
6. 从请求头中提取 `csesidx` 参数
7. 从 Cookie 中提取 `__Secure-C_SES` 和 `__Host-C_OSES`
8. `config_id` 和 `project_id` 需要从页面源码或 API 响应中获取

> **注意**: 如果您有多个账户，可以在 `accounts` 数组中添加更多配置项，实现负载均衡。

### 4. 运行服务

```bash
python src/gemini.py
```

服务将在 `config/app.json` 中配置的地址和端口启动。

> **提示**: 如果启动失败，请检查 `config/config.json` 和 `config/app.json` 文件是否存在且配置正确。日志会输出详细的错误信息。

## API 使用

### 列出可用模型

```bash
curl http://localhost:8000/v1/models
```

### 文本对话

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-2.5-flash",
    "messages": [
      {"role": "user", "content": "你好，请介绍一下自己"}
    ],
    "stream": false
  }'
```

### 流式对话

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-2.5-flash",
    "messages": [
      {"role": "user", "content": "请写一首诗"}
    ],
    "stream": true
  }'
```

### 多模态输入（图片）

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-2.5-pro",
    "messages": [
      {
        "role": "user",
        "content": [
          {"type": "text", "text": "描述这张图片"},
          {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/4AAQ..."}}        ]
      }
    ],
    "stream": false
  }'
```

## 配置选项

### 环境变量

> **注意**: 应用配置现在通过 `config/app.json` 文件管理。环境变量仅在需要覆盖默认配置时使用。

- `PROXY`: 设置代理服务器（覆盖 app.json 中的 proxy）
- `HOST`: 设置服务器监听地址（覆盖 app.json 中的 host）
- `PORT`: 设置服务器监听端口（覆盖 app.json 中的 port）
- `BASE_URL`: 设置基础URL（覆盖 app.json 中的 base_url）

### 模型映射

支持的模型名称：

- `gemini-auto`: 自动选择模型
- `gemini-2.5-flash`: Gemini 2.5 Flash
- `gemini-2.5-pro`: Gemini 2.5 Pro
- `gemini-3-pro-preview`: Gemini 3 Pro Preview

## 注意事项

1. **账户配置**: 确保 `config.json` 中的 cookies 和参数正确且未过期
2. **网络连接**: 如果在中国大陆使用，建议配置代理
3. **并发限制**: 单账户可能有速率限制，建议配置多个账户进行负载均衡
4. **图片处理**: 支持 JPEG、PNG 等常见图片格式的 base64 编码上传

## 故障排除

### 常见问题

1. **JWT 刷新失败**
   - 检查 cookies 是否过期
   - 确认网络连接和代理设置

2. **Session 创建失败**
   - 验证 `config_id` 和 `project_id` 的正确性
   - 检查账户权限

3. **图片上传失败**
   - 确认图片格式和大小
   - 检查 base64 编码是否正确

4. **启动失败**
   - 确保 `config/config.json` 文件存在且格式正确
   - 检查 Python 版本和依赖安装
   - 查看控制台日志输出

### 日志调试

服务运行时会输出详细日志，可以通过日志信息排查问题：

```bash
python src/gemini.py  # 日志级别为 INFO
```

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！

## 加入MitSukina小群
[qwq点我](https://qun.qq.com/universal-share/share?ac=1&authKey=xKNtQIXZ664il6REqLHS3eNQSHRVTyU0Bp3y30siuA%2BYgXC8%2FEAH70XDxvojnREu&busi_data=eyJncm91cENvZGUiOiIxMDc0NjM3MjY3IiwidG9rZW4iOiI3eXhHSVJrNGxYUjhNeVA1SEI2UG9sRjNwNUo5YU9nVFFjQXFTMG00K0xHNTJ1R3NxaExQSGxtM1Z4TS82NmVGIiwidWluIjoiMzY4NzQ1MzI5NCJ9&data=kuGyOedY6KxouJee47K_Kzfpi_Fb9nq_zu7w4bLdKB4yZxqX5X7-q7-qMs9uKYTlv2UJSjaDzUQn4T6BNxlFJQ&svctype=4&tempid=h5_group_info)

MitSukina小群: 1074637267