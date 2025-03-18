import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from logging import Logger
from typing import Any, Optional, AsyncGenerator, Union

import httpx
import requests as rq

from routers.openai_models import (
    BaseChatCompletionBody,
    OpenAIChatCompletion,
    OpenAIChatCompletionChoice,
    OpenAIChatCompletionMessage,
    OpenAIChatCompletionUsage,
    OpenAIChatCompletionChunk,
    OpenAIChatCompletionChunkChoice,
)
from utils import generate_uuid, must_marshal, CookieMsg


class AbsNetClient(ABC):
    """
    """
    
    def __init__(
        self,
        logger: Logger,
        client_kwargs: dict[str, Any]
    ):
        """
        """
        self.logger = logger
        self.client_kwargs = client_kwargs
        
    @staticmethod
    def get_timeout() -> int:
        return 1800
        
    @abstractmethod
    def has_proxy(self) -> tuple[bool, str]:
        """
        """
    
    @abstractmethod
    async def close(self):
        """
        关闭HTTP客户端并释放资源
        """
        

@dataclass(frozen=True)
class RequestResponse:
    error_msg: Union[str, None]
    data: Union[bytes, None]
    status_code: Union[int, None]        


class AsyncNetClient(AbsNetClient, ABC):
    """
    """
    
    def __init__(
        self,
        logger: Logger,
        client_kwargs: dict[str, Any]
    ):
        """
        """
        super().__init__(logger, client_kwargs)
        
        # 创建异步HTTP客户端        
        has_proxy, proxy_url = self.has_proxy()
        if has_proxy:
            self.logger.debug(f"创建异步HTTP客户端，使用代理: {proxy_url}")
        
        self.http_client = httpx.AsyncClient(**client_kwargs)
        logger.debug("异步HTTP客户端已初始化")
        
    def has_proxy(self) -> tuple[bool, str]:
        if 'proxy' in self.client_kwargs:
            return True, self.client_kwargs['proxy']
        else:
            return False, ''
    
    async def close(self):
        """
        关闭异步HTTP客户端并释放资源
        """
        if self.http_client:
            await self.http_client.aclose()
            self.http_client = None
            self.logger.debug("异步HTTP客户端已关闭")

    async def do_request(self, fetch: bool, stream: bool, method: str, url: str, headers: dict[str, str], payload: Any) -> AsyncGenerator[RequestResponse, None]:
        """
        """

        # 将请求负载序列化为JSON
        json_payload = json.dumps(payload)

        # 添加调试日志
        self.logger.debug(f"[发送请求] [异步] [请求方法]: {method}")
        self.logger.debug(f"[发送请求] [异步] [请求地址]: : {url}")
        self.logger.debug(f"[发送请求] [异步] [请求负载]: : {json_payload}")
        
        # 记录代理信息（如果有）
        has_proxy, proxy_url = self.has_proxy()
        if has_proxy:
            self.logger.debug(f"[发送请求] [异步] [请求代理]: : {proxy_url}")
        
        # 发送请求并处理响应
        error_msg = None
        response = None
        try:
            response = await self.http_client.request(
                method=method,
                url=url,
                content=json_payload,
                headers=headers
            )
            
            self.logger.debug(f"[发送请求] [异步] [响应状态码]: : {response.status_code}")
            
            # 检查响应状态码
            if response.status_code != 200:
                try:
                    body = response.text
                    error_msg = f"异步请求错误，响应码: {response.status_code} {response.reason_phrase}, 响应内容: {body[:500]}"
                except Exception as e:
                    error_msg = f"提取非200异步响应信息时，触发非预期异常: {e}"
            
                yield RequestResponse(error_msg, None, response.status_code)
        
        except Exception as e:
            # 请求错误（连接问题等）
            error_msg = f"异步请求过程中，出现非预期的错误: {str(e)}"
            self.logger.error(error_msg)
            yield RequestResponse(error_msg, None, None)
            
        # 流式读取数据块
        if error_msg is not None or response is None:  # 只是为了消除愚蠢的 response 未定义警告。。。
            return
        if fetch is False:
            return
        
        if stream:
            try:
                async for line in response.aiter_lines():
                    yield RequestResponse(None, line.encode('utf-8'), None)
            except Exception as e:
                # 请求错误（连接问题等）
                error_msg = f"异步读取数据块的过程中，出现非预期的错误: {str(e)}"
                self.logger.error(error_msg)
                yield RequestResponse(error_msg, None, None)
        else:
            yield RequestResponse(None, response.content, None)


