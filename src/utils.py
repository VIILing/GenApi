import json
import os
import threading
import uuid
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union
from typing_extensions import Self


# 设置日志
logger = logging.getLogger("GenApi.utils")


class BaseCookie(ABC):
    def __init__(self, index: int, cookie: str, file_name: str):
        self.index = index
        self.classification = self.get_classification()
        self.file_name = file_name
        self.is_enable = True
        self.cookie = cookie
        self.success_count = 0
        self.fail_count = 0
        self.last_success_time = None
        self.last_fail_time = None
        self.last_error = None
        self.is_occupied = False
        self.has_been_deleted = False
        self.continues_error_time = []  # 记录连续失败的时间列表
        self.last_update_times = datetime.now()  # 记录最后更新时间，默认为创建时间
        
    @abstractmethod
    def get_classification(self) -> str:
        pass
        
    def mark_occupied(self):
        """记录占用"""
        self.is_occupied = True
        
    def mark_unoccupied(self, error_msg: Optional[str] = None):
        """记录释放"""
        self.is_occupied = False
        if error_msg is None:
            self.success_count += 1
            self.last_success_time = datetime.now()
            self.continues_error_time = []  # 请求成功时清空连续失败列表
        else:
            self.fail_count += 1
            self.last_fail_time = datetime.now()
            self.last_error = error_msg
            self.continues_error_time.append(datetime.now())  # 请求失败时添加当前时间到失败列表
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取cookie的统计信息
        
        Returns:
            包含cookie统计信息的字典
        """
        return {
            "index": self.index,
            "classification": self.classification,
            "file_name": self.file_name,
            "is_enable": self.is_enable,
            "cookie": self.cookie,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "last_success_time": self.last_success_time.isoformat() if self.last_success_time else None,
            "last_fail_time": self.last_fail_time.isoformat() if self.last_fail_time else None,
            "last_error": self.last_error,
            "is_occupied": self.is_occupied,
            "continues_error_count": len(self.continues_error_time),
            "last_update_times": self.last_update_times.isoformat() if self.last_update_times else None
        }
        
        
class GrokCookie(BaseCookie):
    """
    Grok Cookie对象，包含cookie及其使用统计信息
    """
    def get_classification(self) -> str:
        return "grok"


# 线程安全的cookie轮换计数器
class ThreadSafeCookieManagerClass:
    """
    线程安全的cookie轮换计数器，管理GrokCookie对象
    """
    def __init__(self, cookies: List[str], filenames: List[str]):
        self.lock = threading.Lock()
        self.cookies: dict[int, BaseCookie] = {}
        
        # 初始化GrokCookie对象
        for i, cookie in enumerate(cookies):
            filename = filenames[i] if filenames and i < len(filenames) else ""
            self.cookies[i] = GrokCookie(i, cookie, filename)
            
        self.next_idx = max(self.cookies.keys()) + 1

    def get_cookie(self, classification: Optional[str] = None) -> tuple[Optional[int], Optional[str]]:
        """
        获取下一个可用的cookie
        
        Returns:
            (cookie索引, cookie字符串)的元组，如果没有可用cookie则返回(None, None)
        """
        with self.lock:
            # 筛选可用的cookie
            available_cookies = []
            for cookie in self.cookies.values():
                # 基础筛选条件
                if not cookie.is_enable or cookie.is_occupied or cookie.has_been_deleted:
                    continue
                
                # 分类筛选
                if classification and cookie.classification != classification:
                    continue
                
                # 连续失败策略处理
                if len(cookie.continues_error_time) >= 3:
                    # 如果最后更新时间晚于最后失败时间，清空失败记录并允许使用
                    if cookie.last_update_times > cookie.continues_error_time[-1]:
                        logger.info(f"Cookie {cookie.index} 连续失败但已更新，清空失败记录")
                        cookie.continues_error_time = []
                    # 如果最后失败时间超过24小时，允许尝试一次
                    elif datetime.now() - cookie.continues_error_time[-1] > timedelta(hours=24):
                        logger.info(f"Cookie {cookie.index} 连续失败但超过24小时，允许尝试")
                    # 否则不允许使用
                    else:
                        logger.info(f"Cookie {cookie.index} 连续失败且未更新，跳过使用")
                        continue
                
                available_cookies.append(cookie)
            
            if not available_cookies:
                logger.warning("没有可用的Cookie，所有Cookie都在使用中或不符合使用条件")
                return None, None
            
            # 选择使用次数最少的cookie
            min_use = min(available_cookies, key=lambda x: (x.success_count + x.fail_count))
            min_use.mark_occupied()
            
            return min_use.index, min_use.cookie
   
    def release_cookie(self, cookie_index: int, error_msg: str = None):
        """
        释放指定cookie索引并更新其统计信息
        
        Args:
            cookie_index: cookie索引
            error_msg: 如果失败，错误信息
        """
        with self.lock:
            if cookie_index is not None and cookie_index in self.cookies:
                # 释放 cookie 并更新统计信息
                self.cookies[cookie_index].mark_unoccupied(error_msg)
                    
                # 如果是403错误，记录特殊日志
                if error_msg and "403" in error_msg:
                    logger.warning(f"Cookie {cookie_index} 收到403错误: {error_msg}")
    
    def get_cookie_stats(self) -> List[Dict[str, Any]]:
        """
        获取所有cookie的统计信息
        
        Returns:
            包含所有cookie统计信息的列表
        """
        with self.lock:
            return [cookie.get_stats() for cookie in self.cookies.values() if not cookie.has_been_deleted]
        
    @classmethod
    def load_cookies_from_files(cls) -> Self:
        """
        从指定目录加载所有的.txt文件内容作为cookies
        
        Args:
            dir_path: 包含cookie文件的目录路径
            
        Returns:
            ThreadSafeCookieManagerClass实例
        """
        cookies = []
        filenames = []
        
        # 确保目录存在
        os.makedirs("cookies", exist_ok=True)
        
        # 读取并处理所有文件
        for file_path in os.listdir("cookies"):
            try:
                with open(f"cookies/{file_path}", "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        cookies.append(content)
                        filenames.append(file_path)
                        logger.info(f"已加载cookie文件: {file_path}")
            except Exception as e:
                logger.warning(f"警告: 无法读取cookie文件 {file_path}: {e}")
        
        return cls(cookies, filenames)
    
    def update_cookie(self, cookie_index: int, cookie: str) -> tuple[bool, str]:
        """
        更新指定索引的cookie
        
        Args:
            cookie_index: cookie索引
            cookie: 新的cookie字符串
            
        Returns:
            (是否成功, 成功或失败信息)的元组
        """
        with self.lock:
            if cookie_index is None or cookie_index not in self.cookies:
                return False, "cookie索引不存在"
            else:
                self.cookies[cookie_index].cookie = cookie
                self.cookies[cookie_index].continues_error_time = []  # 更新cookie时清空连续失败列表
                self.cookies[cookie_index].last_update_times = datetime.now()  # 更新最后更新时间
                logger.info(f"已在内存中更新cookie: {self.cookies[cookie_index].file_name}")
                
                try:
                    logger.info(f"尝试写入更新后的cookie: {self.cookies[cookie_index].file_name}")
                    with open(f"cookies/{self.cookies[cookie_index].file_name}", "w", encoding="utf-8") as f:
                        f.write(cookie)
                except Exception as e:
                    logger.error(f"更新cookie文件时出错: {str(e)}")
                    return False, f"更新cookie文件时出错: {str(e)}"
            
            return True, "Cookie更新成功"
        
    def is_enable_cookie(self, cookie_index: int, new_status: bool) -> bool:
        """
        启用或禁用指定cookie索引
        
        Args:
            cookie_index: cookie索引
            new_status: 新的启用状态
            
        Returns:
            True: 启用成功
            False: 启用失败
        """
        with self.lock:
            if cookie_index is None or cookie_index not in self.cookies:
                return False, "cookie索引不存在"
            else:
                self.cookies[cookie_index].is_enable = new_status
                return True, "Cookie更新成功"
            
    def add_cookie(self, file_name: str, cookie: str) -> tuple[bool, str]:
        """
        添加新的cookie
        
        Args:
            cookie: 新的cookie字符串    
            file_name: 新的cookie文件名
        """
        
        if file_name in {v.file_name for v in self.cookies.values()}:
            return False, "文件名已存在"
        
        with self.lock:
            try:
                with open(f"cookies/{file_name}", "w", encoding="utf-8") as f:
                    f.write(cookie)
            except Exception as e:
                logger.error(f"添加cookie文件时出错: {str(e)}")
                return False, f"添加cookie文件时出错: {str(e)}"
            
            self.cookies[self.next_idx] = GrokCookie(self.next_idx, cookie, file_name)
            self.cookies[self.next_idx].last_update_times = datetime.now()  # 设置最后更新时间为添加时间
            self.next_idx += 1
            
            return True, "Cookie添加成功"
            
    def delete_cookie(self, cookie_index: int) -> tuple[bool, str]:
        """
        删除指定cookie索引
        
        Args:
            cookie_index: cookie索引
        """
        with self.lock:
            if cookie_index is None or cookie_index not in self.cookies:
                return False, "cookie索引不存在"
            else:
                self.cookies[cookie_index].has_been_deleted = True
                
                try:
                    if os.path.exists(f"cookies/{self.cookies[cookie_index].file_name}"):
                        os.remove(f"cookies/{self.cookies[cookie_index].file_name}")
                except Exception as e:
                    logger.error(f"删除cookie文件时出错: {str(e)}")
                    return True, f"删除cookie文件时出错: {str(e)}"
                
                return True, "Cookie删除成功"


def must_marshal(obj: Any) -> str:
    """
    将给定值序列化为JSON字符串，如果出错则触发异常
    
    Args:
        obj: 要序列化的对象
        
    Returns:
        JSON字符串
    """
    return json.dumps(obj)


def generate_uuid() -> str:
    """
    生成一个UUID字符串
    
    Returns:
        UUID字符串
    """
    return str(uuid.uuid4()) 