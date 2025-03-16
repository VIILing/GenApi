# GenApi

这是一个使用 `Python FastAPI`实现的各种大语言模型的 `API`代理服务器，提供与 `OpenAI API`兼容的接口，让你可以通过标准的OpenAI客户端库来使用各种大语言模型。该项目通过管理和轮换多个 `cookies `，解决了单一 `Cookie`可能被 `CloudFlare`拦截或使用次数限制的问题，提供了稳定可靠的 `API`访问体验。

目前实现了代理访问功能的模型有：

- grok

## 特性

- 完全兼容OpenAI API接口
- 支持流式响应
- 支持网络搜索功能
- 支持大消息自动上传为文件
- 支持多Cookie负载均衡与智能轮换
- 支持HTTP/SOCKS5代理
- 提供CloudFlare绕过代理功能
- 内置Web管理界面，支持在线查看和管理Cookie
- 完善的权限控制系统，支持管理员和查看者权限组
- 详细的Cookie统计和监控

## 安装与运行

1. 克隆仓库并进入项目目录
2. 将 `src/config-template.yaml`复制为 `src/config.yaml`。
3. 安装依赖:

```bash
pip install -r requirements.txt
```

4. 运行

```bash
cd src
fastapi run app.py
```

## 配置方式

### 1. 配置文件

在 `config.yaml`文件中配置服务器:

```yaml
token: "your_auth_token"
textBeforePrompt: "自定义提示前缀"
textAfterPrompt: "自定义提示后缀"
keepChat: true
ignoreThinking: true
httpProxy: "http://your-proxy:port"
cfProxyUrl: "http://your-cf-proxy:port"

# 权限组配置
viewerGroup:
  - ["viewer1", "password1"]
  - ["viewer2", "password2"]
adminGroup:
  - ["admin1", "password1"]
  - ["admin2", "password2"]
```

## Cookie管理系统

### Cookie轮询策略

系统实现了高级的Cookie管理和轮询策略，确保API请求的负载均衡和稳定性：

1. **负载均衡**：系统会自动选择使用次数最少的可用Cookie，确保所有Cookie被均匀使用
2. **状态追踪**：系统会记录每个Cookie的成功/失败次数、最后成功/失败时间和错误信息
3. **自动错误处理**：当检测到Cookie被CloudFlare拦截(403错误)时，会自动标记并记录详细信息
4. **多级重试**：直接请求失败时，会自动尝试使用CloudFlare绕过代理重试。（CloudFlare绕过代理是指，爬虫服务商提供给你的代理地址，通过使用该代理地址去请求的话，爬虫服务商会自动帮你解决验证码。目前该功能仍处于实验期。）

### 在线Cookie管理

系统提供了Web界面用于在线管理和监控Cookie，提供以下功能：

1. **实时统计**：查看所有Cookie的使用统计，包括成功/失败次数、使用率等。
2. **详细信息**：查看每个Cookie的详细信息，包括来源文件、最后使用时间等。
3. **在线编辑**：管理员用户可以在线更新Cookie内容与Cookie启用与否。
4. **状态监控**：实时监控Cookie状态，快速发现失效或被拦截的Cookie。

访问路径：`/web/setting/cookie_manager`

## 权限控制系统

系统实现了两级权限控制：

1. **查看者(Viewer)**：可以查看Cookie统计信息，但不能修改。
2. **管理员(Admin)**：拥有所有查看者权限，并可以更新Cookie内容。

权限控制基于HTTP Basic认证，可以在配置文件中设置用户名和密码：

```yaml
viewerGroup:
  - ["viewer1", "password1"]
adminGroup:
  - ["admin1", "password1"]
```

管理员自动拥有查看者权限。可以通过访问 `/logout`路径注销当前登录。

## API端点

### 管理API

除了标准的OpenAI兼容API外，系统还提供了以下管理API端点：

- **GET /api/setting/cookie-stats**：获取所有Cookie的统计信息
- **GET /api/setting/cookie-stats?cookie_index=1**：获取指定索引Cookie的统计信息
- **POST /api/setting/update-cookie**：更新指定Cookie内容(仅管理员)

## 使用Cookie文件

你可以在 `cookies`目录中放置多个 `.txt`文件，每个文件包含一个有效的Grok cookie。服务器会自动加载这些文件，并在处理请求时使用线程安全的方式轮换这些Cookie。

## API使用

### 列出可用模型

```
GET /v1/models
```

### 聊天完成

```
POST /v1/chat/completions
```

请求格式与OpenAI API兼容:

```json
{
  "model": "grok-3",
  "messages": [
    {"role": "system", "content": "你是一个有用的AI助手。"},
    {"role": "user", "content": "你好，介绍一下你自己！"}
  ],
  "stream": true
}
```

支持的模型名称:

- `grok-3`: 标准模型
- `grok-3-reasoning`: 推理模型(显示思考过程)

## 与OpenAI客户端库一起使用

```python
import openai

client = openai.OpenAI(
    api_key="your_auth_token",
    base_url="http://localhost:8180/v1"
)

response = client.chat.completions.create(
    model="grok-3",
    messages=[
        {"role": "system", "content": "你是一个有用的AI助手。"},
        {"role": "user", "content": "你好，介绍一下你自己！"}
    ]
)

print(response.choices[0].message.content)
```
