"""统一响应体定义。

约定：{code: 0 表示成功, 非 0 表示失败, msg: 提示信息, data: 业务数据}
"""
from typing import Any, Optional

from pydantic import BaseModel


class ApiResponse(BaseModel):
    """统一响应模型。"""
    code: int = 0
    msg: str = "ok"
    data: Optional[Any] = None


def success(data: Any = None, msg: str = "ok") -> dict:
    """构造成功响应。"""
    return {"code": 0, "msg": msg, "data": data}


def error(code: int = 1, msg: str = "error", data: Any = None) -> dict:
    """构造失败响应。"""
    return {"code": code, "msg": msg, "data": data}


# 常用错误码
CODE_SUCCESS = 0
CODE_FAIL = 1
CODE_UNAUTHORIZED = 401
CODE_FORBIDDEN = 403
CODE_NOT_FOUND = 404
CODE_PARAMS_ERROR = 400
CODE_SERVER_ERROR = 500
