"""MinIO 对象存储适配层。

封装 ObjectStorageClient 类，内部使用 minio python SDK。
未来切换阿里云 COS / 腾讯 OSS 只需替换此实现，上层业务不变。
"""
from __future__ import annotations

import logging
from datetime import timedelta
from io import BytesIO
from typing import Iterator, Optional

from minio import Minio
from minio.error import S3Error

from .config import settings

logger = logging.getLogger(__name__)

# 系统所需的全部 bucket 名称
REQUIRED_BUCKETS = [
    "openim-avatar",      # 用户头像
    "openim-chat-image",  # 聊天图片（原图+缩略图）
    "openim-file",        # 发送的文件
    "openim-background",  # 聊天背景图片
    "openim-release",     # 客户端版本更新包
]


class ObjectStorageClient:
    """对象存储客户端适配层。

    屏蔽底层 MinIO SDK 细节，对外提供统一的上传/下载/预签名/初始化接口。
    若后续迁移到阿里云 COS 或腾讯 OSS，仅需保持方法签名一致即可平滑替换。
    """

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        secure: bool = False,
    ) -> None:
        self.endpoint = endpoint
        self.secure = secure
        # 创建 MinIO 客户端（不使用证书校验，内网部署）
        self._client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )

    def ensure_bucket(self, bucket: str) -> None:
        """确保 bucket 存在，不存在则创建。"""
        try:
            exists = self._client.bucket_exists(bucket)
            if not exists:
                self._client.make_bucket(bucket)
                logger.info("已创建 bucket: %s", bucket)
            else:
                logger.debug("bucket 已存在: %s", bucket)
        except S3Error as e:
            logger.error("确保 bucket 存在失败: %s, 错误: %s", bucket, e)
            raise

    def ensure_all_buckets(self, buckets: Optional[list[str]] = None) -> None:
        """批量确保所有所需 bucket 存在。"""
        target = buckets if buckets is not None else REQUIRED_BUCKETS
        for bucket in target:
            self.ensure_bucket(bucket)

    def upload(
        self,
        bucket: str,
        object_name: str,
        data: BytesIO | bytes,
        length: int,
        content_type: str = "application/octet-stream",
    ) -> str:
        """上传对象到指定 bucket。

        Args:
            bucket: bucket 名称
            object_name: 对象名（key）
            data: 文件数据（BytesIO 或 bytes）
            length: 数据长度（字节）
            content_type: MIME 类型

        Returns:
            object_name（上传后的对象名）
        """
        if isinstance(data, (bytes, bytearray)):
            stream: BytesIO = BytesIO(data)
        else:
            # 已经是 BytesIO，确保指针在开头
            data.seek(0)
            stream = data
        try:
            self._client.put_object(
                bucket_name=bucket,
                object_name=object_name,
                data=stream,
                length=length,
                content_type=content_type,
            )
            logger.info("上传成功: %s/%s (%d bytes)", bucket, object_name, length)
            return object_name
        except S3Error as e:
            logger.error("上传失败: %s/%s, 错误: %s", bucket, object_name, e)
            raise

    def download(self, bucket: str, object_name: str) -> Iterator[bytes]:
        """下载对象，返回字节流迭代器（用于流式响应）。"""
        try:
            response = self._client.get_object(bucket, object_name)
            try:
                # get_object 返回 HTTPStreamResponse，可迭代
                for chunk in response.stream(amt=64 * 1024):
                    yield chunk
            finally:
                response.close()
                response.release_conn()
        except S3Error as e:
            logger.error("下载失败: %s/%s, 错误: %s", bucket, object_name, e)
            raise

    def get_object_info(self, bucket: str, object_name: str):
        """获取对象元信息（stat）。"""
        try:
            return self._client.stat_object(bucket, object_name)
        except S3Error as e:
            logger.error("获取对象信息失败: %s/%s, 错误: %s", bucket, object_name, e)
            raise

    def presigned_url(
        self,
        bucket: str,
        object_name: str,
        expires: int = 3600,
    ) -> str:
        """生成预签名下载 URL。

        Args:
            bucket: bucket 名称
            object_name: 对象名
            expires: 过期时间（秒），默认 3600

        Returns:
            预签名 URL 字符串
        """
        try:
            url = self._client.presigned_get_object(
                bucket_name=bucket,
                object_name=object_name,
                expires=timedelta(seconds=expires),
            )
            return url
        except S3Error as e:
            logger.error("生成预签名 URL 失败: %s/%s, 错误: %s", bucket, object_name, e)
            raise


# 全局单例客户端
storage_client = ObjectStorageClient(
    endpoint=settings.MINIO_ENDPOINT,
    access_key=settings.MINIO_ROOT_USER,
    secret_key=settings.MINIO_ROOT_PASSWORD,
    secure=settings.MINIO_SECURE,
)
