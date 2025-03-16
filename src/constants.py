# Grok API URL相关常量
NEW_CHAT_URL = "https://grok.com/rest/app-chat/conversations/new"  # 创建新对话的端点
UPLOAD_FILE_URL = "https://grok.com/rest/app-chat/upload-file"      # 上传文件的端点

# 模型名称
GROK3_MODEL_NAME = "grok-3"
GROK3_REASONING_MODEL_NAME = "grok-3-reasoning"

# API路径
COMPLETIONS_PATH = "/v1/chat/completions"
LIST_MODELS_PATH = "/v1/models"

# 将消息作为文件上传
DEFAULT_UPLOAD_MESSAGE = False
MESSAGE_CHARS_LIMIT = 50000
DEFAULT_UPLOAD_MESSAGE_PROMPT = "Follow the instructions in the attached file to respond."

# HTTP请求头模版
DEFAULT_HEADERS = {
    "accept": "*/*",
    "accept-language": "en-GB,en;q=0.9",
    "content-type": "application/json",
    "origin": "https://grok.com",
    "priority": "u=1, i",
    "referer": "https://grok.com/",
    "sec-ch-ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Brave";v="126"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "sec-gpc": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36 Edg/134.0.0.0",
}
