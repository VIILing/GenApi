# 内置库
import logging
import time
from typing import AsyncGenerator

# 三方库
from fastapi import HTTPException, Depends, APIRouter
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sse_starlette.sse import EventSourceResponse

# 本地
from src import cf_proxy
from src.init import CF_PROXY_URL
from src.init import CHAT_REQ_TOKEN, CookieManager
from src.routers.clients.client import AbsModelClient, RequestParams, RequestResponse
from src.routers.clients.grok.client import Grok3Client
from src.routers.clients.grok.constants import GROK3_MODEL_NAME, GROK3_REASONING_MODEL_NAME
from src.routers.openai_models import *
from src.utils import CookieMsg


security = HTTPBearer()


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
    if not CHAT_REQ_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="服务器未配置认证令牌"
        )
    
    if credentials.scheme != "Bearer":
        raise HTTPException(
            status_code=401,
            detail="认证方案无效"
        )
    
    if credentials.credentials != CHAT_REQ_TOKEN:
        raise HTTPException(
            status_code=401,
            detail="认证令牌无效"
        )
    
    return credentials.credentials


Router = APIRouter(prefix='/chat', dependencies=[Depends(verify_chat_req)])
logger = logging.getLogger("GenApi.chat")


class UnknownError(Exception):
    pass


@Router.get("/v1/models")
async def list_models(
    _: str = Depends(verify_chat_req)
):
    """
    列出可用模型
    
    Returns:
        模型列表
    """
    
    # 构建模型列表
    model_list = ModelList(
        data=[
            ModelData(id=GROK3_MODEL_NAME, owned_by="xAI"),
            ModelData(id=GROK3_REASONING_MODEL_NAME, owned_by="xAI"),
        ]
    )
    
    return model_list


@Router.post("/v1/chat/completions")
async def chat_completion(
    request_body: BaseChatCompletionBody,
    _: str = Depends(verify_chat_req)
):
    """
    """
    
    # 检查消息
    if not request_body.messages:
        raise HTTPException(
            status_code=400,
            detail="未提供消息"
        )
    
    # 选择cookie
    if not CookieManager or not CookieManager.cookies:
        raise HTTPException(
            status_code=400,
            detail="未配置Cookie"
        )
    
    cookie_msg = CookieManager.get_cookie()
    if not cookie_msg:
        raise HTTPException(
            status_code=503,
            detail="暂无可用的cookie，请稍后再试"
        )
        
    # 确定模型
    model_client: AbsModelClient
    if request_body.model in {GROK3_MODEL_NAME, GROK3_REASONING_MODEL_NAME}:
        model_client = Grok3Client(logger, {})
    else:
        raise HTTPException(
            status_code=503,
            detail="请求的模型不存在"
        )
    
    request_params = model_client.generate_request_params(request_body, cookie_msg)

    try:
        # 尝试使用异步客户端直接请求
        logger.info("尝试使用异步客户端直接请求")
        return await _chat_completion(True, request_body.stream, model_client, request_params, cookie_msg)
    
    except HTTPException as e:
        # 直接请求失败，检查是否配置了CF代理
        logger.info(f"异步直接请求失败: {e}")
        
        if CF_PROXY_URL is None or CF_PROXY_URL == '':
            logger.info("未配置CF绕过代理，无法进行重试")
            raise HTTPException(
                status_code=500,
                detail=f"异步直接请求失败，且未配置CF绕过代理，请求结束。异常: {e}"
            ) from e

        # 尝试使用同步客户端和CF代理进行重试
        logger.info("尝试使用CF绕过代理和同步客户端进行重试")
        
        # 获取CF代理配置
        proxy_url = cf_proxy.BrightDataProxy.get_normal_proxy(CF_PROXY_URL)
        logger.debug(f"使用CF绕过代理: {proxy_url}")
        
        request_params.proxy = proxy_url
        # 使用同步客户端和CF代理重试请求
        return await _chat_completion(False, False, model_client, request_params, cookie_msg)


async def _chat_completion(
        is_async: bool,
        is_stream: bool,
        model_client: AbsModelClient,
        req_params: RequestParams,
        cookie_msg: CookieMsg
    ):
    """
    执行聊天补全请求
    """
    
    if is_async:
        if is_stream:
            # 对于流式响应，客户端会在生成器内部关闭，而不是在这里关闭
            # 在返回了 EventSourceResponse 之后，会立刻执行 finally 块
            return EventSourceResponse(_async_stream_with_cookie_cleanup(model_client, req_params, cookie_msg))
        else:
            # 异步非流式响应，收集完整结果
            try:
                full_response = await model_client.async_full_response(req_params)
                CookieManager.release_cookie(cookie_msg, full_response.error_msg)
                if full_response.error_msg is None:
                    return JSONResponse(content=model_client.create_openai_full_response_body(full_response.data.decode()))
                else:
                    raise HTTPException(
                        status_code=500,
                        detail=full_response.error_msg
                    )
            except Exception as e:
                model_name = model_client.get_model_name()
                error_msg = f"模型 {model_name} 在处理异步完整数据的过程中，出现非预期的错误：{e}"
                CookieManager.release_cookie(cookie_msg, error_msg)
                logger.error(error_msg)
                raise HTTPException(
                    status_code=500,
                    detail=error_msg
                ) from e
    else:
        try:
            full_response = model_client.sync_full_response(req_params)  # 考虑之后丢线程池，不要阻塞住主进程。
            CookieManager.release_cookie(cookie_msg, full_response.error_msg)
            if full_response.error_msg is None:
                return JSONResponse(content=model_client.create_openai_full_response_body(full_response.data.decode()))
            else:
                raise HTTPException(
                    status_code=500,
                    detail=full_response.error_msg
                )
        except Exception as e:
            model_name = model_client.get_model_name()
            error_msg = f"模型 {model_name} 在处理同步完整数据的过程中，出现非预期的错误：{e}"
            CookieManager.release_cookie(cookie_msg, error_msg)
            logger.error(error_msg)
            raise HTTPException(
                status_code=500,
                detail=error_msg
            ) from e


async def _async_stream_with_cookie_cleanup(
    model_client: AbsModelClient,
    req_params:  RequestParams,
    cookie_msg: CookieMsg
) -> AsyncGenerator[RequestResponse, None]:
    """
    """
    
    error_msg = None
    try:
        chunk: RequestResponse
        async for chunk in await model_client.async_stream_response(req_params):
            if chunk.error_msg is not None:
                openai_data_block = model_client.convert_token_to_openai_format(
                    token=chunk.data.decode(),
                    completion_id=f"chatcmpl-{time.time()}"
                )
                yield openai_data_block
            else:
                model_name = model_client.get_model_name()
                error_msg = f"模型 {model_name} 在处理异步流式数据的过程中，出现响应错误：{chunk.error_msg}"
                logger.error(error_msg)
                raise HTTPException(
                    status_code=500,
                    detail=error_msg
                )
        yield "[DONE]"

    except Exception as e:
        model_name = model_client.get_model_name()
        error_msg = f"模型 {model_name} 在处理异步流式数据的过程中，出现非预期的错误：{e}"
        logger.error(error_msg)
        raise HTTPException(
            status_code=500,
            detail=error_msg
        ) from e
    
    finally:
        # 释放cookie
        logger.debug("异步流式响应完成，释放cookie")
        CookieManager.release_cookie(cookie_msg, error_msg)