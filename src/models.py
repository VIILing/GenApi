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


# OpenAI API兼容的消息结构体，对应Go中的OpenAIChatCompletionMessage
class OpenAIChatCompletionMessage(BaseModel):
    """OpenAI API兼容的消息结构体"""
    role: str = Field(..., description="消息角色 (system, user, assistant)")
    content: str = Field(..., description="消息内容")


# OpenAI API兼容的流式响应选择结构体，对应Go中的OpenAIChatCompletionChunkChoice
class OpenAIChatCompletionChunkChoice(BaseModel):
    """OpenAI API兼容的流式响应选择结构体"""
    index: int = Field(..., description="选择索引")
    delta: OpenAIChatCompletionMessage = Field(..., description="增量消息")
    finish_reason: Optional[str] = Field(None, description="完成原因")


# OpenAI的流式响应格式，对应Go中的OpenAIChatCompletionChunk
class OpenAIChatCompletionChunk(BaseModel):
    """表示OpenAI的流式响应格式"""
    id: str = Field(..., description="响应ID")
    object: str = Field("chat.completion.chunk", description="对象类型")
    created: int = Field(..., description="创建时间戳")
    model: str = Field(..., description="模型名称")
    choices: List[OpenAIChatCompletionChunkChoice] = Field(..., description="选择数组")


# OpenAI API兼容的完整响应选择结构体，对应Go中的OpenAIChatCompletionChoice
class OpenAIChatCompletionChoice(BaseModel):
    """OpenAI API兼容的完整响应选择结构体"""
    index: int = Field(..., description="选择索引")
    message: OpenAIChatCompletionMessage = Field(..., description="完整消息")
    finish_reason: Optional[str] = Field(None, description="完成原因")


# OpenAI API兼容的使用量统计结构体，对应Go中的OpenAIChatCompletionUsage
class OpenAIChatCompletionUsage(BaseModel):
    """OpenAI API兼容的使用量统计结构体"""
    prompt_tokens: int = Field(..., description="提示令牌数")
    completion_tokens: int = Field(..., description="完成令牌数")
    total_tokens: int = Field(..., description="总令牌数")


# OpenAI的非流式响应格式，对应Go中的OpenAIChatCompletion
class OpenAIChatCompletion(BaseModel):
    """表示OpenAI的非流式响应格式"""
    id: str = Field(..., description="响应ID")
    object: str = Field("chat.completion", description="对象类型")
    created: int = Field(..., description="创建时间戳")
    model: str = Field(..., description="模型名称")
    choices: List[OpenAIChatCompletionChoice] = Field(..., description="选择数组")
    usage: OpenAIChatCompletionUsage = Field(..., description="使用量统计")


# OpenAI API兼容的模型元数据，对应Go中的ModelData
class ModelData(BaseModel):
    """表示OpenAI兼容响应的模型元数据"""
    id: str = Field(..., description="模型ID")
    object: str = Field("model", description="对象类型")
    owned_by: str = Field(..., description="模型拥有者")


# OpenAI兼容端点的可用模型，对应Go中的ModelList
class ModelList(BaseModel):
    """包含OpenAI兼容端点的可用模型"""
    object: str = Field("list", description="对象类型")
    data: List[ModelData] = Field(..., description="模型数据列表")


# 请求体结构体，对应Go中的RequestBody
class RequestBody(BaseModel):
    """表示POST请求到/v1/chat/completions端点的JSON主体结构"""
    model: str = Field(..., description="模型选择")
    messages: List[OpenAIChatCompletionMessage] = Field(..., description="消息列表")
    stream: bool = Field(False, description="是否流式响应")
    grokCookies: Optional[Union[str, List[str]]] = Field(None, description="单个cookie(string)或cookie列表([]string)")
    cookieIndex: Optional[int] = Field(None, description="从1开始，0表示自动轮换选择cookie")
    enableSearch: Optional[int] = Field(None, description="> 0 为 true，== 0 为 false")
    uploadMessage: Optional[int] = Field(None, description="> 0 为 true，== 0 为 false")
    textBeforePrompt: Optional[str] = Field(None, description="提示前的文本")
    textAfterPrompt: Optional[str] = Field(None, description="提示后的文本")
    keepChat: Optional[int] = Field(None, description="> 0 为 true，== 0 为 false")
    ignoreThinking: Optional[int] = Field(None, description="> 0 为 true，== 0 为 false")


# GrokClient类配置，用于Python类定义，对应Go中的GrokClient结构体
class GrokClientConfig(BaseModel):
    """定义了与Grok 3 Web API交互的客户端配置"""
    headers: Dict[str, str] = Field(..., description="HTTP请求的头信息")
    isReasoning: bool = Field(False, description="是否使用推理模型的标志")
    enableSearch: bool = Field(False, description="是否在网络中搜索的标志")
    uploadMessage: bool = Field(False, description="是否将消息作为文件上传的标志")
    keepChat: bool = Field(False, description="是否保留聊天历史的标志")
    ignoreThinking: bool = Field(False, description="是否在响应中排除思考令牌的标志") 