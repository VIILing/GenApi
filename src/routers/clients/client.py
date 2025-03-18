import json
from abc import ABC, abstractmethod
from logging import Logger
from typing import Any, Optional, AsyncGenerator
from dataclasses import dataclass

import httpx
import requests as rq


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
    
    async def do_request(self, fetch: bool, method: str, url: str, headers: dict[str, str], payload: Any) -> AsyncGenerator[tuple[Optional[str], Any], None]:
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
        self.logger.debug(f"[发送请求] [异步] [请求方法]: {method}")
        self.logger.debug(f"[发送请求] [异步] [请求地址]: : {url}")
        self.logger.debug(f"[发送请求] [异步] [请求负载]: : {json_payload}")
        
        # 记录代理信息（如果有）
        has_proxy, proxy_url = self.has_proxy()
        if has_proxy:
            self.logger.debug(f"[发送请求] [异步] [请求代理]: : {proxy_url}")
        
        # 发送请求并处理响应
        error_msg = None
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
                yield error_msg, None
            
            yield None, None
        
        except Exception as e:
            # 请求错误（连接问题等）
            error_msg = f"异步请求过程中，出现非预期的错误: {str(e)}"
            self.logger.error(error_msg)
            yield error_msg, None
            
        # 流式读取数据块
        if error_msg is not None:
            return
        if fetch is False:
            return
        
        try:
            async for line in response.aiter_lines():
                yield None, line
        except Exception as e:
            # 请求错误（连接问题等）
            error_msg = f"异步读取数据块的过程中，出现非预期的错误: {str(e)}"
            self.logger.error(error_msg)
            yield error_msg, None
        finally:
            await response.aclose()


class SyncClient(AbsNetClient, ABC):
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
        
        self.http_client = rq.session(**client_kwargs)
        logger.debug("同步HTTP客户端已初始化")
        
    def has_proxy(self) -> tuple[bool, str]:
        if 'proxy' in self.client_kwargs:
            return True, self.client_kwargs['proxy']
        else:
            return False, ''
    
    async def close(self):
        """
        关闭同步HTTP客户端并释放资源
        """
        if self.http_client:
            self.http_client.close()
            self.http_client = None
            self.logger.debug("同步HTTP客户端已关闭")
    
    async def do_request(self, fetch: bool, method: str, url: str, headers: dict[str, str], payload: Any) -> tuple[Optional[str], Any]:
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
            response = await self.http_client.request(
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
                    error_msg = f"同步请求错误，响应码: {response.status_code} {response.reason_phrase}, 响应内容: {body[:500]}"
                except Exception as e:
                    error_msg = f"提取非200同步响应信息时，触发非预期异常: {e}"
                    
            if error_msg is not None:
                return error_msg, None
        
        except Exception as e:
            # 请求错误（连接问题等）
            error_msg = f"异步请求过程中，出现非预期的错误: {str(e)}"
            self.logger.error(error_msg)
            return error_msg, None
        
        # 一次性读取全部数据块
        if fetch is False:
            return
        
        try:
            content = response.content
            return None, content
        except Exception as e:
            # 请求错误（连接问题等）
            error_msg = f"同步读取数据块的过程中，出现非预期的错误: {str(e)}"
            self.logger.error(error_msg)
            return error_msg, None
        finally:
            response.close()
            
            
class RequestParams:
    url: str
    headers: dict[str, str]
    payload: Optional[dict[str, Any]]


class ModelClient(ABC):
    
    @abstractmethod
    def get_model_name(self) -> str:
        """
        """
        
    @abstractmethod
    def generate_request_params(self, message: str, request_dict: dict[str, Any]) -> RequestParams:
        """
        """
    
    @abstractmethod
    async def async_stream_response(self, message: str) -> AsyncGenerator[str, None]:
        """
        """
    
    @abstractmethod
    async def async_full_response(self, message: str) -> str:
        """
        """
        
    @abstractmethod
    def sync_full_response(self, message: str) -> str:
        """
        """
