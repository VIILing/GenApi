import os
import logging
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse, Response, HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
import yaml

import cf_proxy
from client import AsyncGrokClient, SyncGrokClient, BaseGrokClient, GrokApiError
from models import ModelList, ModelData, RequestBody
from constants import (
    GROK3_MODEL_NAME,
    GROK3_REASONING_MODEL_NAME,
    COMPLETIONS_PATH,
    LIST_MODELS_PATH,
    DEFAULT_UPLOAD_MESSAGE
)
from utils import ThreadSafeCookieManagerClass


import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials


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
logger.setLevel(logging.INFO)


# 安全认证
security = HTTPBearer()

# 全局配置
api_token = "mio"
text_before_prompt = ""
text_after_prompt = ""
keep_chat = False
ignore_thinking = False
http_proxy = ""
cookie_manager = ThreadSafeCookieManagerClass.load_cookies_from_files()
cf_proxy_url = ""

# 管理页面可查阅用户组
_ViewerUser: dict[bytes, bytes] = {}

# 管理页面可管理用户组
_AdminUser: dict[bytes, bytes] = {}


# 认证依赖项
async def verify_chat_req(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    验证API令牌
    
    Args:
        credentials: HTTP认证凭据
        
    Returns:
        验证通过的令牌
        
    Raises:
        HTTPException: 如果认证失败
    """
    if not api_token:
        raise HTTPException(
            status_code=500,
            detail="服务器未配置认证令牌"
        )
    
    if credentials.scheme != "Bearer":
        raise HTTPException(
            status_code=401,
            detail="认证方案无效"
        )
    
    if credentials.credentials != api_token:
        raise HTTPException(
            status_code=401,
            detail="认证令牌无效"
        )
    
    return credentials.credentials


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """应用启动时的初始化工作"""

    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    global api_token, cookie_manager, text_before_prompt, text_after_prompt, keep_chat, ignore_thinking, http_proxy, cf_proxy_url

    if config.get('token'):
        api_token = config['token']
    if config.get('textBeforePrompt'):
        text_before_prompt = config['textBeforePrompt']
    if config.get('textAfterPrompt'):
        text_after_prompt = config['textAfterPrompt']
    if config.get('keepChat'):
        keep_chat = True
    if config.get('ignoreThinking'):
        ignore_thinking = True
    if config.get('httpProxy'):
        http_proxy = config['httpProxy']
    if config.get('cfProxyUrl'):
        cf_proxy_url = config['cfProxyUrl']
    
    if config.get('viewerGroup'):
        for user in config['viewerGroup']:
            _ViewerUser[user[0].encode()] = user[1].encode()
    if config.get('adminGroup'):
        for user in config['adminGroup']:
            _AdminUser[user[0].encode()] = user[1].encode()
    for k, v in _AdminUser.items():
        _ViewerUser[k] = v
    
    # 检查是否有可用的cookie
    if not cookie_manager.cookies:
        logger.error("错误: 未找到任何有效的Grok cookie")
    else:
        logger.info(f"共加载了 {len(cookie_manager.cookies)} 个Grok cookie")

    yield


# 创建FastAPI应用
app = FastAPI(title="Grok 3 API", version="1.0.0", lifespan=lifespan)


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


"""
OpenAI API兼容端点
"""


@app.get(LIST_MODELS_PATH)
async def list_models(
    _: str = Depends(verify_chat_req)
):
    """
    列出可用模型
    
    Returns:
        模型列表
    """
    logger.info(f"请求: GET {LIST_MODELS_PATH}")
    
    # 构建模型列表
    model_list = ModelList(
        data=[
            ModelData(id=GROK3_MODEL_NAME, owned_by="xAI"),
            ModelData(id=GROK3_REASONING_MODEL_NAME, owned_by="xAI"),
        ]
    )
    
    return model_list


class GrokRequestException(Exception):
    """
    Grok请求异常
    """
    def __init__(self, message: str):
        self.message = message



@app.post(COMPLETIONS_PATH)
async def chat_completion(
    request: RequestBody,
    _: str = Depends(verify_chat_req)
):
    """
    处理聊天完成请求
    
    Args:
        request: 请求体
        _: 认证
        
    Returns:
        聊天完成响应
    """
    logger.info(f"请求: POST {COMPLETIONS_PATH}")
    
    # 检查消息
    if not request.messages:
        raise HTTPException(
            status_code=400,
            detail="未提供消息"
        )
    
    # 选择cookie
    if not cookie_manager or not cookie_manager.cookies:
        raise HTTPException(
            status_code=400,
            detail="未配置Grok cookie"
        )
    
    cookie_index, cookie = cookie_manager.get_cookie()
    if not cookie:
        raise HTTPException(
            status_code=503,
            detail="暂无可用的Grok cookie，请稍后再试"
        )
    
    # 确定配置标志
    is_reasoning = request.model == GROK3_REASONING_MODEL_NAME
    
    enable_search = False
    if request.enableSearch is not None and request.enableSearch > 0:
        enable_search = True
    
    upload_message = DEFAULT_UPLOAD_MESSAGE
    if request.uploadMessage is not None and request.uploadMessage > 0:
        upload_message = True
    
    keep_conversation = keep_chat
    if request.keepChat is not None:
        keep_conversation = request.keepChat > 0
    
    ignore_think = ignore_thinking
    if request.ignoreThinking is not None:
        ignore_think = request.ignoreThinking > 0
    
    # 构建要发送给Grok 3的消息
    before_prompt = request.textBeforePrompt or text_before_prompt
    after_prompt = request.textAfterPrompt or text_after_prompt
    
    message_text = f"{before_prompt}\n"
    for msg in request.messages:
        message_text += f"\n[[{msg.role}]]\n{msg.content}"
    message_text += f"\n{after_prompt}"

    # 创建异步客户端尝试直接请求
    grok_client: BaseGrokClient = AsyncGrokClient(
        cookie=cookie,
        is_reasoning=is_reasoning,
        enable_search=enable_search,
        upload_message=upload_message,
        keep_chat=keep_conversation,
        ignore_thinking=ignore_think,
        proxy=http_proxy
    )

    try:
        # 尝试使用异步客户端直接请求
        logger.info("尝试直接请求Grok API（异步客户端）")
        return await _chat_completion_request(request, cookie_index, grok_client, message_text)
    
    except GrokRequestException as e:
        # 直接请求失败，检查是否配置了CF代理
        logger.warning(f"直接请求Grok API失败: {e.message}")
        
        if cf_proxy_url is None or cf_proxy_url == '':
            logger.error("未配置CF绕过代理，无法进行重试")
            # 确保在返回错误前关闭客户端
            await grok_client.close()
            # 释放cookie
            cookie_manager.release_cookie(cookie_index, False, f"未配置CF绕过代理: {e.message}")
            raise HTTPException(
                status_code=500,
                detail=f"请求Grok API失败，且未配置CF绕过代理: {e.message}"
            )
        
        try:
            # 尝试使用同步客户端和CF代理进行重试
            logger.info(f"尝试使用CF绕过代理和同步客户端进行重试")
            
            # 确保原客户端已关闭
            await grok_client.close()
            
            # 获取CF代理配置
            proxy_url = cf_proxy.BrightDataProxy.get_normal_proxy(cf_proxy_url)
            logger.debug(f"使用CF绕过代理: {proxy_url}")
            
            # 创建新的同步客户端使用CF代理
            cf_grok_client: BaseGrokClient = SyncGrokClient(
                cookie=cookie,
                is_reasoning=is_reasoning,
                enable_search=enable_search,
                upload_message=upload_message,
                keep_chat=keep_conversation,
                ignore_thinking=ignore_think,
                proxy=proxy_url
            )
            
            # 使用同步客户端和CF代理重试请求
            return await _chat_completion_request(request, cookie_index, cf_grok_client, message_text)
        
        except Exception as cf_error:
            # CF代理请求也失败
            logger.error(f"使用CF绕过代理和同步客户端请求失败: {str(cf_error)}")
            
            # 释放cookie
            cookie_manager.release_cookie(cookie_index, False, f"使用CF绕过代理和同步客户端请求失败: {str(cf_error)}")
            
            raise HTTPException(
                status_code=500,
                detail=f"使用直接请求和CF绕过代理均失败。直接请求错误: {e.message}，CF代理错误: {str(cf_error)}"
            )
        
    except GrokApiError as e:
        # Grok API错误（包括403等CF拦截）
        error_msg = f"Grok API请求错误: {str(e)}"
        logger.error(error_msg)
        
        # 释放cookie，标记为失败
        if cookie_index is not None:
            # 检查是否是403错误
            is_403_error = "403" in str(e)
            if is_403_error:
                error_msg = f"CloudFlare 403错误: {str(e)}"
                logger.warning(f"Cookie {cookie_index} 收到403错误，可能被CloudFlare拦截")
            
            cookie_manager.release_cookie(cookie_index, False, error_msg)
        
        await grok_client.close()  # 发生错误时关闭客户端
        
        # 特殊处理403错误
        if "403" in str(e):
            # 返回403状态码和详细错误信息
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "message": "CloudFlare拦截请求，请稍后再试或使用其他Cookie",
                        "type": "cf_blocked",
                        "param": None,
                        "code": 403
                    }
                }
            )
        
        raise GrokRequestException(error_msg)
        
    except Exception as e:
        # 其他未预期的异常
        logger.error(f"处理请求时发生未知异常: {str(e)}")
        
        # 确保客户端已关闭并释放cookie
        await grok_client.close()
        cookie_manager.release_cookie(cookie_index, False, f"处理请求时发生未知异常: {str(e)}")
        
        raise HTTPException(
            status_code=500,
            detail=f"处理请求时发生未知异常: {str(e)}"
        )


async def _chat_completion_request(
        request: RequestBody,
        cookie_index: int,
        grok_client: BaseGrokClient,
        message_text: str
    ):
    """
    执行Grok API请求
    
    Args:
        request: 请求体
        cookie_index: cookie索引
        grok_client: BaseGrokClient实例
        message_text: 消息文本
    
    Returns:
        流式或非流式响应
    
    Raises:
        GrokRequestException: 如果请求失败
    """
    try:
        # 根据请求类型选择适当的响应方式
        if request.stream:
            # 流式响应
            logger.info("处理流式响应请求")
            # 对于流式响应，客户端会在生成器内部关闭，而不是在这里关闭
            return EventSourceResponse(_stream_with_cookie_cleanup(grok_client, message_text, cookie_index))
        else:
            # 非流式响应，收集完整结果
            logger.info("处理非流式响应请求")
            try:
                full_response = await grok_client.full_response(message_text)
                
                # 释放cookie
                cookie_manager.release_cookie(cookie_index, True)
                
                # 返回OpenAI格式的响应
                return JSONResponse(content=grok_client.create_openai_full_response_body(full_response))
            finally:
                # 只在非流式响应时关闭客户端
                await grok_client.close()

    except GrokApiError as e:
        # Grok API错误（包括403等CF拦截）
        error_msg = f"Grok API请求错误: {str(e)}"
        logger.error(error_msg)
        
        # 释放cookie，标记为失败
        if cookie_index is not None:
            # 检查是否是403错误
            is_403_error = "403" in str(e)
            if is_403_error:
                error_msg = f"CloudFlare 403错误: {str(e)}"
                logger.warning(f"Cookie {cookie_index} 收到403错误，可能被CloudFlare拦截")
            
            cookie_manager.release_cookie(cookie_index, False, error_msg)
        
        await grok_client.close()  # 发生错误时关闭客户端
        
        # 特殊处理403错误
        if "403" in str(e):
            # 返回403状态码和详细错误信息
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "message": "CloudFlare拦截请求，请稍后再试或使用其他Cookie",
                        "type": "cf_blocked",
                        "param": None,
                        "code": 403
                    }
                }
            )
        
        raise GrokRequestException(error_msg)
        
    except Exception as e:
        # 其他异常
        error_msg = f"处理请求时发生异常: {str(e)}"
        logger.error(error_msg)
        
        # 释放cookie
        if cookie_index is not None:
            cookie_manager.release_cookie(cookie_index, False, error_msg)
            
        await grok_client.close()  # 发生错误时关闭客户端
        
        raise GrokRequestException(error_msg)


async def _stream_with_cookie_cleanup(client: BaseGrokClient, message: str, cookie_index: int):
    """
    包装流式响应生成器，确保在完成后释放cookie和关闭客户端
    
    Args:
        client: BaseGrokClient实例
        message: 消息内容
        cookie_index: cookie索引
        
    Yields:
        OpenAI格式的流式响应数据
    """
    success = True
    error_msg = None
    try:
        # 使用客户端的OpenAI流式响应方法
        async for chunk in client.stream_openai_response(message):
            yield chunk
    except Exception as e:
        logger.error(f"流式响应生成错误: {e}")
        success = False
        error_msg = f"流式响应生成错误: {str(e)}"
        raise
    finally:
        # 释放cookie并关闭客户端
        logger.debug("流式响应完成，释放cookie和关闭客户端")
        cookie_manager.release_cookie(cookie_index, success, error_msg)
        await client.close()  # 流式传输完成后关闭客户端
        

"""
Manager web page
"""

app.mount("/static", StaticFiles(directory="static"), name="static")


_Security = HTTPBasic()


def verify_viewer(
    credentials: Annotated[HTTPBasicCredentials, Depends(_Security)],
):
    current_username_bytes = credentials.username.encode("utf8")
    if current_username_bytes not in _ViewerUser:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    current_password_bytes = _ViewerUser[current_username_bytes]
    is_correct_password = secrets.compare_digest(
        current_password_bytes, credentials.password.encode("utf8")
    )
    if not is_correct_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def verify_admin(
    credentials: Annotated[HTTPBasicCredentials, Depends(_Security)],
):
    current_username_bytes = credentials.username.encode("utf8")
    if current_username_bytes not in _AdminUser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    current_password_bytes = _AdminUser[current_username_bytes]
    is_correct_password = secrets.compare_digest(
        current_password_bytes, credentials.password.encode("utf8")
    )
    if not is_correct_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    return credentials.username


@app.get("/logout")
async def logout():
    # 返回一个 401 状态码，并设置 WWW-Authenticate 头来提示客户端重新认证
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication cleared",
        headers={"WWW-Authenticate": "Basic"}
    )


with open(os.path.join(os.path.split(__file__)[0], 'resources', 'amis_template.html'), 'r', encoding='utf-8') as _fn:
    AmisTemplate = _fn.read()


PageJsonCache: dict[str, str] = dict()
for _root, _dirs, _files in os.walk(os.path.join(os.path.split(__file__)[0], 'resources', 'pages')):
    for _name in _files:
        with open(os.path.join(_root, _name), 'r', encoding='utf-8') as _fn:
            _json_content = _fn.read()
        PageJsonCache[_name] = _json_content


Custom500ErrorHtml = """
<html>
    <head>
        <title>Server Error</title>
    </head>
    <body>
        <h1>500 - Internal Server Error</h1>
        <p>Something went wrong. Please try again later.</p>
    </body>
</html>
"""


def render_html(json_content: str) -> HTMLResponse:
    return HTMLResponse(content=AmisTemplate.format(json_body=json_content), status_code=200)


@app.get("/web/setting/cookie_manager")
async def web_setting_cookie_manager(_: str = Depends(verify_viewer)):
    json_content = PageJsonCache.get("cookie_manager.json")
    if json_content is None:
        return HTMLResponse(content=Custom500ErrorHtml, status_code=500)
    return render_html(json_content)


@app.get("/api/setting/cookie-stats")
async def get_cookie_stats(
    cookie_index: Optional[int] = None,
    _: str = Depends(verify_viewer)
):
    """
    获取所有cookie的统计信息
    
    Returns:
        包含所有cookie统计信息的列表
    """
    if not cookie_manager:
        raise HTTPException(status_code=404, detail="Cookie管理器未初始化")
        
    try:
        stats = {v['index']: v for v in cookie_manager.get_cookie_stats()}
        if cookie_index is not None:
            if cookie_index not in stats:
                raise HTTPException(status_code=404, detail="Cookie索引不存在")
            return stats[cookie_index]
        return list(stats.values())
    except Exception as e:
        logger.error(f"获取cookie统计信息时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取cookie统计信息失败: {str(e)}")


class UpdateCookieRequest(BaseModel):
    cookie_index: int
    cookie: str
    

@app.post("/api/setting/update-cookie")
async def update_cookie(
    request: UpdateCookieRequest,
    _: str = Depends(verify_admin)
):
    if not cookie_manager:
        raise HTTPException(status_code=404, detail="Cookie管理器未初始化") 
    
    try:
        success, msg = cookie_manager.update_cookie(request.cookie_index, request.cookie)
        if not success:
            return {
                "status": 1,
                "msg": msg,
                "data": None
        }
        return {
            "status": 0,
            "msg": "Cookie更新成功",
            "data": {
                "cookie_index": request.cookie_index,
                "cookie": request.cookie
            }
        }
    except Exception as e:
        logger.error(f"更新Cookie时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"更新Cookie失败: {str(e)}")


class IsEnableCookieRequest(BaseModel):
    cookie_index: int
    is_enable: bool
    

@app.post("/api/setting/is-enable-cookie")
async def is_enable_cookie(
    request: IsEnableCookieRequest,
    _: str = Depends(verify_admin)
):
    if not cookie_manager:
        raise HTTPException(status_code=404, detail="Cookie管理器未初始化") 
    
    try:
        success, msg = cookie_manager.is_enable_cookie(request.cookie_index, request.is_enable)
        if not success:
            return {
                "status": 1,
                "msg": msg,
                "data": None
        }
        return {
            "status": 0,
            "msg": "Cookie更新成功",
            "data": None
        }
    except Exception as e:
        logger.error(f"更新Cookie时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"更新Cookie失败: {str(e)}")
