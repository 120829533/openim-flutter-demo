"""会话相关接口：免打扰、置顶、删除、草稿、一键已读、会话列表。"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.database import execute, fetch, fetchone
from app.redis_client import get_redis, key_conv_list, key_unread
from app.schemas.common import error, success
from app.utils.deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


# ===== 请求模型 =====

class MuteReq(BaseModel):
    mute: int = Field(..., description="0 关闭免打扰 1 开启免打扰")


class PinReq(BaseModel):
    pin: int = Field(..., description="0 取消置顶 1 置顶")


class DraftReq(BaseModel):
    content: str = Field(default="", description="草稿内容")


# ===== 接口 =====

@router.put("/{conversation_id}/mute")
async def set_mute(conversation_id: str, req: MuteReq, current_user: dict = Depends(get_current_user)):
    """设置会话免打扰。"""
    if req.mute not in (0, 1):
        return error(code=400, msg="mute 取值只能为 0 或 1")
    affected = await execute(
        """
        UPDATE conversation_members
        SET mute_notification = %s, updated_at = NOW()
        WHERE conversation_id = %s AND user_id = %s AND is_deleted = 0
        """,
        (req.mute, conversation_id, current_user["user_id"]),
    )
    if affected == 0:
        return error(code=404, msg="会话成员不存在")
    return success(msg="设置成功")


@router.put("/{conversation_id}/pin")
async def set_pin(conversation_id: str, req: PinReq, current_user: dict = Depends(get_current_user)):
    """置顶/取消置顶会话。"""
    if req.pin not in (0, 1):
        return error(code=400, msg="pin 取值只能为 0 或 1")
    affected = await execute(
        """
        UPDATE conversation_members
        SET is_pinned = %s, updated_at = NOW()
        WHERE conversation_id = %s AND user_id = %s AND is_deleted = 0
        """,
        (req.pin, conversation_id, current_user["user_id"]),
    )
    if affected == 0:
        return error(code=404, msg="会话成员不存在")
    return success(msg="设置成功")


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: str, current_user: dict = Depends(get_current_user)):
    """标记删除会话（is_deleted=1）。"""
    affected = await execute(
        """
        UPDATE conversation_members
        SET is_deleted = 1, updated_at = NOW()
        WHERE conversation_id = %s AND user_id = %s
        """,
        (conversation_id, current_user["user_id"]),
    )
    if affected == 0:
        return error(code=404, msg="会话成员不存在")
    return success(msg="会话已删除")


@router.put("/{conversation_id}/draft")
async def save_draft(conversation_id: str, req: DraftReq, current_user: dict = Depends(get_current_user)):
    """保存草稿到 drafts 表（不存在则插入，存在则更新）。"""
    user_id = current_user["user_id"]
    existing = await fetchone(
        "SELECT id FROM drafts WHERE user_id = %s AND conversation_id = %s",
        (user_id, conversation_id),
    )
    if existing:
        await execute(
            "UPDATE drafts SET content = %s, updated_at = NOW() WHERE id = %s",
            (req.content, existing["id"]),
        )
    else:
        await execute(
            "INSERT INTO drafts (user_id, conversation_id, content, updated_at) VALUES (%s, %s, %s, NOW())",
            (user_id, conversation_id, req.content),
        )
    return success(msg="草稿已保存")


@router.get("/{conversation_id}/draft")
async def get_draft(conversation_id: str, current_user: dict = Depends(get_current_user)):
    """获取草稿。"""
    row = await fetchone(
        "SELECT content, updated_at FROM drafts WHERE user_id = %s AND conversation_id = %s",
        (current_user["user_id"], conversation_id),
    )
    return success(data={"content": row["content"] if row else "", "updated_at": _dt_to_str(row["updated_at"]) if row else None})


@router.post("/mark_all_read")
async def mark_all_read(current_user: dict = Depends(get_current_user)):
    """一键已读：遍历 Redis unread:{user_id} 清零所有 field。"""
    redis = get_redis()
    key = key_unread(current_user["user_id"])
    # 获取所有会话的未读 field
    fields = await redis.hkeys(key)
    if fields:
        # 将所有 field 的值置为 0
        pipe = redis.pipeline()
        for f in fields:
            pipe.hset(key, f, 0)
        await pipe.execute()
    return success(data={"cleared": len(fields)}, msg="已全部标记为已读")


@router.get("/list")
async def conversation_list(current_user: dict = Depends(get_current_user)):
    """返回会话列表：从 Redis conv_list:{user_id} 读取排序，合并 conversation_members 状态。"""
    user_id = current_user["user_id"]
    redis = get_redis()

    # 从 Redis 有序集合读取会话列表（按 score=last_msg_time 倒序）
    # ZREVRANGE 返回 member 列表
    conv_ids = await redis.zrevrange(key_conv_list(user_id), 0, -1)

    if not conv_ids:
        return success(data=[])

    # 查询数据库中这些会话的成员状态
    placeholders = ",".join(["%s"] * len(conv_ids))
    members = await fetch(
        f"""
        SELECT cm.conversation_id, cm.is_pinned, cm.mute_notification,
               cm.unread_base, cm.cleared_at, cm.is_deleted, cm.joined_at,
               c.type AS conversation_type, c.last_message_id, c.last_message_time
        FROM conversation_members cm
        LEFT JOIN conversations c ON c.conversation_id = cm.conversation_id
        WHERE cm.user_id = %s AND cm.conversation_id IN ({placeholders})
        """,
        (user_id, *conv_ids),
    )
    member_map = {m["conversation_id"]: m for m in members}

    # 读取未读计数
    unread_map = await redis.hgetall(key_unread(user_id))

    # 组装结果，按 Redis 中的顺序输出
    result = []
    for cid in conv_ids:
        m = member_map.get(cid)
        if not m or m.get("is_deleted") == 1:
            # 已删除的会话不在列表中展示
            continue
        result.append({
            "conversation_id": cid,
            "type": m.get("conversation_type"),
            "is_pinned": m.get("is_pinned"),
            "mute_notification": m.get("mute_notification"),
            "unread": int(unread_map.get(cid, 0)),
            "unread_base": m.get("unread_base"),
            "last_message_id": m.get("last_message_id"),
            "last_message_time": _dt_to_str(m.get("last_message_time")),
            "joined_at": _dt_to_str(m.get("joined_at")),
        })
    return success(data=result)


# ===== 工具函数 =====

def _dt_to_str(val) -> Optional[str]:
    """datetime 转字符串。"""
    if val is None:
        return None
    return val.strftime("%Y-%m-%d %H:%M:%S") if hasattr(val, "strftime") else str(val)
