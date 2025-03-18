# 内置库
import logging
from contextlib import asynccontextmanager

import yaml
# 三方库
from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

# 本地
from init import *

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s][%(name)s][%(thread)s][%(threadName)s][%(levelname)s] %(message)s (%(filename)s:%(lineno)d)',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(),
        logging.handlers.TimedRotatingFileHandler(
            'logs/roating_log.log', when='D', backupCount=128, delay=False, utc=False, encoding='utf-8'
        )
    ]
)
logging.getLogger('httpcore').setLevel(logging.ERROR)
logger = logging.getLogger("GenApi.app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    """应用启动时的初始化工作"""

    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    global CHAT_REQ_TOKEN, TEXT_BEFORE_PROMPT, TEXT_AFTER_PROMPT, KEEP_CHAT, IGNORE_THINKING, HTTP_PROXY, CF_PROXY_URL

    if config.get('token'):
        CHAT_REQ_TOKEN = config['token']
    if config.get('textBeforePrompt'):
        TEXT_BEFORE_PROMPT = config['textBeforePrompt']
    if config.get('textAfterPrompt'):
        TEXT_AFTER_PROMPT = config['textAfterPrompt']
    if config.get('keepChat'):
        KEEP_CHAT = True
    if config.get('ignoreThinking'):
        IGNORE_THINKING = True
    if config.get('httpProxy'):
        HTTP_PROXY = config['httpProxy']
    if config.get('cfProxyUrl'):
        CF_PROXY_URL = config['cfProxyUrl']
    
    if config.get('viewerGroup'):
        for user in config['viewerGroup']:
            ViewerUser[user[0].encode()] = user[1].encode()
    if config.get('adminGroup'):
        for user in config['adminGroup']:
            AdminUser[user[0].encode()] = user[1].encode()
    for k, v in AdminUser.items():
        ViewerUser[k] = v
    
    # 检查是否有可用的cookie
    if not CookieManager.cookies:
        logger.error("错误: 未找到任何有效的Grok cookie")
    else:
        logger.info(f"共加载了 {len(CookieManager.cookies)} 个Grok cookie")

    yield


# 创建FastAPI应用
app = FastAPI(title="GenApi", version="1.0.0", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")


# 在应用启动前，添加一个中间件来处理403响应
@app.middleware("http")
async def check_for_403_responses(request: Request, call_next):
    """
    响应中间件，捕获403响应并记录详细信息
    """
    response = await call_next(request)
    
    # 检查是否是403响应
    if response.status_code == 403:
        logger.warning("检测到403状态码响应")
        
        # 尝试获取响应体以记录详细错误
        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        
        # 重新创建响应以返回给客户端
        return Response(
            content=body,
            status_code=403,
            headers=dict(response.headers),
            media_type=response.media_type
        )
    
    return response


from .routers.chat import Router as ChatRouter
app.include_router(ChatRouter)
