"""客服系统 API（集成 OpenIM 消息系统）。

网页端访客通过此 API 发送消息，消息会通过 OpenIM 消息管道
推送到 APK 客服端。APK 客服端回复的消息也会通过 WebSocket
推送到网页端。

架构：
  网页访客 → CS API → Java Message Service → MySQL + Redis → WebSocket 推送
  APK 客服  → OpenIM SDK → Java Message Service → WebSocket 推送 → 网页访客

CS Agent 用户 ID 预设为 cs_agent_001（APK 客服端登录此账号）。
"""
import logging
import uuid
from typing import Optional

import httpx
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import settings
from app.database import execute, fetch, fetchone
from app.utils.security import create_access_token

logger = logging.getLogger(__name__)
router = APIRouter()

# 预设客服账号
CS_AGENT_USER_ID = "cs_agent_001"


# ===== 请求/响应模型 =====

class VisitorMsgReq(BaseModel):
    """网页端访客发送消息请求。"""
    message: str
    visitor_name: Optional[str] = None
    visitor_avatar: Optional[str] = None
    source_page: Optional[str] = None
    visitor_ip: Optional[str] = None


class VisitorMsgResp(BaseModel):
    """网页端访客发送消息响应。"""
    conversation_id: str       # OpenIM 会话 ID
    visitor_id: str            # OpenIM 用户 ID（访客）
    message_id: str            # 消息 ID
    cs_user_id: str            # 客服用户 ID
    token: str                 # JWT token（用于 WebSocket 连接）


class AgentReplyReq(BaseModel):
    """客服端回复消息请求。"""
    conversation_id: str
    content: str
    cs_user_id: str = CS_AGENT_USER_ID


# ===== CORS OPTIONS =====

@router.options("/{path:path}")
async def cors_options():
    return JSONResponse(
        content={},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        },
    )


# ===== 网页端访客 API =====

@router.post("/visitor/send")
async def visitor_send_message(req: VisitorMsgReq):
    """网页端访客发送消息。

    流程：
    1. 查找或创建 OpenIM 用户（访客）
    2. 查找或创建 OpenIM 会话（单聊：访客 ↔ 客服）
    3. 通过 Java 消息服务发送消息
    4. 返回会话信息 + JWT token（供 WebSocket 连接）
    """
    visitor_name = req.visitor_name or f"访客_{uuid.uuid4().hex[:6]}"

    # 1. 查找或创建访客 OpenIM 用户
    visitor_user_id = await _get_or_create_visitor_user(
        visitor_name=visitor_name,
        visitor_avatar=req.visitor_avatar or "",
        visitor_ip=req.visitor_ip,
        source_page=req.source_page,
    )

    # 2. 查找或创建 OpenIM 会话（单聊：visitor ↔ cs_agent）
    conversation_id = await _get_or_create_conversation(visitor_user_id, CS_AGENT_USER_ID)

    # 3. 通过 Java 消息服务发送消息
    message_id = await _send_via_java_service(
        conversation_id=conversation_id,
        sender_id=visitor_user_id,
        msg_type=1,
        content=req.message,
    )

    # 4. 更新 CS 会话映射表
    await _update_cs_conversation(visitor_user_id, conversation_id, req.message)

    # 5. 生成 JWT token（WebSocket 连接用）
    token = create_access_token(visitor_user_id, visitor_user_id)

    logger.info("访客消息已发送 visitor=%s openim_conv=%s message_id=%s",
                visitor_user_id, conversation_id, message_id)

    return {
        "errCode": 0,
        "errMsg": "",
        "data": {
            "conversation_id": conversation_id,
            "visitor_id": visitor_user_id,
            "message_id": message_id,
            "cs_user_id": CS_AGENT_USER_ID,
            "token": token,
        }
    }


@router.get("/visitor/history")
async def visitor_get_history(
    conversation_id: str = Query(...),
    limit: int = Query(default=50),
):
    """网页端访客获取历史消息。

    直接查询 OpenIM messages 表（按时间倒序后反转）。
    """
    raw_messages = await fetch(
        """SELECT message_id, content, msg_type, sender_id,
                  DATE_FORMAT(created_at, '%%Y-%%m-%%d %%H:%%i:%%s') AS created_at
           FROM messages
           WHERE conversation_id = %s AND status = 0
           ORDER BY seq ASC
           LIMIT %s""",
        (conversation_id, limit),
    )

    messages = []
    for m in raw_messages:
        messages.append({
            "message_id": m["message_id"],
            "content": m["content"],
            "msg_type": m["msg_type"],
            "direction": "visitor" if m["sender_id"] != CS_AGENT_USER_ID else "agent",
            "created_at": m["created_at"],
        })

    return {
        "errCode": 0,
        "errMsg": "",
        "data": {"messages": messages}
    }


