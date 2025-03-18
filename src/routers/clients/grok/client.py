import base64
import json
import logging
from typing import Any, Optional, AsyncGenerator

from routers.clients.client import AsyncNetClient, AbsModelClient, RequestParams, RequestResponse
from routers.openai_models import (
    Grok3ChatCompletionBody
)
from utils import generate_uuid, CookieMsg
from routers.clients.grok.constants import (
    NEW_CHAT_URL,
    UPLOAD_FILE_URL,
    GROK3_REASONING_MODEL_NAME,
    DEFAULT_HEADERS,
    MESSAGE_CHARS_LIMIT,
    DEFAULT_UPLOAD_MESSAGE_PROMPT,
    DEFAULT_UPLOAD_MESSAGE,
    DEFAULT_BEFORE_TEXT_PROMPT,
)
from routers.clients.grok.models import ToolOverrides, UploadFileRequest

logger = logging.getLogger('GenApi.GrokClient')


class Grok3Client(AbsModelClient):
    
    def get_model_name(self):
        """
        返回模型的名字。
        模型的不同版本被视为同一种，例如 grok-3 和 grok-3-reasoning 这两个模型，因为接口一致，所以应该返回 grok3 这个字符串。
        """
        return 'grok3'
        
    def generate_request_params(self, req_body: Grok3ChatCompletionBody, cookie: CookieMsg) -> RequestParams:
        """
        """

        headers = DEFAULT_HEADERS.copy()
        headers['cookie'] = cookie.cookie

        # 根据是否启用搜索来设置工具覆盖
        tool_overrides: Any = ToolOverrides().model_dump()

        # 生成消息文本
        before_prompt = req_body.textBeforePrompt  if req_body.textBeforePrompt is not None else DEFAULT_BEFORE_TEXT_PROMPT
        after_prompt = req_body.textAfterPrompt  if req_body.textAfterPrompt is not None else ''
        message_text = f"{before_prompt}\n"
        for msg in req_body.messages:
            message_text += f"\n[[{msg.role}]]\n{msg.content}"
        message_text += f"\n{after_prompt}"
        
        # enable_search = False
        # if self.enable_search:
        #     tool_overrides = {}  # 空字典表示使用默认配置
        
        # 处理文件附件
        # file_attachments: List[str] = []
        # if file_id:
        #     file_attachments = [file_id]
        
        # 构建并返回完整的请求负载
        payload = {
            "disableSearch": False,
            "enableImageGeneration": True,
            "enableImageStreaming": True,
            "enableSideBySide": True,
            "fileAttachments": [],
            "forceConcise": False,
            "imageAttachments": [],
            "imageGenerationCount": 2,
            "isPreset": False,
            "isReasoning": req_body.model == GROK3_REASONING_MODEL_NAME,
            "message": message_text,
            "modelName": "grok-3",
            "returnImageBytes": False,
            "returnRawGrokInXaiRequest": False,
            "sendFinalMetadata": True,
            "temporary": True,
            "toolOverrides": tool_overrides,
            "webpageUrls": [],
        }
        return RequestParams(
            message_text,
            NEW_CHAT_URL,
            headers,
            payload,
            None
        )
        
    async def async_upload_message_as_file(self, message: str, req_params: RequestParams) -> Optional[str]:
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
        with AsyncNetClient(self.logger, self.client_kwargs) as client:
            response = await client.do_request(
                fetch=True,
                stream=False,
                method="POST",
                url=UPLOAD_FILE_URL,
                headers=req_params.headers,
                payload=payload.model_dump()
            )

        # 验证响应
        if response.error_msg is not None or "fileMetadataId" not in json.loads(response.data.decode('utf-8')):
            self.logger.info("上传文件错误: 响应中没有fileMetadataId字段")
            return None
        
        return json.loads(response.data.decode('utf-8'))['fileMetadataId']
    
    async def async_stream_response(self, req_params: RequestParams) -> AsyncGenerator[RequestResponse, None]:
        """
        """
        logger.info('准备发送消息')

        # 处理超长消息上传为文件
        if DEFAULT_UPLOAD_MESSAGE and len(req_params.message) > MESSAGE_CHARS_LIMIT:
            logger.info('消息过长，以文件的形式上传。')
            file_meta_data_id = await self.async_upload_message_as_file(req_params.message, req_params)

            if file_meta_data_id is None:
                raise RuntimeError('Grok3 上传文件失败')

            req_params.payload['fileAttachments'] = [file_meta_data_id]
            req_params.payload['message'] = DEFAULT_UPLOAD_MESSAGE_PROMPT
            req_params.message = DEFAULT_UPLOAD_MESSAGE_PROMPT
            logger.info('上传消息文件成功。')
        
        # 准备请求负载并发送请求
        logger.info('发送流式响应请求')
        with AsyncNetClient(self.logger, self.client_kwargs) as client:
            async for token in client.do_request(
                fetch=True,
                stream=True,
                method="POST",
                url=UPLOAD_FILE_URL,
                headers=req_params.headers,
                payload=req_params.payload
            ):
                yield token
    
    async def async_full_response(self, req_params: RequestParams) -> RequestResponse:
        """
        """
        msg = b''
        found_error = False
        async for chunk in self.async_stream_response(req_params):
            if found_error:
                break
            if chunk.error_msg is not None:
                found_error = True
                yield RequestResponse(chunk.error_msg, None, None)
            msg += chunk.data
        if not found_error:
            yield RequestResponse(None, msg, None)
        
    def sync_full_response(self, req_params: RequestParams) -> RequestResponse:
        """
        """
