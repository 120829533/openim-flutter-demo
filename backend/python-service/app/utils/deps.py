"""FastAPI 依赖：从 Authorization Bearer 解析 JWT，获取当前用户。"""
import logging
from typing import Optional

from fastapi import Depends, Header, HTTPException, status

from app.database import fetchone
from app.redis_client import get_redis, key_token
from app.utils.security import decode_access_token

logger = logging.getLogger(__name__)


async def get_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    """解析 Authorization 头中的 Bearer token，返回当前用户记录（dict）。

    流程：
    1. 从 Authorization 头取出 Bearer token
    2. 解析 JWT 拿到 user_id
    3. 校验 Redis token:{token} 是否存在（支持登出失效）
    4. 从数据库查询用户记录返回
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少认证信息")

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的认证信息")

    # 解析 JWT
    payload = decode_access_token(token)
    if not payload or "user_id" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证已过期或无效")

    user_id = payload["user_id"]

    # 校验 Redis 中的 token 是否仍然有效（登出会删除）
    try:
        redis = get_redis()
        stored_user_id = await redis.get(key_token(token))
        if not stored_user_id or stored_user_id != user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录态已失效，请重新登录")
    except HTTPException:
        raise
    except Exception as e:
        # Redis 异常时不阻断鉴权（降级），仅记录日志
        logger.warning("校验 Redis token 失败，降级放行: %s", e)

    # 查询用户
    user = await fetchone("SELECT * FROM users WHERE user_id = %s", (user_id,))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")

    if user.get("status") == 2:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")

    return user