@router.get("/visitor/token")
async def visitor_get_token(visitor_id: str = Query(...)):
    """为已创建的访客获取新的 WebSocket token。"""
    token = create_access_token(visitor_id, visitor_id)
    return {
        "errCode": 0,
        "errMsg": "",
        "data": {"token": token, "user_id": visitor_id}
    }


# ===== 客服端 API =====

@router.get("/agent/conversations")
async def cs_agent_conversations(
    cs_user_id: str = Query(default=CS_AGENT_USER_ID),
    limit: int = Query(default=100),
    offset: int = Query(default=0),
):
    """客服端获取会话列表。

    从 OpenIM conversation_members 表查询客服参与的所有会话，
    并关联 cs_visitors 获取访客信息。
    """
    conversations = await fetch(
        """SELECT cm.conversation_id, cm.joined_at,
                  v.visitor_name, v.visitor_avatar, v.source_page,
                  v.visitor_ip, v.first_seen, v.last_seen,
                  c.last_message_id, c.last_message_time,
                  c.type AS conv_type
           FROM conversation_members cm
           JOIN conversations c ON cm.conversation_id = c.conversation_id
           JOIN conversation_members cm2 ON cm.conversation_id = cm2.conversation_id
               AND cm2.user_id != cm.user_id
           LEFT JOIN cs_visitors v ON cm2.user_id = v.openim_user_id
           WHERE cm.user_id = %s AND cm.is_deleted = 0
           ORDER BY c.last_message_time DESC
           LIMIT %s OFFSET %s""",
        (cs_user_id, limit, offset),
    )

    result = []
    for conv in conversations:
        conv_id = conv["conversation_id"]
        # 统计未读消息数（通过 Redis unread hash 更好，这里简化查询）
        unread = await fetchone(
            """SELECT COUNT(*) AS cnt FROM messages
               WHERE conversation_id = %s AND sender_id != %s AND status = 0""",
            (conv_id, cs_user_id),
        )
        result.append({
            "conversation_id": conv_id,
            "visitor_name": conv.get("visitor_name") or "未知访客",
            "visitor_avatar": conv.get("visitor_avatar") or "",
            "source_page": conv.get("source_page") or "",
            "last_message_time": str(conv.get("last_message_time") or ""),
            "unread_count": unread["cnt"] if unread else 0,
            "joined_at": str(conv.get("joined_at") or ""),
        })

    return {
        "errCode": 0,
        "errMsg": "",
        "data": {"conversations": result, "total": len(result)}
    }


@router.get("/agent/messages")
async def cs_agent_messages(
    conversation_id: str = Query(...),
    limit: int = Query(default=100),
):
    """客服端获取指定会话的历史消息。"""
    raw_messages = await fetch(
        """SELECT message_id, content, msg_type, sender_id,
                  DATE_FORMAT(created_at, '%%Y-%%m-%%d %%H:%%i:%%s') AS created_at
           FROM messages
           WHERE conversation_id = %s AND status = 0
           ORDER BY seq ASC
           LIMIT %s""",
        (conversation_id, limit),
    )

    messages = []
    for m in raw_messages:
        messages.append({
            "message_id": m["message_id"],
            "content": m["content"],
            "msg_type": m["msg_type"],
            "direction": "visitor" if m["sender_id"] != CS_AGENT_USER_ID else "agent",
            "sender_id": m["sender_id"],
            "created_at": m["created_at"],
        })

    return {
        "errCode": 0,
        "errMsg": "",
        "data": {"messages": messages}
    }


