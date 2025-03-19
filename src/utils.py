import sqlite3
import json
import logging
import os
import threading
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from typing_extensions import Self

# 设置日志
logger = logging.getLogger("GenApi.utils")


@dataclass(frozen=True)
class CookieMsg:
    index: int
    cookie: str


class BaseCookie(ABC):
    def __init__(self, index: int, cookie: str, file_name: str):
        self._index = index
        self._classification: str = self.get_classification()
        self._file_name: str = file_name
        self._is_enable: bool = True
        self._cookie: str = cookie
        self._success_count: int = 0
        self._fail_count: int = 0
        self._last_success_time: Optional[datetime] = None
        self._last_fail_time: Optional[datetime] = None
        self._last_error: Optional[str] = None
        self._is_occupied: bool = False
        self._has_been_deleted: bool = False
        self._continues_error_time: list[datetime] = []  # 记录连续失败的时间列表
        self._last_update_time: datetime = datetime.now()  # 记录最后更新时间，默认为创建时间

    def get_index(self) -> int:
        return self._index

    @abstractmethod
    def get_classification(self) -> str:
        """
        """

    def get_cookie(self) -> str:
        return self._cookie

    def get_file_name(self) -> str:
        return self._file_name

    def set_file_name(self, new_name: str):
        self._file_name = new_name

    def get_is_enable(self) -> bool:
        return self._is_enable

    def set_is_enable(self, new_status: bool):
        self._is_enable = new_status

    def get_is_occupied(self) -> bool:
        return self._is_occupied

    def get_has_been_deleted(self) -> bool:
        return self._has_been_deleted

    def set_has_been_deleted(self, new_status: bool):
        self._has_been_deleted = new_status

    def get_last_update_time(self) -> datetime:
        return self._last_update_time

    def get_continues_error_count(self) -> int:
        return len(self._continues_error_time)

    def get_continues_error_time_by_index(self, idx: int):
        if abs(idx) >= len(self._continues_error_time):
            raise IndexError(f'Index {idx} out of range self._continues_error_time {self.get_continues_error_count()}')
        return self._continues_error_time[idx]

    def clear_continues_error_time(self):
        self._continues_error_time.clear()

    @staticmethod
    def format_datetime(obj: datetime) -> str:
        return obj.strftime('%Y-%m-%d %H:%M:%S')
        
    def mark_occupied(self):
        """记录占用"""
        self._is_occupied = True
        
    def mark_unoccupied(self, error_msg: Optional[str] = None):
        """记录释放"""
        self._is_occupied = False
        if error_msg is None:
            self._success_count += 1
            self._last_success_time = datetime.now()
            self._continues_error_time = []  # 请求成功时清空连续失败列表
        else:
            self._fail_count += 1
            self._last_fail_time = datetime.now()
            self._last_error = error_msg
            self._continues_error_time.append(datetime.now())  # 请求失败时添加当前时间到失败列表

    def update_cookie(self, new_cookie: str):
        self._cookie = new_cookie
        self._continues_error_time = []
        self._last_update_time = datetime.now()

    def update_file_name(self, new_file_name: str):
        self._file_name = new_file_name

    def update_last_update_time(self, new_update_time: datetime):
        self._last_update_time = new_update_time
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取cookie的统计信息
        
        Returns:
            包含cookie统计信息的字典
        """
        return {
            "index": self._index,
            "classification": self._classification,
            "file_name": self._file_name,
            "is_enable": '启用中' if self._is_enable else '手动禁止中',
            "cookie": self._cookie,
            "success_count": self._success_count,
            "fail_count": self._fail_count,
            "last_success_time": self.format_datetime(self._last_success_time) if self._last_success_time else None,
            "last_fail_time": self.format_datetime(self._last_fail_time) if self._last_fail_time else None,
            "last_error": self._last_error,
            "is_occupied": self._is_occupied,
            "continues_error_count": len(self._continues_error_time),
            "last_update_times": self.format_datetime(self._last_update_time) if self._last_update_time else None
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
    def __init__(self, new_cookies: List[str], new_file_names: List[str]):
        self.lock = threading.Lock()
        self.cookies: dict[int, BaseCookie] = {}

        os.makedirs('data')
        self.conn = sqlite3.connect(
            './data/Cookies.db'
        )
        cursor = self.conn.cursor()
        cursor.execute(
            """
            create table if not exists cookies (
                file_name text PRIMARY KEY,
                cookie text,
                classification text,
                is_enable integer,
                last_update_time text,
                total_success_count integer,
                total_fail_count integer,
                success_count integer,
                fail_count integer,
                continues_error_time text,
                last_success_time text,
                last_fail_time text,
                last_error text
            )
            """.strip()
        )
        self.conn.commit()
        cursor.close()
        
        # 初始化GrokCookie对象
        for i, cookie in enumerate(new_cookies):
            file_name = new_file_names[i] if new_file_names and i < len(new_file_names) else ""
            cookie = GrokCookie(i, cookie, file_name)
            if file_name.endswith('.ban'):
                cookie.set_is_enable(False)
            self.cookies[i] = cookie
            
        self.next_idx = max(self.cookies.keys()) + 1 if len(self.cookies) >= 1 else 0

    def close(self):
        if self.conn:
            self.conn.close()

    @staticmethod
    def filter_alive(cookie_list: list[BaseCookie], classification: Optional[str]) -> list[BaseCookie]:

        alive = []

        for cookie in cookie_list:
            # 基础筛选条件
            if not cookie.get_is_enable() or cookie.get_is_occupied() or cookie.get_has_been_deleted():
                continue

            # 分类筛选
            if classification and cookie.get_classification() != classification:
                continue

            # 连续失败策略处理
            if cookie.get_continues_error_count() >= 3:
                # 如果最后更新时间晚于最后失败时间，清空失败记录并允许使用
                if cookie.get_last_update_time() > cookie.get_continues_error_time_by_index(-1):
                    logger.info(f"Cookie {cookie.get_index()} 连续失败但已更新，清空失败记录")
                    cookie.clear_continues_error_time()
                # 如果最后失败时间超过24小时，允许尝试一次
                elif datetime.now() - cookie.get_continues_error_time_by_index(-1) > timedelta(hours=24):
                    logger.info(f"Cookie {cookie.get_index()} 连续失败但超过24小时，允许尝试")
                # 否则不允许使用
                else:
                    logger.info(f"Cookie {cookie.get_index()} 连续失败且未更新，跳过使用")
                    continue

            alive.append(cookie)

        return alive

    def get_cookie(self, classification: Optional[str] = None) -> Optional[CookieMsg]:
        """
        获取下一个可用的cookie
        
        Returns:
            
        """
        with self.lock:
            # 筛选可用的cookie
            available_cookies = self.filter_alive(list(self.cookies.values()), classification)
            
            if not available_cookies:
                logger.warning("没有可用的Cookie，所有Cookie都在使用中或不符合使用条件")
                return None
            
            # 选择使用次数最少的cookie
            min_use = min(available_cookies, key=lambda x: (x.success_count + x.fail_count))
            min_use.mark_occupied()
            
            return CookieMsg(min_use.get_index(), min_use.get_cookie())
   
    def release_cookie(self, cookie_msg: CookieMsg, error_msg: str = None):
        """
        释放指定cookie索引并更新其统计信息
        """
        with self.lock:
            if cookie_msg.index in self.cookies:
                # 释放 cookie 并更新统计信息
                self.cookies[cookie_msg.index].mark_unoccupied(error_msg)
    
    def get_cookie_stats(self) -> List[Dict[str, Any]]:
        """
        获取所有cookie的统计信息
        
        Returns:
            包含所有cookie统计信息的列表
        """
        with self.lock:
            ret = []
            alive = self.filter_alive(list(self.cookies.values()), None)
            alive_index = {c.get_index() for c in alive}
            for cookie in self.cookies.values():
                if cookie.get_has_been_deleted():
                    continue
                s = cookie.get_stats()
                s['is_alive'] = '存活中' if cookie.get_index() in alive_index else '已死亡'
                ret.append(s)
            return ret
        
    @classmethod
    def load_cookies_from_files(cls) -> Self:
        """
        从指定目录加载所有的.txt文件内容作为cookies
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
    
    def update_cookie(self, cookie_index: int, new_cookie: str) -> tuple[bool, str]:
        """
        更新指定索引的cookie
        
        Args:
            cookie_index: cookie索引
            new_cookie: 新的cookie字符串
            
        Returns:
            (是否成功, 成功或失败信息)的元组
        """
        with self.lock:
            if cookie_index is None or cookie_index not in self.cookies:
                return False, "cookie索引不存在"
            else:

                self.cookies[cookie_index].update_cookie(new_cookie)
                logger.info(f"已在内存中更新cookie: {self.cookies[cookie_index].get_file_name()}")
                
                try:
                    logger.info(f"尝试写入更新后的cookie: {self.cookies[cookie_index].get_file_name()}")
                    with open(f"cookies/{self.cookies[cookie_index].get_file_name()}", "w", encoding="utf-8") as f:
                        f.write(new_cookie)
                except Exception as e:
                    logger.error(f"更新cookie文件时出错: {str(e)}")
                    return False, f"更新cookie文件时出错: {str(e)}"
            
            return True, "Cookie更新成功"
        
    def is_enable_cookie(self, cookie_index: int, new_status: bool) -> tuple[bool, str]:
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
                cookie = self.cookies[cookie_index]
                cookie.set_is_enable(new_status)
                try:
                    old_name = cookie.get_file_name()
                    new_suffix = '' if cookie.get_is_enable() else '.ban'
                    new_name = old_name.rstrip('.ban') + new_suffix
                    need_rename = (old_name != new_name)
                    cookie.set_file_name(new_name)

                    if need_rename and os.path.exists(f'cookies/{old_name}'):
                        os.rename(f'cookies/{old_name}', f'cookies/{new_name}')
                except Exception as e:
                    logger.warning(f'Cookie的启用状态变更，尝试重新改名时，出现未知异常: {e}')
                return True, "Cookie更新成功"
            
    def add_cookie(self, file_name: str, cookie: str) -> tuple[bool, str]:
        """
        添加新的cookie
        
        Args:
            cookie: 新的cookie字符串    
            file_name: 新的cookie文件名
        """
        
        if file_name in {v.get_file_name() for v in self.cookies.values()}:
            return False, "文件名已存在"
        
        with self.lock:
            try:
                with open(f"cookies/{file_name}", "w", encoding="utf-8") as f:
                    f.write(cookie)
            except Exception as e:
                logger.error(f"添加cookie文件时出错: {str(e)}")
                return False, f"添加cookie文件时出错: {str(e)}"
            
            self.cookies[self.next_idx] = GrokCookie(self.next_idx, cookie, file_name)
            self.cookies[self.next_idx].update_last_update_time(datetime.now())  # 设置最后更新时间为添加时间
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
                self.cookies[cookie_index].set_has_been_deleted(True)
                
                try:
                    if os.path.exists(f"cookies/{self.cookies[cookie_index].get_file_name()}"):
                        os.remove(f"cookies/{self.cookies[cookie_index].get_file_name()}")
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
