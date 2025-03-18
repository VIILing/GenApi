# 内置库
import logging
import os
import secrets
from typing import Optional, Annotated

# 三方库
from fastapi import HTTPException, Depends, status, APIRouter
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

# 本地
from init import ViewerUser, AdminUser, CookieManager

_Security = HTTPBasic()


RootRouter = APIRouter()
logger = logging.getLogger("GenApi.chat")


def verify_viewer(
    credentials: Annotated[HTTPBasicCredentials, Depends(_Security)],
):
    current_username_bytes = credentials.username.encode("utf8")
    if current_username_bytes not in ViewerUser:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    current_password_bytes = ViewerUser[current_username_bytes]
    is_correct_password = secrets.compare_digest(
        current_password_bytes, credentials.password.encode("utf8")
    )
    if not is_correct_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def verify_admin(
    credentials: Annotated[HTTPBasicCredentials, Depends(_Security)],
):
    current_username_bytes = credentials.username.encode("utf8")
    if current_username_bytes not in AdminUser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    current_password_bytes = AdminUser[current_username_bytes]
    is_correct_password = secrets.compare_digest(
        current_password_bytes, credentials.password.encode("utf8")
    )
    if not is_correct_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    return credentials.username


@RootRouter.get("/logout")
async def logout():
    # 返回一个 401 状态码，并设置 WWW-Authenticate 头来提示客户端重新认证
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication cleared",
        headers={"WWW-Authenticate": "Basic"}
    )


with open(os.path.join(os.path.split(__file__)[0], '..', 'resources', 'amis_template.html'), 'r', encoding='utf-8') as _fn:
    AmisTemplate = _fn.read()


PageJsonCache: dict[str, str] = dict()
for _root, _dirs, _files in os.walk(os.path.join(os.path.split(__file__)[0], '..', 'resources', 'pages')):
    for _name in _files:
        with open(os.path.join(_root, _name), 'r', encoding='utf-8') as _fn:
            _json_content = _fn.read()
        PageJsonCache[_name] = _json_content


CUSTOM_500_ERROR_HTML = """
<html>
    <head>
        <title>Server Error</title>
    </head>
    <body>
        <h1>500 - Internal Server Error</h1>
        <p>Something went wrong. Please try again later.</p>
    </body>
</html>
"""


def render_html(json_content: str) -> HTMLResponse:
    return HTMLResponse(content=AmisTemplate.format(json_body=json_content), status_code=200)


@RootRouter.get("/web/setting/cookie_manager")
async def web_setting_cookie_manager(_: str = Depends(verify_viewer)):
    json_content = PageJsonCache.get("cookie_manager.json")
    if json_content is None:
        return HTMLResponse(content=CUSTOM_500_ERROR_HTML, status_code=500)
    return render_html(json_content)


@RootRouter.get("/api/setting/cookie-stats")
async def get_cookie_stats(
    cookie_index: Optional[int] = None,
    _: str = Depends(verify_viewer)
):
    """
    获取所有cookie的统计信息
    
    Returns:
        包含所有cookie统计信息的列表
    """
    if not CookieManager:
        raise HTTPException(status_code=404, detail="Cookie管理器未初始化")
        
    try:
        stats = {v['index']: v for v in CookieManager.get_cookie_stats()}
        if cookie_index is not None:
            if cookie_index not in stats:
                raise HTTPException(status_code=404, detail="Cookie索引不存在")
            return stats[cookie_index]
        return list(stats.values())
    except Exception as e:
        logger.error(f"获取cookie统计信息时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取cookie统计信息失败: {str(e)}") from e


class UpdateCookieRequest(BaseModel):
    cookie_index: int
    cookie: str
    

@RootRouter.post("/api/setting/update-cookie")
async def update_cookie(
    request: UpdateCookieRequest,
    _: str = Depends(verify_admin)
):
    if not CookieManager:
        raise HTTPException(status_code=404, detail="Cookie管理器未初始化") 
    
    try:
        success, msg = CookieManager.update_cookie(request.cookie_index, request.cookie)
        if not success:
            return {
                "status": 1,
                "msg": msg,
                "data": None
        }
        return {
            "status": 0,
            "msg": "Cookie更新成功",
            "data": {
                "cookie_index": request.cookie_index,
                "cookie": request.cookie
            }
        }
    except Exception as e:
        logger.error(f"更新Cookie时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"更新Cookie失败: {str(e)}") from e


class IsEnableCookieRequest(BaseModel):
    cookie_index: int
    is_enable: bool
    

@RootRouter.post("/api/setting/is-enable-cookie")
async def is_enable_cookie(
    request: IsEnableCookieRequest,
    _: str = Depends(verify_admin)
):
    if not CookieManager:
        raise HTTPException(status_code=404, detail="Cookie管理器未初始化") 
    
    try:
        success, msg = CookieManager.is_enable_cookie(request.cookie_index, request.is_enable)
        if not success:
            return {
                "status": 1,
                "msg": msg,
                "data": None
        }
        return {
            "status": 0,
            "msg": "Cookie更新成功",
            "data": None
        }
    except Exception as e:
        logger.error(f"更新Cookie时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"更新Cookie失败: {str(e)}") from e


class AddCookieRequest(BaseModel):
    file_name: str
    cookie: str


@RootRouter.post("/api/setting/add-cookie")
async def add_cookie(
    request: AddCookieRequest,
    _: str = Depends(verify_admin)
):
    if not CookieManager:
        raise HTTPException(status_code=404, detail="Cookie管理器未初始化") 
    
    try:
        success, msg = CookieManager.add_cookie(request.file_name, request.cookie)
        if not success:
            return {
                "status": 1,
                "msg": msg,
                "data": None
            }
        return {
            "status": 0,
            "msg": "Cookie添加成功",
            "data": {
                "cookie_index": CookieManager.next_idx - 1,
                "file_name": request.file_name
            }
        }
    except Exception as e:
        logger.error(f"添加Cookie时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"添加Cookie失败: {str(e)}") from e


class DeleteCookieRequest(BaseModel):
    cookie_index: int


@RootRouter.post("/api/setting/delete-cookie")
async def delete_cookie(
    request: DeleteCookieRequest,
    _: str = Depends(verify_admin)
):
    if not CookieManager:
        raise HTTPException(status_code=404, detail="Cookie管理器未初始化") 
    
    try:
        success, msg = CookieManager.delete_cookie(request.cookie_index)
        if not success:
            return {
                "status": 1,
                "msg": msg,
                "data": None
            }
        return {
            "status": 0,
            "msg": "Cookie删除成功",
            "data": None
        }
    except Exception as e:
        logger.error(f"删除Cookie时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除Cookie失败: {str(e)}") from e
    
