# 内置库
import os
import logging
from typing import Optional, List, Union
from contextlib import asynccontextmanager

# 三方库
from fastapi import FastAPI, HTTPException, Request, Depends, status, APIRouter
from fastapi.responses import JSONResponse, Response, HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse
import yaml
import secrets

# 本地
from src.init import CHAT_REQ_TOKEN, CookieManager
from src import cf_proxy
from src.routers.openai_models import *
from src.routers.clients.client import ModelClient
from src.routers.clients.grok.client import Grok3Client
from src.routers.clients.grok.constants import GROK3_MODEL_NAME, GROK3_REASONING_MODEL_NAME


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
    request_body: RequestBody,
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
    model_client: ModelClient
    if request_body.model in {GROK3_MODEL_NAME, GROK3_REASONING_MODEL_NAME}:
        model_client = Grok3Client()
    else:
        raise HTTPException(
            status_code=503,
            detail="请求的模型不存在"
        )
    
    # 确定配置标志
    request_params = model_client.generate_request_params(
        request_body.messages,
        
    )
    
    is_reasoning = request.model == GROK3_REASONING_MODEL_NAME
    
    enable_search = False
    if request.enableSearch is not None and request.enableSearch > 0:
        enable_search = True
    
    upload_message = DEFAULT_UPLOAD_MESSAGE
    if request.uploadMessage is not None and request.uploadMessage > 0:
        upload_message = True
    
    keep_conversation = KEEP_CHAT
    if request.keepChat is not None:
        keep_conversation = request.keepChat > 0
    
    ignore_think = IGNORE_THINKING
    if request.ignoreThinking is not None:
        ignore_think = request.ignoreThinking > 0
    
    # 构建要发送给Grok 3的消息
    before_prompt = request.textBeforePrompt or TEXT_BEFORE_PROMPT
    after_prompt = request.textAfterPrompt or TEXT_AFTER_PROMPT
    
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
        proxy=HTTP_PROXY
    )

    try:
        # 尝试使用异步客户端直接请求
        logger.info("尝试直接请求Grok API（异步客户端）")
        return await _chat_completion_request(request, cookie_index, grok_client, message_text)
    
    except GrokRequestException as e:
        # 直接请求失败，检查是否配置了CF代理
        logger.warning(f"直接请求Grok API失败: {e.message}")
        
        if CF_PROXY_URL is None or CF_PROXY_URL == '':
            logger.error("未配置CF绕过代理，无法进行重试")
            # 确保在返回错误前关闭客户端
            await grok_client.close()
            # 释放cookie
            CookieManager.release_cookie(cookie_index, f"未配置CF绕过代理: {e.message}")
            raise HTTPException(
                status_code=500,
                detail=f"请求Grok API失败，且未配置CF绕过代理: {e.message}"
            ) from e
        
        try:
            # 尝试使用同步客户端和CF代理进行重试
            logger.info("尝试使用CF绕过代理和同步客户端进行重试")
            
            # 确保原客户端已关闭
            await grok_client.close()
            
            # 获取CF代理配置
            proxy_url = cf_proxy.BrightDataProxy.get_normal_proxy(CF_PROXY_URL)
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
            CookieManager.release_cookie(cookie_index, f"使用CF绕过代理和同步客户端请求失败: {str(cf_error)}")
            
            raise HTTPException(
                status_code=500,
                detail=f"使用直接请求和CF绕过代理均失败。直接请求错误: {e.message}，CF代理错误: {str(cf_error)}"
            ) from e
        
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
            
            CookieManager.release_cookie(cookie_index, error_msg)
        
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
        
        raise GrokRequestException(error_msg) from e
        
    except Exception as e:
        # 其他未预期的异常
        logger.error(f"处理请求时发生未知异常: {str(e)}")
        
        # 确保客户端已关闭并释放cookie
        await grok_client.close()
        CookieManager.release_cookie(cookie_index, f"处理请求时发生未知异常: {str(e)}")
        
        raise HTTPException(
            status_code=500,
            detail=f"处理请求时发生未知异常: {str(e)}"
        ) from e


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
                CookieManager.release_cookie(cookie_index)
                
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
            
            CookieManager.release_cookie(cookie_index, error_msg)
        
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
        
        raise GrokRequestException(error_msg) from e
        
    except Exception as e:
        # 其他异常
        error_msg = f"处理请求时发生异常: {str(e)}"
        logger.error(error_msg)
        
        # 释放cookie
        if cookie_index is not None:
            CookieManager.release_cookie(cookie_index, error_msg)
            
        await grok_client.close()  # 发生错误时关闭客户端
        
        raise GrokRequestException(error_msg) from e


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
    error_msg = None
    try:
        # 使用客户端的OpenAI流式响应方法
        async for chunk in client.stream_openai_response(message):
            logger.debug(f'Yield OpenAi chunk: {chunk}')
            yield chunk
    except Exception as e:
        logger.error(f"流式响应生成错误: {e}")
        error_msg = f"流式响应生成错误: {str(e)}"
        raise
    finally:
        # 释放cookie并关闭客户端
        logger.debug("流式响应完成，释放cookie和关闭客户端")
        CookieManager.release_cookie(cookie_index, error_msg)
        await client.close()  # 流式传输完成后关闭客户端