@router.post("/agent/reply")
async def cs_agent_reply(req: AgentReplyReq):
    """客服端回复客户（通过 Java 消息服务发送）。"""
    # 从会话中获取访客 user_id
    member = await fetchone(
        """SELECT cm2.user_id AS visitor_id
           FROM conversation_members cm
           JOIN conversation_members cm2 ON cm.conversation_id = cm2.conversation_id
               AND cm2.user_id != cm.user_id
           WHERE cm.conversation_id = %s AND cm.user_id = %s""",
        (req.conversation_id, req.cs_user_id),
    )

    if not member:
        return {
            "errCode": 1,
            "errMsg": "会话不存在",
            "data": None
        }

    message_id = await _send_via_java_service(
        conversation_id=req.conversation_id,
        sender_id=req.cs_user_id,
        msg_type=1,
        content=req.content,
    )

    # 更新 CS 会话最后消息
    await execute(
        """INSERT INTO cs_conversations (conversation_id, openim_conv_id, visitor_id, cs_user_id,
            status, last_message, last_message_time, created_at, updated_at)
           VALUES (%s, %s, %s, %s, 'active', %s, NOW(), NOW(), NOW())
           ON DUPLICATE KEY UPDATE
            last_message = VALUES(last_message),
            last_message_time = VALUES(last_message_time),
            updated_at = VALUES(updated_at)""",
        (f"cs_{uuid.uuid4().hex[:16]}", req.conversation_id,
         member["visitor_id"], req.cs_user_id, req.content[:200]),
    )

    return {
        "errCode": 0,
        "errMsg": "",
        "data": {"message_id": message_id}
    }


@router.get("/visitor-names")
async def get_visitor_names():
    """获取所有访客的 user_id -> visitor_name 映射。

    Flutter 客服端加载会话列表时调用，用于显示访客名称。
    """
    rows = await fetch(
        """SELECT openim_user_id, visitor_name, visitor_avatar
           FROM cs_visitors"""
    )
    names = {}
    for r in rows:
        names[r["openim_user_id"]] = {
            "name": r["visitor_name"],
            "avatar": r["visitor_avatar"] or "",
        }
    return {
        "errCode": 0,
        "errMsg": "",
        "data": {"visitors": names}
    }


# ===== 内部工具函数 =====

async def _get_or_create_visitor_user(
    visitor_name: str,
    visitor_avatar: str,
    visitor_ip: Optional[str],
    source_page: Optional[str],
) -> str:
    """查找或创建访客的 OpenIM 用户和 CS 访客记录。

    返回 OpenIM user_id。
    """
    # 先按 IP 查找已有访客
    if visitor_ip:
        row = await fetchone(
            """SELECT v.openim_user_id, v.visitor_id
               FROM cs_visitors v
               WHERE v.visitor_ip = %s
               ORDER BY v.last_seen DESC LIMIT 1""",
            (visitor_ip,),
        )
        if row and row["openim_user_id"]:
            # 更新最近访问时间
            await execute(
                """UPDATE cs_visitors
                   SET last_seen = NOW(), visitor_name = %s, source_page = %s
                   WHERE visitor_id = %s""",
                (visitor_name, source_page, row["visitor_id"]),
            )
            return row["openim_user_id"]

    # 创建新的 OpenIM 用户
    openim_user_id = uuid.uuid4().hex
    await execute(
        """INSERT INTO users
           (user_id, account, password_hash, phone, email, avatar, nickname,
            gender, birthday, language, status, last_login_at, created_at, updated_at)
           VALUES (%s, %s, '', '', '', %s, %s, 0, NULL, 'zh-CN', 1, NOW(), NOW(), NOW())
           ON DUPLICATE KEY UPDATE updated_at = NOW()""",
        (openim_user_id, openim_user_id, visitor_avatar, visitor_name),
    )

    # 创建用户设置
    await execute(
        """INSERT IGNORE INTO user_settings
           (user_id, font_size, notification_sound, vibration, dnd_start, dnd_end,
            background_image, created_at, updated_at)
           VALUES (%s, 2, 1, 1, NULL, NULL, '', NOW(), NOW())""",
        (openim_user_id,),
    )

    # 创建 CS 访客记录
    visitor_id = f"v_{uuid.uuid4().hex[:12]}"
    await execute(
        """INSERT INTO cs_visitors
           (visitor_id, openim_user_id, visitor_name, visitor_avatar,
            visitor_ip, source_page, first_seen, last_seen)
           VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())""",
        (visitor_id, openim_user_id, visitor_name, visitor_avatar,
         visitor_ip, source_page),
    )

    logger.info("新访客已创建 visitor_id=%s openim_user_id=%s", visitor_id, openim_user_id)
    return openim_user_id


