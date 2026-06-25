"""OpenIM Chat API 兼容层。

Flutter 客户端的 Apis 类调用 OpenIM Chat Server 的接口（/account/*, /user/* 等），
本模块将这些接口适配到我们的后端逻辑，使 Flutter 客户端无需修改即可对接。

关键差异处理：
- 响应格式：OpenIM 用 {errCode, errMsg, errDlt, data}，本兼容层统一返回此格式
- 密码：Flutter 端发送 MD5(password)，服务端对该 MD5 字符串再做 bcrypt 哈希存储
- 登录返回：{userID, imToken, chatToken}，imToken/chatToken 均为我们的 JWT
- 鉴权：Flutter 端通过 token 请求头传递 chatToken
"""
import logging
import uuid
from typing import Optional

import httpx
from fastapi import APIRouter, File, Header, UploadFile
from pydantic import BaseModel

from app.config import settings
from app.database import execute, execute_returning, fetchall, fetchone
from app.redis_client import get_redis, key_token, key_vcode
from app.utils.security import create_access_token, decode_access_token, hash_password, verify_password

logger = logging.getLogger(__name__)
router = APIRouter()


# ===== OpenIM 响应格式工具函数 =====

def _ok(data=None):
    """OpenIM 成功响应。"""
    return {"errCode": 0, "errMsg": "", "errDlt": "", "data": data}


def _err(code: int, msg: str):
    """OpenIM 错误响应。"""
    return {"errCode": code, "errMsg": msg, "errDlt": msg, "data": None}


# ===== 兼容层鉴权：解析 token 请求头 =====

async def _get_user_id_from_token(token: Optional[str] = Header(default=None)) -> Optional[str]:
    """从 token 请求头解析 JWT，返回 user_id；失败返回 None。"""
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload or "user_id" not in payload:
        return None
    return payload["user_id"]


# ===== 用户信息格式转换 =====

def _user_to_openim(u: dict) -> dict:
    """将数据库用户记录转为 OpenIM UserFullInfo 格式。"""
    return {
        "userID": u.get("user_id", ""),
        "account": u.get("account", ""),
        "phoneNumber": u.get("phone", ""),
        "email": u.get("email", ""),
        "nickname": u.get("nickname", ""),
        "faceURL": u.get("avatar", ""),
        "gender": u.get("gender", 0),
        "birth": _date_to_timestamp(u.get("birthday")),
        "level": 0,
        "allowAddFriend": 1,
        "allowBeep": 1,
        "allowVibration": 1,
        "globalRecvMsgOpt": 0,
        "status": u.get("status", 1),
        "isFriendship": False,
        "isBlacklist": False,
    }


def _date_to_timestamp(d) -> int:
    """将日期转为时间戳（秒），失败返回 0。"""
    if not d:
        return 0
    try:
        import datetime
        if isinstance(d, str):
            d = datetime.datetime.fromisoformat(d)
        if hasattr(d, "timestamp"):
            return int(d.timestamp())
    except Exception:
        pass
    return 0


def _make_cert(user_id: str, account: str) -> dict:
    """生成登录凭证 {userID, imToken, chatToken}。"""
    token = create_access_token(user_id, account)
    return {"userID": user_id, "imToken": token, "chatToken": token}


# ===== 账号接口 /account/* =====

@router.post("/account/code/send")
async def code_send(req: dict):
    """发送验证码。Flutter 端调用 Urls.getVerificationCode。"""
    phone = (req.get("phoneNumber") or "").strip()
    email = (req.get("email") or "").strip()
    target = phone or email
    if not target:
        return _err(10001, "手机号或邮箱不能为空")

    redis = get_redis()
    if settings.SMS_DEV_MODE:
        code = settings.SMS_DEV_CODE
        logger.info("[开发模式] 验证码 target=%s code=%s", target, code)
    else:
        import secrets
        code = str(secrets.randbelow(10 ** settings.SMS_CODE_LENGTH)).zfill(settings.SMS_CODE_LENGTH)
    await redis.set(key_vcode(target), code, ex=settings.SMS_CODE_TTL_SECONDS)
    return _ok({})


@router.post("/account/code/verify")
async def code_verify(req: dict):
    """校验验证码。"""
    phone = (req.get("phoneNumber") or "").strip()
    email = (req.get("email") or "").strip()
    target = phone or email
    code = req.get("verifyCode") or ""
    redis = get_redis()
    stored = await redis.get(key_vcode(target))
    if not stored or stored != code:
        return _err(30001, "验证码错误")
    return _ok({})


