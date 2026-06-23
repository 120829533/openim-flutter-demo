"""Redis 异步客户端模块。

使用 redis-py 的异步 API（redis.asyncio）。
"""
import logging
from typing import Optional

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

# 全局 Redis 客户端（在应用启动事件中初始化）
_redis: Optional[aioredis.Redis] = None


async def init_redis() -> None:
    """初始化 Redis 异步客户端。"""
    global _redis
    if _redis is not None:
        return
    _redis = aioredis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD or None,
        db=settings.REDIS_DB,
        decode_responses=True,
    )
    # 测试连接
    try:
        await _redis.ping()
        logger.info("Redis 连接成功: %s:%s db=%s", settings.REDIS_HOST, settings.REDIS_PORT, settings.REDIS_DB)
    except Exception as e:
        logger.error("Redis 连接失败: %s", e)
        raise


async def close_redis() -> None:
    """关闭 Redis 连接。"""
    global _redis
    if _redis is not None:
        await _redis.close()
        _redis = None
        logger.info("Redis 连接已关闭")


def get_redis() -> aioredis.Redis:
    """获取当前 Redis 客户端。"""
    if _redis is None:
        raise RuntimeError("Redis 客户端尚未初始化，请先调用 init_redis()")
    return _redis


# ===== Redis key 约定（与 Java 服务保持一致）=====

def key_online(user_id: str) -> str:
    """在线状态 key: online:{user_id}"""
    return f"online:{user_id}"


def key_unread(user_id: str) -> str:
    """未读计数 key: unread:{user_id} (hash)"""
    return f"unread:{user_id}"


def key_conv_list(user_id: str) -> str:
    """会话列表 key: conv_list:{user_id} (sorted set)"""
    return f"conv_list:{user_id}"


def key_vcode(phone: str) -> str:
    """验证码 key: vcode:{phone}"""
    return f"vcode:{phone}"


def key_token(token: str) -> str:
    """token key: token:{token}"""
    return f"token:{token}"
