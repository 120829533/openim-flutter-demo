"""文件上传/下载路由。

统一前缀 /api/file，统一响应格式 {code, msg, data}。
- code=0 表示成功，非 0 表示失败
"""
from __future__ import annotations

import os
import uuid
from typing import Any, Dict

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import StreamingResponse

from ..config import settings
from ..minio_client import storage_client
from ..utils.image import (
    compress_avatar,
    compress_background,
    compress_chat_image,
    guess_image_content_type,
)

router = APIRouter(prefix="/api/file", tags=["file"])

# 允许的图片扩展名
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}


def _success(data: Any = None, msg: str = "ok") -> Dict[str, Any]:
    """构造成功响应。"""
    return {"code": 0, "msg": msg, "data": data}


def _error(msg: str, code: int = -1) -> Dict[str, Any]:
    """构造失败响应。"""
    return {"code": code, "msg": msg, "data": None}


def _gen_object_name(original_name: str) -> str:
    """生成对象名：UUID + 原文件名后缀，避免冲突。"""
    ext = os.path.splitext(original_name)[1].lower()
    return f"{uuid.uuid4().hex}{ext}"


def _check_image_ext(filename: str) -> bool:
    """校验图片扩展名。"""
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_IMAGE_EXT


def _build_download_url(bucket: str, object_name: str) -> str:
    """构造对外可访问的下载链接（走本服务代理下载）。"""
    base = settings.PUBLIC_BASE_URL.rstrip("/") if settings.PUBLIC_BASE_URL else ""
    return f"{base}/api/file/download?bucket={bucket}&object_name={object_name}"


@router.post("/image/upload")
async def upload_image(file: UploadFile = File(...)):
    """上传聊天图片。

    使用 Pillow 压缩生成缩略图（原图 max 1280px，缩略图 max 256px），
    原图与缩略图分别上传到 openim-chat-image bucket。
    返回 {original_url, thumbnail_url}。
    """
    if not file.filename or not _check_image_ext(file.filename):
        return _error("不支持的图片格式")

    raw = await file.read()
    if not raw:
        return _error("文件为空")

    # 校验大小
    if len(raw) > settings.file_max_size_bytes:
        return _error(f"文件超过最大限制 {settings.FILE_MAX_SIZE_MB}MB")

    try:
        original_bytes, thumbnail_bytes = compress_chat_image(raw)
    except Exception as e:  # noqa: BLE001
        return _error(f"图片处理失败: {e}")

    content_type = guess_image_content_type()
    bucket = "openim-chat-image"

    # 原图对象名
    original_object = _gen_object_name(file.filename)
    # 缩略图对象名加 _thumb 前缀
    name_part, ext = os.path.splitext(original_object)
    thumbnail_object = f"{name_part}_thumb{ext}"

    try:
        storage_client.upload(
            bucket=bucket,
            object_name=original_object,
            data=original_bytes,
            length=len(original_bytes),
            content_type=content_type,
        )
        storage_client.upload(
            bucket=bucket,
            object_name=thumbnail_object,
            data=thumbnail_bytes,
            length=len(thumbnail_bytes),
            content_type=content_type,
        )
    except Exception as e:  # noqa: BLE001
        return _error(f"图片上传失败: {e}")

    return _success(
        {
            "original_url": _build_download_url(bucket, original_object),
            "thumbnail_url": _build_download_url(bucket, thumbnail_object),
        }
    )


@router.post("/avatar/upload")
async def upload_avatar(file: UploadFile = File(...)):
    """上传用户头像。

    压缩为正方形（256x256），上传到 openim-avatar bucket。
    返回 {url}。
    """
    if not file.filename or not _check_image_ext(file.filename):
        return _error("不支持的图片格式")

    raw = await file.read()
    if not raw:
        return _error("文件为空")

    if len(raw) > settings.file_max_size_bytes:
        return _error(f"文件超过最大限制 {settings.FILE_MAX_SIZE_MB}MB")

    try:
        avatar_bytes = compress_avatar(raw)
    except Exception as e:  # noqa: BLE001
        return _error(f"头像处理失败: {e}")

    bucket = "openim-avatar"
    object_name = _gen_object_name(file.filename)
    content_type = guess_image_content_type()

    try:
        storage_client.upload(
            bucket=bucket,
            object_name=object_name,
            data=avatar_bytes,
            length=len(avatar_bytes),
            content_type=content_type,
        )
    except Exception as e:  # noqa: BLE001
        return _error(f"头像上传失败: {e}")

    return _success({"url": _build_download_url(bucket, object_name)})


