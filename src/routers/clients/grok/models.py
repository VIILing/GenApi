from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field


# 工具覆盖模型，对应Go中的ToolOverrides结构体
class ToolOverrides(BaseModel):
    """定义了可以在Grok API中启用或禁用的各种工具"""
    imageGen: bool = Field(default=False, description="图像生成功能")
    trendsSearch: bool = Field(default=False, description="趋势搜索功能") 
    webSearch: bool = Field(default=False, description="网页搜索功能")
    xMediaSearch: bool = Field(default=False, description="X平台媒体搜索功能")
    xPostAnalyze: bool = Field(default=False, description="X平台帖子分析功能")
    xSearch: bool = Field(default=False, description="X平台搜索功能")


# 上传文件请求，对应Go中的UploadFileRequest结构体
class UploadFileRequest(BaseModel):
    """表示上传文件的请求"""
    content: str = Field(..., description="Base64编码的文件内容")
    fileMimeType: str = Field(..., description="文件MIME类型")
    fileName: str = Field(..., description="文件名")


# 上传文件响应，对应Go中的UploadFileResponse结构体
class UploadFileResponse(BaseModel):
    """表示上传文件的响应"""
    fileMetadataId: str = Field(..., description="上传文件的元数据ID")


# 响应令牌，对应Go中的ResponseToken结构体
class ResponseTokenContent(BaseModel):
    """
    表示响应令牌的内容
    按各个字段在生命周期首次出现顺序排序
    """
    userResponse: Optional[Dict[str, Any]] = None
    isThinking: Optional[bool] = None
    isSoftStop: Optional[bool] = None
    responseId: Optional[str] = None
    
    token: Optional[str] = None
    
    finalMetadata: Optional[Dict[str, Any]] = None
    modelResponse: Optional[Dict[str, Any]] = None  # 这里有完整的响应


class ResponseTokenResult(BaseModel):
    """
    表示响应令牌的结果
    按各个字段在生命周期首次出现顺序排序
    """
    response: Optional[ResponseTokenContent] = None
    title: Optional[Dict[str, Any]] = None


class ResponseToken(BaseModel):
    """表示来自Grok 3 Web API的单个令牌响应"""
    result: ResponseTokenResult


# GrokClient类配置，用于Python类定义，对应Go中的GrokClient结构体
class GrokClientConfig(BaseModel):
    """定义了与Grok 3 Web API交互的客户端配置"""
    headers: Dict[str, str] = Field(..., description="HTTP请求的头信息")
    isReasoning: bool = Field(False, description="是否使用推理模型的标志")
    enableSearch: bool = Field(False, description="是否在网络中搜索的标志")
    uploadMessage: bool = Field(False, description="是否将消息作为文件上传的标志")
    keepChat: bool = Field(False, description="是否保留聊天历史的标志")
    ignoreThinking: bool = Field(False, description="是否在响应中排除思考令牌的标志") 