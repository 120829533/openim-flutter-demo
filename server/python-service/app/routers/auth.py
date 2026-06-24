"""认证相关接口：发送验证码、注册、登录、登出。"""
import logging
import secrets
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from app.config import settings
from app.database import execute, execute_returning, fetchone
from app.redis_client import get_redis, key_token, key_vcode
from app.schemas.common import error, success
from app.utils.deps import get_current_user
from app.utils.security import create_access_token, hash_password, verify_password

logger = logging.getLogger(__name__)
router = APIRouter()


# ===== 请求模型 =====

class SendCodeReq(BaseModel):
    phone: str = Field(..., description="手机号")


class RegisterReq(BaseModel):
    phone: str = Field(..., description="手机号")
    password: str = Field(..., min_length=6, description="密码")
    code: str = Field(..., description="验证码")
    nickname: str = Field(default="", description="昵称")


class LoginReq(BaseModel):
    account: str = Field(..., description="账号（手机号或用户名）")
    password: str = Field(..., description="密码")


# ===== 接口 =====

@router.post("/send_code")
async def send_code(req: SendCodeReq):
    """发送验证码。

    开发模式：固定返回 123456，并打印日志。
    生产模式：生成随机验证码存入 Redis。
    """
    phone = req.phone.strip()
    if not phone:
        return error(code=400, msg="手机号不能为空")

    redis = get_redis()
    if settings.SMS_DEV_MODE:
        code = settings.SMS_DEV_CODE
        logger.info("[开发模式] 验证码 phone=%s code=%s", phone, code)
    else:
        # 生成随机数字验证码
        max_num = 10 ** settings.SMS_CODE_LENGTH
        code = str(secrets.randbelow(max_num)).zfill(settings.SMS_CODE_LENGTH)

    # 存入 Redis，设置 TTL
    await redis.set(key_vcode(phone), code, ex=settings.SMS_CODE_TTL_SECONDS)

    return success(msg="验证码已发送")


@router.post("/register")
async def register(req: RegisterReq):
    """注册：校验验证码，创建用户，初始化 user_settings。"""
    phone = req.phone.strip()
    if not phone:
        return error(code=400, msg="手机号不能为空")

    # 校验验证码
    redis = get_redis()
    stored_code = await redis.get(key_vcode(phone))
    if not stored_code or stored_code != req.code:
        return error(code=400, msg="验证码错误或已过期")

    # 检查手机号是否已注册
    existing = await fetchone("SELECT id FROM users WHERE phone = %s", (phone,))
    if existing:
        return error(code=400, msg="该手机号已注册")

    # 生成 user_id 与 account
    user_id = uuid.uuid4().hex
    account = phone  # 默认账号为手机号
    password_hash = hash_password(req.password)
    nickname = req.nickname.strip() or phone

    # 创建用户
    await execute_returning(
        """
        INSERT INTO users
            (user_id, account, password_hash, phone, email, avatar, nickname,
             gender, birthday, language, status, last_login_at, created_at, updated_at)
        VALUES
            (%s, %s, %s, %s, NULL, NULL, %s,
             0, NULL, 'zh-CN', 1, NULL, NOW(), NOW())
        """,
        (user_id, account, password_hash, phone, nickname),
    )

    # 初始化 user_settings
    await execute_returning(
        """
        INSERT INTO user_settings
            (user_id, font_size, notification_sound, vibration,
             dnd_start, dnd_end, background_image, created_at, updated_at)
        VALUES
            (%s, 0, 1, 1, NULL, NULL, NULL, NOW(), NOW())
        """,
        (user_id,),
    )

    # 注册成功后删除验证码
    await redis.delete(key_vcode(phone))

    logger.info("用户注册成功 user_id=%s phone=%s", user_id, phone)
    return success(data={"user_id": user_id, "account": account}, msg="注册成功")


@router.post("/login")
async def login(req: LoginReq):
    """登录：校验密码，签发 JWT，更新 last_login_at，写入 Redis token。"""
    account = req.account.strip()
    if not account:
        return error(code=400, msg="账号不能为空")

    # 支持手机号或 account 登录
    user = await fetchone(
        "SELECT * FROM users WHERE account = %s OR phone = %s LIMIT 1",
        (account, account),
    )
    if not user:
        return error(code=400, msg="账号不存在")

    if not verify_password(req.password, user.get("password_hash", "")):
        return error(code=400, msg="密码错误")

    if user.get("status") == 2:
        return error(code=403, msg="账号已被禁用")

    user_id = user["user_id"]
    # 签发 JWT
    token = create_access_token(user_id, user.get("account") or account)

    # 更新最后登录时间
    await execute("UPDATE users SET last_login_at = NOW(), updated_at = NOW() WHERE user_id = %s", (user_id,))

    # 写入 Redis token（用于登出失效控制），TTL 与 JWT 一致
    redis = get_redis()
    await redis.set(key_token(token), user_id, ex=settings.PYTHON_JWT_EXPIRE_HOURS * 3600)

    logger.info("用户登录成功 user_id=%s", user_id)
    return success(
        data={
            "token": token,
            "user_id": user_id,
            "account": user.get("account"),
            "nickname": user.get("nickname"),
            "avatar": user.get("avatar"),
        },
        msg="登录成功",
    )


@router.post("/logout")
async def logout(
    current_user: dict = Depends(get_current_user),
    authorization: Optional[str] = Header(default=None),
):
    """登出：删除 Redis 中的 token，使当前登录态失效。"""
    redis = get_redis()
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if token:
            await redis.delete(key_token(token))
    logger.info("用户登出 user_id=%s", current_user.get("user_id"))
    return success(msg="已退出登录")