@router.post("/background/upload")
async def upload_background(file: UploadFile = File(...)):
    """上传聊天背景图。

    上传到 openim-background bucket。
    返回 {url}。
    """
    if not file.filename or not _check_image_ext(file.filename):
        return _error("不支持的图片格式")

    raw = await file.read()
    if not raw:
        return _error("文件为空")

    if len(raw) > settings.file_max_size_bytes:
        return _error(f"文件超过最大限制 {settings.FILE_MAX_SIZE_MB}MB")

    try:
        bg_bytes = compress_background(raw)
    except Exception as e:  # noqa: BLE001
        return _error(f"背景图处理失败: {e}")

    bucket = "openim-background"
    object_name = _gen_object_name(file.filename)
    content_type = guess_image_content_type()

    try:
        storage_client.upload(
            bucket=bucket,
            object_name=object_name,
            data=bg_bytes,
            length=len(bg_bytes),
            content_type=content_type,
        )
    except Exception as e:  # noqa: BLE001
        return _error(f"背景图上传失败: {e}")

    return _success({"url": _build_download_url(bucket, object_name)})


@router.post("/file/upload")
async def upload_file(file: UploadFile = File(...)):
    """上传任意文件。

    校验大小（FILE_MAX_SIZE_MB），上传到 openim-file bucket。
    返回 {url, file_name, size}。
    """
    if not file.filename:
        return _error("文件名为空")

    raw = await file.read()
    if not raw:
        return _error("文件为空")

    if len(raw) > settings.file_max_size_bytes:
        return _error(f"文件超过最大限制 {settings.FILE_MAX_SIZE_MB}MB")

    bucket = "openim-file"
    object_name = _gen_object_name(file.filename)
    content_type = file.content_type or "application/octet-stream"

    try:
        storage_client.upload(
            bucket=bucket,
            object_name=object_name,
            data=raw,
            length=len(raw),
            content_type=content_type,
        )
    except Exception as e:  # noqa: BLE001
        return _error(f"文件上传失败: {e}")

    return _success(
        {
            "url": _build_download_url(bucket, object_name),
            "file_name": file.filename,
            "size": len(raw),
        }
    )


@router.post("/release/upload")
async def upload_release(file: UploadFile = File(...)):
    """上传客户端版本更新包。

    上传到 openim-release bucket。
    返回 {url}。
    """
    if not file.filename:
        return _error("文件名为空")

    raw = await file.read()
    if not raw:
        return _error("文件为空")

    # 版本包通常较大，不强制走 FILE_MAX_SIZE_MB，但仍做 2 倍上限保护
    hard_limit = settings.file_max_size_bytes * 2
    if len(raw) > hard_limit:
        return _error(f"文件超过最大限制 {settings.FILE_MAX_SIZE_MB * 2}MB")

    bucket = "openim-release"
    object_name = _gen_object_name(file.filename)
    content_type = file.content_type or "application/octet-stream"

    try:
        storage_client.upload(
            bucket=bucket,
            object_name=object_name,
            data=raw,
            length=len(raw),
            content_type=content_type,
        )
    except Exception as e:  # noqa: BLE001
        return _error(f"版本包上传失败: {e}")

    return _success({"url": _build_download_url(bucket, object_name)})


@router.get("/download")
async def download(
    bucket: str = Query(..., description="bucket 名称"),
    object_name: str = Query(..., description="对象名"),
):
    """代理 MinIO 下载，返回 StreamingResponse。"""
    try:
        # 获取对象元信息以拿到 content_type 和 size
        stat = storage_client.get_object_info(bucket, object_name)
    except Exception as e:  # noqa: BLE001
        return _error(f"对象不存在或获取信息失败: {e}")

    content_type = getattr(stat, "content_type", None) or "application/octet-stream"
    size = getattr(stat, "size", -1)

    headers = {}
    if size and size > 0:
        headers["Content-Length"] = str(size)
    # 使用 object_name 作为下载文件名
    headers["Content-Disposition"] = f'attachment; filename="{object_name}"'

    return StreamingResponse(
        storage_client.download(bucket, object_name),
        media_type=content_type,
        headers=headers,
    )


@router.get("/presigned")
async def presigned(
    bucket: str = Query(..., description="bucket 名称"),
    object_name: str = Query(..., description="对象名"),
    expires: int = Query(3600, description="过期时间（秒）"),
):
    """生成预签名下载 URL。"""
    try:
        url = storage_client.presigned_url(bucket, object_name, expires=expires)
    except Exception as e:  # noqa: BLE001
        return _error(f"生成预签名 URL 失败: {e}")

    return _success({"url": url, "expires": expires})
