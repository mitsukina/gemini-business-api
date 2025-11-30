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

## 快速开始

### 1. 环境准备

确保您已安装 Python 3.8+：

```bash
python --version
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置账户

创建 `config.json` 配置文件：

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
python gemini.py
```

服务将在 `http://0.0.0.0:8000` 启动。

> **提示**: 如果启动失败，请检查 `config.json` 文件是否存在且配置正确。日志会输出详细的错误信息。

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

- `PROXY`: 设置代理服务器，默认 `http://127.0.0.1:10808`
- `HOST`: 设置服务器监听地址，默认 `0.0.0.0`
- `PORT`: 设置服务器监听端口，默认 `8000`
- `BASE_URL`: 设置基础URL，默认根据 `HOST` 和 `PORT` 自动生成（例如 `http://localhost:8000`）

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
   - 确保 `config.json` 文件存在且格式正确
   - 检查 Python 版本和依赖安装
   - 查看控制台日志输出

### 日志调试

服务运行时会输出详细日志，可以通过日志信息排查问题：

```bash
python gemini.py  # 日志级别为 INFO
```

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！

## 加入MitSukina小群
[qwq点我](https://qun.qq.com/universal-share/share?ac=1&authKey=xKNtQIXZ664il6REqLHS3eNQSHRVTyU0Bp3y30siuA%2BYgXC8%2FEAH70XDxvojnREu&busi_data=eyJncm91cENvZGUiOiIxMDc0NjM3MjY3IiwidG9rZW4iOiI3eXhHSVJrNGxYUjhNeVA1SEI2UG9sRjNwNUo5YU9nVFFjQXFTMG00K0xHNTJ1R3NxaExQSGxtM1Z4TS82NmVGIiwidWluIjoiMzY4NzQ1MzI5NCJ9&data=kuGyOedY6KxouJee47K_Kzfpi_Fb9nq_zu7w4bLdKB4yZxqX5X7-q7-qMs9uKYTlv2UJSjaDzUQn4T6BNxlFJQ&svctype=4&tempid=h5_group_info)

MitSukina小群: 1074637267