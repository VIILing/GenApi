import json
import base64
import httpx
import time
from typing import Dict, Any, List, Optional, Union, Callable, AsyncGenerator, Tuple, Generator
import asyncio
from io import BytesIO
import logging
from abc import ABC, abstractmethod

from models import (
    ToolOverrides, 
    UploadFileRequest, 
    UploadFileResponse, 
    ResponseToken,
    OpenAIChatCompletionChunk,
    OpenAIChatCompletionChunkChoice,
    OpenAIChatCompletionMessage,
    OpenAIChatCompletion,
    OpenAIChatCompletionChoice,
    OpenAIChatCompletionUsage
)
from constants import (
    NEW_CHAT_URL,
    UPLOAD_FILE_URL,
    GROK3_MODEL_NAME,
    GROK3_REASONING_MODEL_NAME,
    DEFAULT_HEADERS,
    MESSAGE_CHARS_LIMIT,
    DEFAULT_UPLOAD_MESSAGE_PROMPT
)
from utils import generate_uuid, must_marshal

logger = logging.getLogger('GenApi.client')


class GrokApiError(Exception):
    pass


class BaseGrokClient(ABC):
    """
    BaseGrokClient定义了与Grok 3 Web API交互的抽象基类。
    它封装了API端点、HTTP头信息和通用配置标志。
    具体的请求实现由子类完成。
    """
    
    def __init__(
        self,
        cookie: str,
        is_reasoning: bool = False,
        enable_search: bool = False,
        upload_message: bool = False,
        keep_chat: bool = False,
        ignore_thinking: bool = False,
        timeout: int = 1800,  # 默认30分钟超时
        proxy: Optional[str] = None
    ):
        """
        创建一个新的BaseGrokClient实例，使用提供的cookie和配置标志。
        
        Args:
            cookie: Grok的cookie
            is_reasoning: 是否使用推理模型
            enable_search: 是否在网络中搜索
            upload_message: 是否将消息作为文件上传
            keep_chat: 是否保留聊天历史
            ignore_thinking: 是否在响应中排除思考令牌
            timeout: 请求超时时间（秒）
            proxy: 代理服务器URL
        """
        # 创建headers并添加cookie
        self.headers = DEFAULT_HEADERS.copy()
        self.headers["cookie"] = cookie
        
        # 设置配置标志
        self.is_reasoning = is_reasoning
        self.enable_search = enable_search
        self.upload_message = upload_message
        self.keep_chat = keep_chat
        self.ignore_thinking = ignore_thinking
        
        # 存储超时设置
        self.timeout = timeout
        
        # 存储代理设置
        self.proxy = proxy
        
        # 客户端将在子类中初始化
        # self.client = ...
        
    def get_model_name(self) -> str:
        """
        根据is_reasoning标志返回适当的模型名称。
        
        Returns:
            模型名称字符串
        """
        if self.is_reasoning:
            return GROK3_REASONING_MODEL_NAME
        else:
            return GROK3_MODEL_NAME
    
    def prepare_payload(self, message: str, file_id: str = "") -> Dict[str, Any]:
        """
        根据给定的消息和配置构建Grok 3 Web API的请求负载。
        
        Args:
            message: 要发送的消息内容
            file_id: 可选的文件ID（如果消息作为文件上传）
            
        Returns:
            请求负载字典
        """
        # 根据是否启用搜索来设置工具覆盖
        tool_overrides: Any = ToolOverrides().model_dump()
        if self.enable_search:
            tool_overrides = {}  # 空字典表示使用默认配置
        
        # 处理文件附件
        file_attachments: List[str] = []
        if file_id:
            file_attachments = [file_id]
        
        # 构建并返回完整的请求负载
        return {
            "deepsearchPreset": "",
            "disableSearch": False,
            "enableImageGeneration": True,
            "enableImageStreaming": True,
            "enableSideBySide": True,
            "fileAttachments": file_attachments,
            "forceConcise": False,
            "imageAttachments": [],
            "imageGenerationCount": 2,
            "isPreset": False,
            "isReasoning": self.is_reasoning,
            "message": message,
            "modelName": "grok-3",
            "returnImageBytes": False,
            "returnRawGrokInXaiRequest": False,
            "sendFinalMetadata": True,
            "temporary": not self.keep_chat,
            "toolOverrides": tool_overrides,
            "webpageUrls": [],
        }
        
    def convert_token_to_openai_format(self, token: str, completion_id: str) -> str:
        """
        将Grok token转换为OpenAI流式响应格式
        
        Args:
            token: Grok token
            completion_id: 完成ID
            
        Returns:
            OpenAI格式的流式响应数据
        """
        chunk = OpenAIChatCompletionChunk(
            id=completion_id,
            created=int(time.time()),
            model=self.get_model_name(),
            choices=[
                OpenAIChatCompletionChunkChoice(
                    index=0,
                    delta=OpenAIChatCompletionMessage(
                        role="assistant",
                        content=token
                    ),
                    finish_reason=None
                )
            ]
        )
        return f"data: {must_marshal(chunk.model_dump())}\n\n"
    
    @abstractmethod
    async def close(self):
        """关闭HTTP客户端并释放资源"""
        pass
    
    @abstractmethod
    async def _do_request(self, method: str, url: str, payload: Any) -> Any:
        """
        发送HTTP请求的抽象方法，由子类实现。
        
        Args:
            method: HTTP方法（GET、POST等）
            url: 请求URL
            payload: 请求负载
            
        Returns:
            HTTP响应对象
            
        Raises:
            GrokApiError: 如果请求失败
        """
        pass
    
    @abstractmethod
    async def _upload_message_as_file(self, message: str) -> UploadFileResponse:
        """
        将消息作为文件上传的抽象方法，由子类实现。
        
        Args:
            message: 要上传的消息内容
            
        Returns:
            上传文件的响应对象
            
        Raises:
            GrokApiError: 如果上传失败
        """
        pass
    
    @abstractmethod
    async def _parse_streaming_response(self, response: Any) -> AsyncGenerator[str, None]:
        """
        解析流式响应的抽象方法，由子类实现。
        
        Args:
            response: HTTP响应对象
            
        Yields:
            响应令牌字符串
        """
        pass
    
    async def stream_response(self, message: str) -> AsyncGenerator[str, None]:
        """
        向Grok 3 Web API发送消息，并以生成器形式返回原始响应令牌。
        
        Args:
            message: 要发送的消息内容
            
        Yields:
            响应令牌字符串
            
        Raises:
            GrokApiError: 如果请求失败
        """
        # 处理超长消息上传为文件
        file_id = ""
        if self.upload_message or len(message) > MESSAGE_CHARS_LIMIT:
            upload_resp = await self._upload_message_as_file(message)
            file_id = upload_resp.fileMetadataId
            message = DEFAULT_UPLOAD_MESSAGE_PROMPT
        
        # 准备请求负载并发送请求
        payload = self.prepare_payload(message, file_id)
        response = await self._do_request(
            method="POST",
            url=NEW_CHAT_URL,
            payload=payload
        )
        
        # 解析并生成响应令牌
        async for token in self._parse_streaming_response(response):
            yield token
    
    async def stream_openai_response(self, message: str) -> AsyncGenerator[str, None]:
        """
        向Grok 3 Web API发送消息，并以OpenAI兼容格式返回流式响应。
        
        Args:
            message: 要发送的消息内容
            
        Yields:
            OpenAI格式的流式响应数据字符串
            
        Raises:
            GrokApiError: 如果请求失败
        """
        # 使用流式响应获取token
        async for token in self.stream_response(message):
            # 为每个token生成OpenAI格式的事件
            chunk_data = self.convert_token_to_openai_format(
                token=token,
                completion_id=f"chatcmpl-{time.time()}"
            )
            yield chunk_data
        
        # 发送完成事件
        yield "data: [DONE]\n\n"
    
    async def full_response(self, message: str) -> str:
        """
        向Grok 3 Web API发送消息，并返回完整的响应字符串。
        
        Args:
            message: 要发送的消息内容
            
        Returns:
            完整响应字符串
            
        Raises:
            GrokApiError: 如果请求失败
        """
        full_text = ""
        async for token in self.stream_response(message):
            full_text += token
        return full_text
    
    def create_openai_full_response_body(self, content: str) -> Dict[str, Any]:
        """
        为非流式请求创建OpenAI响应体
        
        Args:
            content: 完整的响应内容
            
        Returns:
            OpenAI格式的完整响应字典
        """
        return OpenAIChatCompletion(
            id=f"chatcmpl-{generate_uuid()}",
            created=int(time.time()),
            model=self.get_model_name(),
            choices=[
                OpenAIChatCompletionChoice(
                    index=0,
                    message=OpenAIChatCompletionMessage(
                        role="assistant",
                        content=content
                    ),
                    finish_reason="stop"
                )
            ],
            usage=OpenAIChatCompletionUsage(
                prompt_tokens=-1,
                completion_tokens=-1,
                total_tokens=-1
            )
        ).model_dump()