async def _get_or_create_conversation(visitor_user_id: str, cs_user_id: str) -> str:
    """查找或创建 OpenIM 单聊会话。

    使用固定格式的 conversation_id：si_{user1}_{user2}（排序后），
    确保同一对用户只有一个会话。
    """
    # 生成确定性会话 ID（两个用户 ID 排序后拼接）
    ids = sorted([visitor_user_id, cs_user_id])
    conversation_id = f"si_{ids[0]}_{ids[1]}"

    # 检查是否已存在
    existing = await fetchone(
        "SELECT conversation_id FROM conversations WHERE conversation_id = %s",
        (conversation_id,),
    )
    if existing:
        return conversation_id

    # 创建会话
    await execute(
        """INSERT INTO conversations
           (conversation_id, type, last_message_id, last_message_time, created_at, updated_at)
           VALUES (%s, 1, '', NOW(), NOW(), NOW())""",
        (conversation_id,),
    )

    # 添加双方为会话成员
    await execute(
        """INSERT INTO conversation_members
           (conversation_id, user_id, joined_at, updated_at)
           VALUES (%s, %s, NOW(), NOW())""",
        (conversation_id, visitor_user_id),
    )
    await execute(
        """INSERT INTO conversation_members
           (conversation_id, user_id, joined_at, updated_at)
           VALUES (%s, %s, NOW(), NOW())""",
        (conversation_id, cs_user_id),
    )

    logger.info("OpenIM 会话已创建 conversation_id=%s", conversation_id)
    return conversation_id


async def _send_via_java_service(
    conversation_id: str,
    sender_id: str,
    msg_type: int,
    content: str,
) -> str:
    """通过 Java 消息服务发送消息。

    调用 Java 服务的 REST API，让消息经过完整的消息管道
    （存 MySQL、写 Redis、WebSocket 推送、离线通知）。

    失败时降级为直接写入 messages 表。
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{settings.JAVA_SERVICE_URL}/api/message/send",
                json={
                    "conversationId": conversation_id,
                    "senderId": sender_id,
                    "msgType": msg_type,
                    "content": content,
                },
            )
            data = resp.json()
            if data.get("code") == 0 and data.get("data"):
                msg_id = data["data"].get("messageId") or data["data"].get("message_id")
                if msg_id:
                    return msg_id
            logger.warning("Java 消息服务返回异常: %s", data)
    except Exception as e:
        logger.warning("调用 Java 消息服务失败，降级为直接写库: %s", e)

    # 降级：直接写入 messages 表
    return await _fallback_send_message(conversation_id, sender_id, msg_type, content)


async def _fallback_send_message(
    conversation_id: str,
    sender_id: str,
    msg_type: int,
    content: str,
) -> str:
    """降级方案：直接写入 messages 表（不经过 Java 消息管道）。"""
    message_id = uuid.uuid4().hex

    # 获取当前最大 seq
    row = await fetchone(
        "SELECT COALESCE(MAX(seq), 0) AS max_seq FROM messages WHERE conversation_id = %s",
        (conversation_id,),
    )
    next_seq = (row["max_seq"] if row else 0) + 1

    await execute(
        """INSERT INTO messages
           (message_id, conversation_id, sender_id, msg_type, content,
            status, seq, created_at)
           VALUES (%s, %s, %s, %s, %s, 0, %s, NOW(3))""",
        (message_id, conversation_id, sender_id, msg_type, content, next_seq),
    )

    # 更新会话最后消息时间
    await execute(
        """UPDATE conversations
           SET last_message_id = %s, last_message_time = NOW(), updated_at = NOW()
           WHERE conversation_id = %s""",
        (message_id, conversation_id),
    )

    logger.info("消息已降级写入 message_id=%s", message_id)
    return message_id


async def _update_cs_conversation(
    visitor_user_id: str,
    conversation_id: str,
    message: str,
) -> None:
    """更新 CS 会话映射表。"""
    cs_conv_id = f"cs_{uuid.uuid4().hex[:16]}"
    await execute(
        """INSERT INTO cs_conversations
           (conversation_id, openim_conv_id, visitor_id, cs_user_id,
            status, last_message, last_message_time, created_at, updated_at)
           VALUES (%s, %s, %s, %s, 'active', %s, NOW(), NOW(), NOW())
           ON DUPLICATE KEY UPDATE
            last_message = VALUES(last_message),
            last_message_time = VALUES(last_message_time),
            updated_at = VALUES(updated_at)""",
        (cs_conv_id, conversation_id, visitor_user_id, CS_AGENT_USER_ID, message[:200]),
    )