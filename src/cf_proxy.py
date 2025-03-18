import logging

logger = logging.getLogger('GenApi.cf_proxy')


class BrightDataProxy:
    """
    Bright Data 代理配置工具类
    
    提供用于配置 Bright Data 代理的静态方法，适用于同步和异步 httpx 客户端。
    """

    @staticmethod
    def get_normal_proxy(proxy_url: str) -> str:
        """
        返回可直接用于 httpx 客户端的代理 URL
        
        此方法返回的代理 URL 适用于 httpx.Client 和 httpx.AsyncClient 的 proxy 参数。
        对于异步客户端，代理可能无法正常工作，建议在异步客户端失败后使用同步客户端重试。
        
        Args:
            proxy_url: Bright Data 代理 URL
            
        Returns:
            str: 格式化后的代理 URL，直接用于 httpx.Client(proxy=...)
        """
        logger.debug(f"使用标准 Bright Data 代理: {proxy_url}")
        # 直接返回代理 URL 字符串，适用于 proxy 参数
        return proxy_url

    @staticmethod
    def get_country_specific_proxy(proxy_url: str, country_code="us") -> str:
        """
        返回包含国家/地区标识的代理 URL
        
        创建一个附带国家/地区会话标识的代理 URL，适用于需要特定地理位置的请求。
        
        Args:
            proxy_url: Bright Data 代理 URL
            country_code: 国家/地区代码 (例如: "us", "gb")
            
        Returns:
            str: 包含国家/地区标识的代理 URL
        """
        # 创建带有国家/地区标识的会话ID
        session_id = f"session-{country_code}"
        logger.debug(f"创建国家/地区特定会话代理，国家/地区代码: {country_code}")

        _, head, tail = proxy_url.split(':', maxsplit=2)
        
        # 构建代理URL，包含会话ID
        country_proxy_url = f"http:{head}-session-{session_id}:{tail}"
        logger.debug(f"生成的国家/地区特定代理: {country_proxy_url}")
        
        # 直接返回代理 URL 字符串
        return country_proxy_url