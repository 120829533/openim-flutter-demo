"""用户相关接口：资料、密码、黑名单、语言偏好。"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.database import execute, fetch, fetchone
from app.redis_client import get_redis, key_vcode
from app.schemas.common import error, success
from app.utils.deps import get_current_user
from app.utils.security import hash_password, verify_password

logger = logging.getLogger(__name__)
router = APIRouter()


# ===== 请求模型 =====

class UpdateProfileReq(BaseModel):
    nickname: Optional[str] = None
    gender: Optional[int] = Field(default=None, description="性别 0未知 1男 2女")
    birthday: Optional[str] = Field(default=None, description="生日 YYYY-MM-DD")
    avatar: Optional[str] = None
    email: Optional[str] = None


class UpdatePasswordReq(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=6)


class ResetPasswordReq(BaseModel):
    phone: str
    code: str
    new_password: str = Field(..., min_length=6)


class UpdateLanguageReq(BaseModel):
    language: str = Field(..., description="语言代码，如 zh-CN")


# ===== 接口 =====

@router.get("/profile")
async def get_profile(current_user: dict = Depends(get_current_user)):
    """返回当前用户信息。"""
    return success(data=_format_user(current_user))


@router.put("/profile")
async def update_profile(req: UpdateProfileReq, current_user: dict = Depends(get_current_user)):
    """修改 nickname/gender/birthday/avatar/email。"""
    user_id = current_user["user_id"]
    fields = []
    args = []
    for col, val in [
        ("nickname", req.nickname),
        ("gender", req.gender),
        ("birthday", req.birthday),
        ("avatar", req.avatar),
        ("email", req.email),
    ]:
        if val is not None:
            fields.append(f"{col} = %s")
            args.append(val)

    if not fields:
        return error(code=400, msg="没有需要更新的字段")

    fields.append("updated_at = NOW()")
    args.append(user_id)
    await execute(f"UPDATE users SET {', '.join(fields)} WHERE user_id = %s", tuple(args))
    return success(msg="更新成功")


@router.put("/password")
async def update_password(req: UpdatePasswordReq, current_user: dict = Depends(get_current_user)):
    """修改密码：校验旧密码后更新。"""
    if not verify_password(req.old_password, current_user.get("password_hash", "")):
        return error(code=400, msg="旧密码错误")

    new_hash = hash_password(req.new_password)
    await execute(
        "UPDATE users SET password_hash = %s, updated_at = NOW() WHERE user_id = %s",
        (new_hash, current_user["user_id"]),
    )
    return success(msg="密码修改成功")


@router.post("/reset_password")
async def reset_password(req: ResetPasswordReq, current_user: dict = Depends(get_current_user)):
    """重置密码：通过手机号 + 验证码重置（需登录）。"""
    phone = req.phone.strip()
    if not phone:
        return error(code=400, msg="手机号不能为空")

    # 校验当前账号与手机号一致
    if current_user.get("phone") != phone:
        return error(code=403, msg="只能重置本人手机号的密码")

    # 校验验证码
    redis = get_redis()
    stored_code = await redis.get(key_vcode(phone))
    if not stored_code or stored_code != req.code:
        return error(code=400, msg="验证码错误或已过期")

    new_hash = hash_password(req.new_password)
    await execute(
        "UPDATE users SET password_hash = %s, updated_at = NOW() WHERE user_id = %s",
        (new_hash, current_user["user_id"]),
    )
    await redis.delete(key_vcode(phone))
    return success(msg="密码重置成功")


@router.get("/blacklist")
async def get_blacklist(current_user: dict = Depends(get_current_user)):
    """返回黑名单列表（join users 表）。"""
    rows = await fetch(
        """
        SELECT b.id, b.user_id, b.blocked_user_id, b.created_at,
               u.account, u.nickname, u.avatar, u.phone
        FROM blacklist b
        LEFT JOIN users u ON u.user_id = b.blocked_user_id
        WHERE b.user_id = %s
        ORDER BY b.created_at DESC
        """,
        (current_user["user_id"],),
    )
    return success(data=rows)


@router.post("/blacklist/{user_id}")
async def add_blacklist(user_id: str, current_user: dict = Depends(get_current_user)):
    """拉黑指定用户。"""
    if user_id == current_user["user_id"]:
        return error(code=400, msg="不能拉黑自己")

    # 校验被拉黑用户是否存在
    target = await fetchone("SELECT id FROM users WHERE user_id = %s", (user_id,))
    if not target:
        return error(code=404, msg="目标用户不存在")

    # 避免重复拉黑
    existing = await fetchone(
        "SELECT id FROM blacklist WHERE user_id = %s AND blocked_user_id = %s",
        (current_user["user_id"], user_id),
    )
    if existing:
        return error(code=400, msg="已拉黑该用户")

    await execute(
        "INSERT INTO blacklist (user_id, blocked_user_id, created_at) VALUES (%s, %s, NOW())",
        (current_user["user_id"], user_id),
    )
    return success(msg="拉黑成功")


@router.delete("/blacklist/{user_id}")
async def remove_blacklist(user_id: str, current_user: dict = Depends(get_current_user)):
    """移出黑名单。"""
    affected = await execute(
        "DELETE FROM blacklist WHERE user_id = %s AND blocked_user_id = %s",
        (current_user["user_id"], user_id),
    )
    if affected == 0:
        return error(code=404, msg="记录不存在")
    return success(msg="已移出黑名单")


@router.put("/language")
async def update_language(req: UpdateLanguageReq, current_user: dict = Depends(get_current_user)):
    """修改语言偏好。"""
    await execute(
        "UPDATE users SET language = %s, updated_at = NOW() WHERE user_id = %s",
        (req.language, current_user["user_id"]),
    )
    return success(msg="语言设置成功")


# ===== 工具函数 =====

def _format_user(user: dict) -> dict:
    """格式化用户信息，去除敏感字段。"""
    return {
        "user_id": user.get("user_id"),
        "account": user.get("account"),
        "phone": user.get("phone"),
        "email": user.get("email"),
        "avatar": user.get("avatar"),
        "nickname": user.get("nickname"),
        "gender": user.get("gender"),
        "birthday": user.get("birthday"),
        "language": user.get("language"),
        "status": user.get("status"),
        "last_login_at": _dt_to_str(user.get("last_login_at")),
        "created_at": _dt_to_str(user.get("created_at")),
    }


def _dt_to_str(val) -> Optional[str]:
    """datetime 转字符串。"""
    if val is None:
        return None
    return val.strftime("%Y-%m-%d %H:%M:%S") if hasattr(val, "strftime") else str(val)