@router.post("/account/register")
async def account_register(req: dict):
    """注册。Flutter 端调用 Urls.register。"""
    user_data = req.get("user") or req
    phone = (user_data.get("phoneNumber") or "").strip()
    email = (user_data.get("email") or "").strip()
    account = (user_data.get("account") or "").strip()
    nickname = (user_data.get("nickname") or "").strip()
    password = user_data.get("password") or ""  # Flutter 端已 MD5
    code = req.get("verifyCode") or ""
    target = phone or email

    if not target and not account:
        return _err(10001, "账号不能为空")
    if not password:
        return _err(10001, "密码不能为空")

    # 校验验证码
    redis = get_redis()
    stored = await redis.get(key_vcode(target))
    if not stored or stored != code:
        return _err(30001, "验证码错误或已过期")

    # 检查是否已注册
    conditions = []
    params = []
    if phone:
        conditions.append("phone = %s")
        params.append(phone)
    if email:
        conditions.append("email = %s")
        params.append(email)
    if account:
        conditions.append("account = %s")
        params.append(account)
    if not conditions:
        conditions.append("phone = %s")
        params.append(phone or "")

    existing = await fetchone(
        f"SELECT id FROM users WHERE {' OR '.join(conditions)}",
        tuple(params),
    )
    if existing:
        return _err(20001, "账号已注册")

    user_id = uuid.uuid4().hex
    final_account = account or phone or email
    password_hash = hash_password(password)  # 对 MD5 字符串做 bcrypt
    nickname = nickname or final_account

    await execute_returning(
        """INSERT INTO users
           (user_id, account, password_hash, phone, email, avatar, nickname,
            gender, birthday, language, status, last_login_at, created_at, updated_at)
           VALUES (%s, %s, %s, %s, %s, '', %s, %s, NULL, 'zh-CN', 1, NULL, NOW(), NOW())""",
        (user_id, final_account, password_hash, phone, email, nickname, user_data.get("gender", 0)),
    )
    await execute_returning(
        """INSERT INTO user_settings
           (user_id, font_size, notification_sound, vibration, dnd_start, dnd_end,
            background_image, created_at, updated_at)
           VALUES (%s, 2, 1, 1, NULL, NULL, '', NOW(), NOW())""",
        (user_id,),
    )
    await redis.delete(key_vcode(target))

    logger.info("注册成功 user_id=%s", user_id)
    return _ok(_make_cert(user_id, final_account))


@router.post("/account/login")
async def account_login(req: dict):
    """登录。Flutter 端调用 Urls.login。"""
    account = (req.get("account") or "").strip()
    phone = (req.get("phoneNumber") or "").strip()
    email = (req.get("email") or "").strip()
    password = req.get("password") or ""  # Flutter 端已 MD5
    code = req.get("verifyCode") or ""
    identifier = account or phone or email

    if not identifier:
        return _err(10001, "账号不能为空")

    user = await fetchone(
        "SELECT * FROM users WHERE account = %s OR phone = %s OR email = %s LIMIT 1",
        (identifier, identifier, identifier),
    )
    if not user:
        return _err(40001, "账号未注册")

    # 密码登录
    if password:
        if not verify_password(password, user.get("password_hash", "")):
            return _err(40002, "密码错误")
    # 验证码登录
    elif code:
        redis = get_redis()
        stored = await redis.get(key_vcode(identifier))
        if not stored or stored != code:
            return _err(30001, "验证码错误")
    else:
        return _err(10001, "请输入密码或验证码")

    if user.get("status") == 0:
        return _err(40004, "账号已被禁用")

    user_id = user["user_id"]
    token = create_access_token(user_id, user.get("account") or identifier)
    await execute("UPDATE users SET last_login_at = NOW(), updated_at = NOW() WHERE user_id = %s", (user_id,))
    redis = get_redis()
    await redis.set(key_token(token), user_id, ex=settings.PYTHON_JWT_EXPIRE_HOURS * 3600)

    logger.info("登录成功 user_id=%s", user_id)
    return _ok(_make_cert(user_id, user.get("account") or identifier))


