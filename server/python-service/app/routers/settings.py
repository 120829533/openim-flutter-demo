"""用户设置接口：通用设置、聊天背景。"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.database import execute, fetchone
from app.schemas.common import error, success
from app.utils.deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


# ===== 请求模型 =====

class UpdateSettingsReq(BaseModel):
    font_size: Optional[int] = Field(default=None, description="字号 0/1/2")
    notification_sound: Optional[int] = Field(default=None, description="提示音 0关 1开")
    vibration: Optional[int] = Field(default=None, description="振动 0关 1开")
    dnd_start: Optional[str] = Field(default=None, description="免打扰开始 HH:MM")
    dnd_end: Optional[str] = Field(default=None, description="免打扰结束 HH:MM")


class BackgroundReq(BaseModel):
    image_url: str = Field(..., description="背景图 URL（前端先上传到文件服务）")


# ===== 接口 =====

@router.get("/")
async def get_settings(current_user: dict = Depends(get_current_user)):
    """返回当前用户的 user_settings。"""
    row = await fetchone(
        "SELECT * FROM user_settings WHERE user_id = %s",
        (current_user["user_id"],),
    )
    if not row:
        # 不存在则创建默认记录
        await execute(
            """
            INSERT INTO user_settings
                (user_id, font_size, notification_sound, vibration,
                 dnd_start, dnd_end, background_image, created_at, updated_at)
            VALUES (%s, 0, 1, 1, NULL, NULL, NULL, NOW(), NOW())
            """,
            (current_user["user_id"],),
        )
        row = await fetchone(
            "SELECT * FROM user_settings WHERE user_id = %s",
            (current_user["user_id"],),
        )
    return success(data=_format_settings(row))


@router.put("/")
async def update_settings(req: UpdateSettingsReq, current_user: dict = Depends(get_current_user)):
    """修改 font_size/notification_sound/vibration/dnd_start/dnd_end。"""
    user_id = current_user["user_id"]
    fields = []
    args = []
    for col, val in [
        ("font_size", req.font_size),
        ("notification_sound", req.notification_sound),
        ("vibration", req.vibration),
        ("dnd_start", req.dnd_start),
        ("dnd_end", req.dnd_end),
    ]:
        if val is not None:
            fields.append(f"{col} = %s")
            args.append(val)

    if not fields:
        return error(code=400, msg="没有需要更新的字段")

    # 确保记录存在
    existing = await fetchone("SELECT id FROM user_settings WHERE user_id = %s", (user_id,))
    if not existing:
        await execute(
            """
            INSERT INTO user_settings
                (user_id, font_size, notification_sound, vibration,
                 dnd_start, dnd_end, background_image, created_at, updated_at)
            VALUES (%s, 0, 1, 1, NULL, NULL, NULL, NOW(), NOW())
            """,
            (user_id,),
        )

    fields.append("updated_at = NOW()")
    args.append(user_id)
    await execute(f"UPDATE user_settings SET {', '.join(fields)} WHERE user_id = %s", tuple(args))
    return success(msg="设置已更新")


@router.put("/background")
async def update_background(req: BackgroundReq, current_user: dict = Depends(get_current_user)):
    """设置聊天背景（背景图由前端先上传到文件服务，这里只存 URL）。"""
    user_id = current_user["user_id"]
    existing = await fetchone("SELECT id FROM user_settings WHERE user_id = %s", (user_id,))
    if not existing:
        await execute(
            """
            INSERT INTO user_settings
                (user_id, font_size, notification_sound, vibration,
                 dnd_start, dnd_end, background_image, created_at, updated_at)
            VALUES (%s, 0, 1, 1, NULL, NULL, %s, NOW(), NOW())
            """,
            (user_id, req.image_url),
        )
    else:
        await execute(
            "UPDATE user_settings SET background_image = %s, updated_at = NOW() WHERE user_id = %s",
            (req.image_url, user_id),
        )
    return success(msg="背景设置成功")


# ===== 工具函数 =====

def _format_settings(row: Optional[dict]) -> dict:
    """格式化设置记录。"""
    if not row:
        return {}
    return {
        "font_size": row.get("font_size"),
        "notification_sound": row.get("notification_sound"),
        "vibration": row.get("vibration"),
        "dnd_start": row.get("dnd_start"),
        "dnd_end": row.get("dnd_end"),
        "background_image": row.get("background_image"),
        "updated_at": _dt_to_str(row.get("updated_at")),
    }


def _dt_to_str(val) -> Optional[str]:
    """datetime 转字符串。"""
    if val is None:
        return None
    return val.strftime("%Y-%m-%d %H:%M:%S") if hasattr(val, "strftime") else str(val)
