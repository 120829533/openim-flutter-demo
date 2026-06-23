"""安全工具模块：JWT 签发/校验、bcrypt 密码哈希。"""
import datetime
import logging
from typing import Optional

import bcrypt
import jwt

from app.config import settings

logger = logging.getLogger(__name__)


# ===== 密码哈希 =====

def hash_password(password: str) -> str:
    """使用 bcrypt 对密码进行哈希，返回字符串形式。"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """校验明文密码与 bcrypt 哈希是否匹配。"""
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


# ===== JWT =====

def create_access_token(user_id: str, account: str) -> str:
    """签发 JWT，payload 含 user_id, account, exp。"""
    now = datetime.datetime.now(datetime.timezone.utc)
    expire = now + datetime.timedelta(hours=settings.PYTHON_JWT_EXPIRE_HOURS)
    payload = {
        "user_id": user_id,
        "account": account,
        "exp": expire,
        "iat": now,
    }
    token = jwt.encode(payload, settings.PYTHON_JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token


def decode_access_token(token: str) -> Optional[dict]:
    """校验并解析 JWT，返回 payload；失败返回 None。"""
    try:
        payload = jwt.decode(token, settings.PYTHON_JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("JWT 已过期")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning("JWT 无效: %s", e)
        return None
