from typing import Optional, List, Union

from pydantic import BaseModel, Field


# OpenAI API兼容的消息结构体
class OpenAIChatCompletionMessage(BaseModel):
    """OpenAI API兼容的消息结构体"""
    role: str = Field(..., description="消息角色 (system, user, assistant)")
    content: str = Field(..., description="消息内容")


# OpenAI API兼容的流式响应选择结构体
class OpenAIChatCompletionChunkChoice(BaseModel):
    """OpenAI API兼容的流式响应选择结构体"""
    index: int = Field(..., description="选择索引")
    delta: OpenAIChatCompletionMessage = Field(..., description="增量消息")
    finish_reason: Optional[str] = Field(None, description="完成原因")


# OpenAI的流式响应格式
class OpenAIChatCompletionChunk(BaseModel):
    """表示OpenAI的流式响应格式"""
    id: str = Field(..., description="响应ID")
    object: str = Field("chat.completion.chunk", description="对象类型")
    created: int = Field(..., description="创建时间戳")
    model: str = Field(..., description="模型名称")
    choices: List[OpenAIChatCompletionChunkChoice] = Field(..., description="选择数组")


# OpenAI API兼容的完整响应选择结构体
class OpenAIChatCompletionChoice(BaseModel):
    """OpenAI API兼容的完整响应选择结构体"""
    index: int = Field(..., description="选择索引")
    message: OpenAIChatCompletionMessage = Field(..., description="完整消息")
    finish_reason: Optional[str] = Field(None, description="完成原因")


# OpenAI API兼容的使用量统计结构体
class OpenAIChatCompletionUsage(BaseModel):
    """OpenAI API兼容的使用量统计结构体"""
    prompt_tokens: int = Field(..., description="提示令牌数")
    completion_tokens: int = Field(..., description="完成令牌数")
    total_tokens: int = Field(..., description="总令牌数")


# OpenAI的非流式响应格式
class OpenAIChatCompletion(BaseModel):
    """表示OpenAI的非流式响应格式"""
    id: str = Field(..., description="响应ID")
    object: str = Field("chat.completion", description="对象类型")
    created: int = Field(..., description="创建时间戳")
    model: str = Field(..., description="模型名称")
    choices: List[OpenAIChatCompletionChoice] = Field(..., description="选择数组")
    usage: OpenAIChatCompletionUsage = Field(..., description="使用量统计")


# OpenAI API兼容的模型元数据
class ModelData(BaseModel):
    """表示OpenAI兼容响应的模型元数据"""
    id: str = Field(..., description="模型ID")
    object: str = Field("model", description="对象类型")
    owned_by: str = Field(..., description="模型拥有者")


# OpenAI兼容端点的可用模型
class ModelList(BaseModel):
    """包含OpenAI兼容端点的可用模型"""
    object: str = Field("list", description="对象类型")
    data: List[ModelData] = Field(..., description="模型数据列表")


# 聊天补全请求体结构体
class BaseChatCompletionBody(BaseModel):
    """表示POST请求到/v1/chat/completions端点的JSON主体结构"""
    model: str = Field(..., description="模型选择")
    messages: List[OpenAIChatCompletionMessage] = Field(..., description="消息列表")
    stream: bool = Field(False, description="是否流式响应")
    
    
class Grok3ChatCompletionBody(BaseChatCompletionBody):
    grokCookies: Optional[Union[str, List[str]]] = Field(None, description="单个cookie(string)或cookie列表([]string)")
    cookieIndex: Optional[int] = Field(None, description="从1开始，0表示自动轮换选择cookie")
    enableSearch: Optional[int] = Field(None, description="> 0 为 true，== 0 为 false")
    uploadMessage: Optional[int] = Field(None, description="> 0 为 true，== 0 为 false")
    textBeforePrompt: Optional[str] = Field(None, description="提示前的文本")
    textAfterPrompt: Optional[str] = Field(None, description="提示后的文本")
    keepChat: Optional[int] = Field(None, description="> 0 为 true，== 0 为 false")
    ignoreThinking: Optional[int] = Field(None, description="> 0 为 true，== 0 为 false")