@router.post("/account/password/reset")
async def password_reset(req: dict):
    """重置密码。"""
    phone = (req.get("phoneNumber") or "").strip()
    email = (req.get("email") or "").strip()
    password = req.get("password") or ""  # MD5
    code = req.get("verifyCode") or ""
    target = phone or email

    if not target:
        return _err(10001, "手机号或邮箱不能为空")

    redis = get_redis()
    stored = await redis.get(key_vcode(target))
    if not stored or stored != code:
        return _err(30001, "验证码错误")

    user = await fetchone("SELECT id FROM users WHERE phone = %s OR email = %s", (phone, email))
    if not user:
        return _err(40001, "账号未注册")

    password_hash = hash_password(password)
    await execute("UPDATE users SET password_hash = %s, updated_at = NOW() WHERE phone = %s OR email = %s",
                  (password_hash, phone, email))
    await redis.delete(key_vcode(target))
    return _ok({})


@router.post("/account/password/change")
async def password_change(req: dict):
    """修改密码。"""
    user_id = req.get("userID") or ""
    current = req.get("currentPassword") or ""  # MD5
    new_pwd = req.get("newPassword") or ""  # MD5

    if not user_id or not current or not new_pwd:
        return _err(10001, "参数不完整")

    user = await fetchone("SELECT * FROM users WHERE user_id = %s", (user_id,))
    if not user:
        return _err(40001, "用户不存在")

    if not verify_password(current, user.get("password_hash", "")):
        return _err(40002, "原密码错误")

    password_hash = hash_password(new_pwd)
    await execute("UPDATE users SET password_hash = %s, updated_at = NOW() WHERE user_id = %s",
                  (password_hash, user_id))
    return _ok({})


# ===== 用户接口 /user/* =====

@router.post("/user/update")
async def user_update(req: dict):
    """更新用户信息。Flutter 端调用 Urls.updateUserInfo。"""
    user_id = req.get("userID") or ""
    if not user_id:
        return _err(10001, "userID 不能为空")

    fields = []
    params = []
    mapping = {
        "account": "account",
        "phoneNumber": "phone",
        "email": "email",
        "nickname": "nickname",
        "faceURL": "avatar",
        "gender": "gender",
    }
    for k, v in mapping.items():
        if k in req and req[k] is not None:
            fields.append(f"{v} = %s")
            params.append(req[k])
    # birth 是时间戳，转为日期
    if "birth" in req and req["birth"] is not None:
        fields.append("birthday = FROM_UNIXTIME(%s)")
        params.append(int(req["birth"]))

    if not fields:
        return _ok({})

    fields.append("updated_at = NOW()")
    params.append(user_id)
    await execute(f"UPDATE users SET {', '.join(fields)} WHERE user_id = %s", tuple(params))
    return _ok({})


@router.post("/user/find/full")
async def user_find_full(req: dict):
    """批量查询用户完整信息。Flutter 端调用 Urls.getUsersFullInfo。"""
    user_ids = req.get("userIDs") or []
    if not user_ids:
        return _ok({"users": []})

    placeholders = ",".join(["%s"] * len(user_ids))
    rows = await fetchall(
        f"SELECT * FROM users WHERE user_id IN ({placeholders})",
        tuple(user_ids),
    )
    users = [_user_to_openim(u) for u in rows]
    return _ok({"users": users})