class SyncNetClient(AbsNetClient, ABC):
    """
    """
    
    def __init__(
        self,
        logger: Logger,
        client_kwargs: dict[str, Any]
    ):
        """
        """
        super().__init__(logger, client_kwargs)
        
        # 创建同步HTTP客户端
        has_proxy, proxy_url = self.has_proxy()
        if has_proxy:
            self.logger.debug(f"创建异步HTTP客户端，使用代理: {proxy_url}")
        
        self.http_client = rq.Session()
        for k, v in client_kwargs.items():
            self.http_client.k = v
        logger.debug("同步HTTP客户端已初始化")
        
    def has_proxy(self) -> tuple[bool, str]:
        if 'proxy' in self.client_kwargs:
            return True, self.client_kwargs['proxy']
        else:
            return False, ''
   
    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False
    
    async def close(self):
        """
        关闭同步HTTP客户端并释放资源
        """
        self._enter_flag = False
        
        if self.http_client:
            self.http_client.close()
            self.http_client = None
            self.logger.debug("同步HTTP客户端已关闭")
    
    async def do_request(self, fetch: bool, method: str, url: str, headers: dict[str, str], payload: Union[dict, list]) -> RequestResponse:
        """
        """
        
        if self._enter_flag is False:
            raise RuntimeError('You must set instance to with ... block')
        
        # 将请求负载序列化为JSON
        json_payload = json.dumps(payload)

        # 添加调试日志
        self.logger.debug(f"[发送请求] [同步] [请求方法]: {method}")
        self.logger.debug(f"[发送请求] [同步] [请求地址]: : {url}")
        self.logger.debug(f"[发送请求] [同步] [请求负载]: : {json_payload}")
        
        # 记录代理信息（如果有）
        has_proxy, proxy_url = self.has_proxy()
        if has_proxy:
            self.logger.debug(f"[发送请求] [同步] [请求代理]: : {proxy_url}")
        
        # 发送请求并处理响应
        error_msg = None
        try:
            response = self.http_client.request(
                method=method,
                url=url,
                json=json_payload,
                headers=headers
            )
            
            self.logger.debug(f"[发送请求] [同步] [响应状态码]: : {response.status_code}")
            
            # 检查响应状态码
            if response.status_code != 200:
                try:
                    body = response.text
                    error_msg = f"同步请求错误，响应码: {response.status_code}, 响应内容: {body[:500]}"
                except Exception as e:
                    error_msg = f"提取非200同步响应信息时，触发非预期异常: {e}"
                    
                return RequestResponse(error_msg, None, response.status_code)
        
        except Exception as e:
            # 请求错误（连接问题等）
            error_msg = f"异步请求过程中，出现非预期的错误: {str(e)}"
            self.logger.error(error_msg)
            return RequestResponse(error_msg, None, None)
        
        # 一次性读取全部数据块
        if fetch is False:
            return RequestResponse(None, None, None)
        
        try:
            content = response.content
            return RequestResponse(error_msg, content, response.status_code)
        except Exception as e:
            # 请求错误（连接问题等）
            error_msg = f"同步读取数据块的过程中，出现非预期的错误: {str(e)}"
            self.logger.error(error_msg)
            return RequestResponse(error_msg, None, response.status_code)
            

@dataclass()
class RequestParams:
    message: str
    url: str
    headers: dict[str, str]
    payload: Optional[dict[str, Any]]
    proxy: Union[str, None]


# 为什么要单独设置这么一个错误类出来，是因为我想实现被验证码拦截后，无感切换其他Cookie重试的功能
# 当然，现在还没有实现，还只是张饼就是了
class CaptchaBlockError(Exception):
    pass


class AbsModelClient(ABC):
    
    def __init__(
        self,
        logger: Logger,
        client_kwargs: dict[str, Any]
    ):
        self.logger = logger
        self.client_kwargs = client_kwargs
        
    @abstractmethod
    def get_model_name(self):
        """
        返回模型的名字。
        模型的不同版本被视为同一种，例如 grok-3 和 grok-3-reasoning 这两个模型，因为接口一致，所以应该返回 grok3 这个字符串。
        """
        
    @abstractmethod
    def generate_request_params(self, req_body: BaseChatCompletionBody, cookie: CookieMsg) -> RequestParams:
        """
        """
    
    @abstractmethod
    async def async_stream_response(self, req_params: RequestParams) -> AsyncGenerator[RequestResponse, None]:
        """
        """
    
    @abstractmethod
    async def async_full_response(self, req_params: RequestParams) -> RequestResponse:
        """
        """
        
    @abstractmethod
    def sync_full_response(self, req_params: RequestParams) -> RequestResponse:
        """
        """
        
    def create_openai_full_response_body(self, content: str) -> dict[str, Any]:
        """
        为非流式完整请求创建OpenAI响应体
        
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
        return must_marshal(chunk.model_dump())  # sse_starlette 模块会自动附加 data: 和 \n\n 部分