class AsyncGrokClient(BaseGrokClient):
    """
    AsyncGrokClient是BaseGrokClient的异步实现。
    使用httpx.AsyncClient发送请求。
    """
    
    def __init__(
        self,
        cookie: str,
        is_reasoning: bool = False,
        enable_search: bool = False,
        upload_message: bool = False,
        keep_chat: bool = False,
        ignore_thinking: bool = False,
        timeout: int = 1800,
        proxy: Optional[str] = None
    ):
        """
        创建一个新的AsyncGrokClient实例，初始化异步HTTP客户端。
        
        Args:
            cookie: Grok的cookie
            is_reasoning: 是否使用推理模型
            enable_search: 是否在网络中搜索
            upload_message: 是否将消息作为文件上传
            keep_chat: 是否保留聊天历史
            ignore_thinking: 是否在响应中排除思考令牌
            timeout: 请求超时时间（秒）
            proxy: 代理服务器URL
        """
        super().__init__(
            cookie, 
            is_reasoning, 
            enable_search, 
            upload_message, 
            keep_chat, 
            ignore_thinking, 
            timeout, 
            proxy
        )
        
        # 创建异步HTTP客户端
        client_kwargs = {
            "timeout": self.timeout,
            "follow_redirects": True,
            "verify": False  # 禁用SSL验证以兼容自签名证书
        }
        
        # 如果提供了代理，添加到客户端配置
        if self.proxy:
            client_kwargs["proxy"] = self.proxy
            logger.debug(f"创建异步HTTP客户端，使用代理: {self.proxy}")
        
        self.http_client = httpx.AsyncClient(**client_kwargs)
        logger.debug("异步HTTP客户端已初始化")
    
    async def close(self):
        """关闭异步HTTP客户端并释放资源"""
        if self.http_client:
            await self.http_client.aclose()
            self.http_client = None
            logger.debug("异步HTTP客户端已关闭")
    
    async def _do_request(self, method: str, url: str, payload: Any) -> httpx.Response:
        """
        异步发送HTTP请求。
        
        Args:
            method: HTTP方法（GET、POST等）
            url: 请求URL
            payload: 请求负载
            
        Returns:
            HTTP响应对象
            
        Raises:
            GrokApiError: 如果请求失败
        """
        # 将请求负载序列化为JSON
        json_payload = json.dumps(payload)

        # 添加调试日志
        logger.debug(f"异步请求方法: {method}")
        logger.debug(f"请求URL: {url}")
        logger.debug(f"请求负载: {json_payload}")
        
        # 记录代理信息（如果有）
        if self.proxy:
            logger.debug(f"使用代理: {self.proxy}")
        
        # 发送请求并处理响应
        try:
            response = await self.http_client.request(
                method=method,
                url=url,
                content=json_payload,
                headers=self.headers
            )
            
            logger.debug(f"响应状态码: {response.status_code}")
            
            # 检查响应状态码
            if response.status_code != 200:
                try:
                    body = response.text
                    error_msg = f"Grok API错误: {response.status_code} {response.reason_phrase}, 响应内容: {body[:500]}"
                except Exception:
                    error_msg = f"Grok API错误: {response.status_code} {response.reason_phrase}"
                raise GrokApiError(error_msg)
            
            return response
        except httpx.RequestError as e:
            # 请求错误（连接问题等）
            logger.error(f"异步请求错误: {str(e)}")
            raise GrokApiError(f"异步请求错误: {str(e)}")
    
    async def _upload_message_as_file(self, message: str) -> UploadFileResponse:
        """
        异步将消息作为文件上传
        
        Args:
            message: 要上传的消息内容
            
        Returns:
            上传文件的响应对象
            
        Raises:
            GrokApiError: 如果上传失败
        """
        # 将消息内容编码为Base64
        content = base64.b64encode(message.encode('utf-8')).decode('utf-8')
        
        # 准备上传请求
        payload = UploadFileRequest(
            content=content,
            fileMimeType="text/plain",
            fileName=f"{generate_uuid()}.txt"
        )
        
        logger.info("正在将消息作为文件上传")
        
        # 发送上传文件请求
        response = await self._do_request(
            method="POST",
            url=UPLOAD_FILE_URL,
            payload=payload.model_dump()
        )
        
        # 解析响应
        response_data = response.json()
        
        # 验证响应
        if "fileMetadataId" not in response_data:
            raise GrokApiError("上传文件错误: 响应中没有fileMetadataId字段")
        
        return UploadFileResponse(**response_data)
    
    async def _parse_streaming_response(self, response: httpx.Response) -> AsyncGenerator[str, None]:
        """
        解析来自Grok 3的流式响应。
        
        Args:
            response: HTTP响应对象
            
        Yields:
            响应令牌字符串
        """
        is_thinking = False
        
        # 逐行读取响应内容
        async for line in response.aiter_lines():
            line = line.strip()
            if not line:
                continue
            
            try:
                # 解析JSON响应
                token_obj = json.loads(line)
                resp_token = ResponseToken(**token_obj)
                
                # 检查是否有有效的token响应
                if (resp_token.result.response and resp_token.result.response.token):
                    # 提取令牌文本
                    token_text = resp_token.result.response.token
                    token_is_thinking = resp_token.result.response.isThinking or False
                    
                    # 根据配置处理思考令牌
                    if self.ignore_thinking and token_is_thinking:
                        continue
                    elif token_is_thinking:
                        if not is_thinking:
                            token_text = "<think>\n" + token_text
                        is_thinking = True
                    elif is_thinking:
                        token_text = token_text + "\n</think>\n\n"
                        is_thinking = False
                    
                    if token_text:
                        yield token_text
                # 忽略其他类型的响应（如conversation、userResponse、finalMetadata等）
                
            except json.JSONDecodeError:
                logger.warning(f"警告: 无法解析JSON: {line}")
            except Exception as e:
                logger.warning(f"警告: 处理响应时出错: {e}")