@router.post("/user/search/full")
async def user_search_full(req: dict):
    """搜索用户。Flutter 端调用 Urls.searchUserFullInfo。"""
    keyword = (req.get("keyword") or "").strip()
    if not keyword:
        return _ok({"users": []})

    rows = await fetchall(
        "SELECT * FROM users WHERE account LIKE %s OR phone LIKE %s OR nickname LIKE %s LIMIT 20",
        (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"),
    )
    users = [_user_to_openim(u) for u in rows]
    return _ok({"users": users})


@router.post("/user/rtc/get_token")
async def rtc_get_token(req: dict):
    """获取 RTC token（桩实现，音视频通话需要独立的 LiveKit 服务）。"""
    return _ok({"token": "", "roomID": req.get("room", ""), "identity": req.get("identity", "")})


# ===== 好友接口 /friend/* =====

@router.post("/friend/search")
async def friend_search(req: dict):
    """搜索好友。Flutter 端调用 Urls.searchFriendInfo。"""
    keyword = (req.get("keyword") or "").strip()
    if not keyword:
        return _ok({"users": []})

    rows = await fetchall(
        "SELECT * FROM users WHERE account LIKE %s OR phone LIKE %s OR nickname LIKE %s LIMIT 20",
        (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"),
    )
    users = [_user_to_openim(u) for u in rows]
    return _ok({"users": users})


# ===== 管理接口 /manager/* =====

@router.post("/manager/get_users_online_status")
async def online_status(req: dict):
    """查询用户在线状态（从 Redis 读取）。"""
    user_ids = req.get("userIDs") or []
    redis = get_redis()
    result = []
    for uid in user_ids:
        online = await redis.exists(f"online:{uid}")
        result.append({"userID": uid, "status": "online" if online else "offline"})
    return _ok(result)


@router.post("/manager/get_all_users_uid")
async def all_users_uid():
    """获取所有用户 ID。"""
    rows = await fetchall("SELECT user_id FROM users")
    return _ok({"userIDs": [r["user_id"] for r in rows], "total": len(rows)})


# ===== 文件上传 /third/minio_upload =====

@router.post("/third/minio_upload")
async def minio_upload(
    file: UploadFile = File(...),
    token: Optional[str] = Header(default=None),
):
    """文件上传：代理到文件服务。Flutter 端调用 HttpUtil.uploadImageForMinio。

    返回格式：{errCode:0, data: {URL: "..."}}（Flutter 端读取 data.URL）
    """
    file_type = 1  # 1=图片 2=视频 3=文件，Flutter 端默认传 1
    content = await file.read()
    files = {"file": (file.filename or "upload", content, file.content_type or "application/octet-stream")}

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            if file_type == 1:
                # 图片走图片上传接口
                resp = await client.post(
                    f"{settings.FILE_SERVICE_URL}/api/file/image/upload",
                    files=files,
                )
                data = resp.json()
                if data.get("code") == 0:
                    url = data.get("data", {}).get("original_url", "")
                    return _ok({"URL": url})
                return _err(-1, data.get("msg", "上传失败"))
            else:
                resp = await client.post(
                    f"{settings.FILE_SERVICE_URL}/api/file/file/upload",
                    files=files,
                )
                data = resp.json()
                if data.get("code") == 0:
                    url = data.get("data", {}).get("url", "")
                    return _ok({"URL": url})
                return _err(-1, data.get("msg", "上传失败"))
    except Exception as e:
        logger.error("文件上传代理失败: %s", e)
        return _err(-1, f"文件上传失败: {e}")


# ===== 版本检测 /app/check =====

@router.post("/app/check")
async def app_check(req: dict):
    """客户端版本检测。"""
    platform = req.get("platform") or "android"
    row = await fetchone(
        "SELECT * FROM app_versions WHERE platform = %s ORDER BY version_code DESC LIMIT 1",
        (platform,),
    )
    if not row:
        return _ok(None)
    return _ok({
        "version": row.get("version", ""),
        "versionCode": row.get("version_code", 0),
        "downloadURL": row.get("download_url", ""),
        "updateLog": row.get("update_log", ""),
        "forceUpdate": bool(row.get("is_force", 0)),
    })


# ===== 客户端配置 /client_config/get =====

@router.get("/client_config/get")
async def client_config():
    """获取客户端配置。"""
    return _ok({
        "discoverPageURL": settings.DISCOVER_PAGE_URL,
        "allowSendMsgNotFriend": settings.ALLOW_SEND_MSG_NOT_FRIEND,
    })


# ===== 同步辅助端点（Flutter SDK 登录后自动调用，返回空数据即可） =====

@router.post("/user/get_users_info")
async def get_users_info(req: dict):
    """批量获取用户信息（同步用）。"""
    user_ids = req.get("userIDs") or []
    if not user_ids:
        return _ok({"users": []})
    return await user_find_full(req)


@router.post("/friend/get_incremental_friends")
async def get_incremental_friends(req: dict):
    """增量同步好友列表（桩实现）。"""
    return _ok({"friends": [], "version": "0"})


@router.post("/group/get_incremental_join_groups")
async def get_incremental_groups(req: dict):
    """增量同步群组列表（桩实现）。"""
    return _ok({"groups": [], "version": "0"})


@router.post("/conversation/get_incremental_conversations")
async def get_incremental_conversations(req: dict):
    """增量同步会话列表（桩实现）。"""
    return _ok({"conversations": [], "version": "0"})


@router.post("/group/get_recv_group_applicationList")
async def get_group_application_list(req: dict):
    """获取群组申请列表（桩实现）。"""
    return _ok({"applications": [], "total": 0})


@router.post("/friend/get_friend_apply_list")
async def get_friend_apply_list(req: dict):
    """获取好友申请列表（桩实现）。"""
    return _ok({"applications": [], "total": 0})


@router.post("/third/set_app_badge")
async def set_app_badge(req: dict):
    """设置 App 角标（桩实现）。"""
    return _ok({})


@router.post("/friend/get_black_list")
async def get_black_list(req: dict):
    """获取黑名单列表（桩实现）。"""
    return _ok({"blacks": [], "total": 0})
