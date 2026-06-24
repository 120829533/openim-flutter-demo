"""图片处理工具模块。

使用 Pillow 完成图片压缩、缩略图生成、头像裁剪等操作。
"""
from __future__ import annotations

import io
from typing import Tuple

from PIL import Image

from ..config import settings

# 缩略图最大边长（px）
THUMBNAIL_MAX_SIZE = 256
# 聊天原图最大边长（px）
IMAGE_MAX_SIZE = 1280
# 头像正方形边长（px）
AVATAR_SIZE = 256


def _open_image(data: bytes) -> Image.Image:
    """从字节流打开图片，统一转为 RGB。"""
    img = Image.open(io.BytesIO(data))
    # 处理 EXIF 旋转信息，保证方向正确
    try:
        from PIL import ImageOps

        img = ImageOps.exif_transpose(img)
    except Exception:  # noqa: BLE001
        pass
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    return img


def _resize_to_max(img: Image.Image, max_size: int) -> Image.Image:
    """按最长边等比缩放，不超过 max_size；若原图更小则保持原样。"""
    w, h = img.size
    if max(w, h) <= max_size:
        return img
    if w >= h:
        new_w = max_size
        new_h = int(h * max_size / w)
    else:
        new_h = max_size
        new_w = int(w * max_size / h)
    # 使用高质量 LANCZOS 重采样
    return img.resize((new_w, new_h), Image.LANCZOS)


def _encode(img: Image.Image, fmt: str = "JPEG") -> bytes:
    """将图片编码为字节流。"""
    buf = io.BytesIO()
    save_img = img
    # JPEG 不支持 RGBA，统一转 RGB
    if fmt.upper() == "JPEG" and save_img.mode in ("RGBA", "P"):
        save_img = save_img.convert("RGB")
    save_img.save(buf, format=fmt, quality=settings.FILE_IMAGE_QUALITY, optimize=True)
    return buf.getvalue()


def compress_chat_image(data: bytes) -> Tuple[bytes, bytes]:
    """压缩聊天图片，生成原图与缩略图。

    - 原图：最长边不超过 1280px，质量 FILE_IMAGE_QUALITY
    - 缩略图：最长边不超过 256px

    Returns:
        (original_bytes, thumbnail_bytes)
    """
    img = _open_image(data)
    # 原图压缩
    original_img = _resize_to_max(img, IMAGE_MAX_SIZE)
    original_bytes = _encode(original_img, "JPEG")
    # 缩略图
    thumbnail_img = _resize_to_max(img, THUMBNAIL_MAX_SIZE)
    thumbnail_bytes = _encode(thumbnail_img, "JPEG")
    return original_bytes, thumbnail_bytes


def compress_avatar(data: bytes) -> bytes:
    """将头像压缩为 256x256 正方形。

    采用居中裁剪策略：先把图片等比放大/缩小到短边 256，再居中裁剪为正方形。
    """
    img = _open_image(data)
    w, h = img.size
    # 以短边为基准缩放到 AVATAR_SIZE
    side = min(w, h)
    scale = AVATAR_SIZE / side
    new_w = int(w * scale)
    new_h = int(h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    # 居中裁剪为正方形
    left = (new_w - AVATAR_SIZE) // 2
    top = (new_h - AVATAR_SIZE) // 2
    img = img.crop((left, top, left + AVATAR_SIZE, top + AVATAR_SIZE))
    return _encode(img, "JPEG")


def compress_background(data: bytes) -> bytes:
    """压缩聊天背景图，最长边不超过 1920px。"""
    img = _open_image(data)
    img = _resize_to_max(img, 1920)
    return _encode(img, "JPEG")


def guess_image_content_type() -> str:
    """返回压缩后图片的 content_type。"""
    return "image/jpeg"