class SyncGrokClient(BaseGrokClient):
    """
    SyncGrokClient是BaseGrokClient的同步实现。
    使用httpx.Client发送请求，但提供与异步接口兼容的包装。
    """
    
    def __init__(
        self,
        cookie: str,
        is_reasoning: bool = False,
        enable_search: bool = False,
        upload_message: bool = False,
        keep_chat: bool = False,
        ignore_thinking: bool = False,
        timeout: int = 1800,
        proxy: Optional[str] = None
    ):
        """
        创建一个新的SyncGrokClient实例，初始化同步HTTP客户端。
        
        Args:
            cookie: Grok的cookie
            is_reasoning: 是否使用推理模型
            enable_search: 是否在网络中搜索
            upload_message: 是否将消息作为文件上传
            keep_chat: 是否保留聊天历史
            ignore_thinking: 是否在响应中排除思考令牌
            timeout: 请求超时时间（秒）
            proxy: 代理服务器URL
        """
        super().__init__(
            cookie, 
            is_reasoning, 
            enable_search, 
            upload_message, 
            keep_chat, 
            ignore_thinking, 
            timeout, 
            proxy
        )
        
        # 创建同步HTTP客户端
        client_kwargs = {
            "timeout": self.timeout,
            "follow_redirects": True,
            "verify": False  # 禁用SSL验证以兼容自签名证书
        }
        
        # 如果提供了代理，添加到客户端配置
        if self.proxy:
            client_kwargs["proxy"] = self.proxy
            logger.debug(f"创建同步HTTP客户端，使用代理: {self.proxy}")
        
        self.http_client = httpx.Client(**client_kwargs)
        logger.debug("同步HTTP客户端已初始化")
    
    async def close(self):
        """关闭同步HTTP客户端并释放资源（异步兼容接口）"""
        if self.http_client:
            self.http_client.close()
            self.http_client = None
            logger.debug("同步HTTP客户端已关闭")
    
    async def _do_request(self, method: str, url: str, payload: Any) -> httpx.Response:
        """
        同步发送HTTP请求，提供异步兼容接口。
        
        Args:
            method: HTTP方法（GET、POST等）
            url: 请求URL
            payload: 请求负载
            
        Returns:
            HTTP响应对象
            
        Raises:
            GrokApiError: 如果请求失败
        """
        # 将请求负载序列化为JSON
        json_payload = json.dumps(payload)

        # 添加调试日志
        logger.debug(f"同步请求方法: {method}")
        logger.debug(f"请求URL: {url}")
        logger.debug(f"请求负载: {json_payload}")
        
        # 记录代理信息（如果有）
        if self.proxy:
            logger.debug(f"使用同步代理: {self.proxy}")
        
        # 发送请求并处理响应
        try:
            response = self.http_client.request(
                method=method,
                url=url,
                content=json_payload,
                headers=self.headers
            )
            
            logger.debug(f"同步响应状态码: {response.status_code}")
            
            # 检查响应状态码
            if response.status_code != 200:
                try:
                    body = response.text
                    error_msg = f"Grok API同步错误: {response.status_code} {response.reason_phrase}, 响应内容: {body[:500]}"
                except Exception:
                    error_msg = f"Grok API同步错误: {response.status_code} {response.reason_phrase}"
                raise GrokApiError(error_msg)
            
            return response
        except httpx.RequestError as e:
            # 请求错误（连接问题等）
            logger.error(f"同步请求错误: {str(e)}")
            raise GrokApiError(f"同步请求错误: {str(e)}")
    
    async def _upload_message_as_file(self, message: str) -> UploadFileResponse:
        """
        同步将消息作为文件上传，提供异步兼容接口
        
        Args:
            message: 要上传的消息内容
            
        Returns:
            上传文件的响应对象
            
        Raises:
            GrokApiError: 如果上传失败
        """
        # 将消息内容编码为Base64
        content = base64.b64encode(message.encode('utf-8')).decode('utf-8')
        
        # 准备上传请求
        payload = UploadFileRequest(
            content=content,
            fileMimeType="text/plain",
            fileName=f"{generate_uuid()}.txt"
        )
        
        logger.info("正在同步将消息作为文件上传")
        
        # 发送上传文件请求
        response = await self._do_request(
            method="POST",
            url=UPLOAD_FILE_URL,
            payload=payload.model_dump()
        )
        
        # 解析响应
        response_data = response.json()
        
        # 验证响应
        if "fileMetadataId" not in response_data:
            raise GrokApiError("上传文件错误: 响应中没有fileMetadataId字段")
        
        return UploadFileResponse(**response_data)
    
    async def _parse_streaming_response(self, response: httpx.Response) -> AsyncGenerator[str, None]:
        """
        解析同步响应，将其包装为异步生成器。
        
        Args:
            response: HTTP响应对象
            
        Yields:
            响应令牌字符串
        """
        is_thinking = False
        
        # 逐行读取响应内容
        for line in response.iter_lines():
            line = line.strip()
            if not line:
                continue
            
            try:
                # 解析JSON响应
                token_obj = json.loads(line)
                resp_token = ResponseToken(**token_obj)
                
                # 检查是否有有效的token响应
                if (resp_token.result.response and resp_token.result.response.token):
                    # 提取令牌文本
                    token_text = resp_token.result.response.token
                    token_is_thinking = resp_token.result.response.isThinking or False
                    
                    # 根据配置处理思考令牌
                    if self.ignore_thinking and token_is_thinking:
                        continue
                    elif token_is_thinking:
                        if not is_thinking:
                            token_text = "<think>\n" + token_text
                        is_thinking = True
                    elif is_thinking:
                        token_text = token_text + "\n</think>\n\n"
                        is_thinking = False
                    
                    if token_text:
                        yield token_text
                # 忽略其他类型的响应
                
            except json.JSONDecodeError:
                logger.warning(f"警告: 无法解析JSON: {line}")
            except Exception as e:
                logger.warning(f"警告: 处理响应时出错: {e}")


# 向后兼容的类别名
GrokClient = AsyncGrokClient 