"""配置模块，使用 pydantic-settings 读取环境变量。"""
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """服务配置，从环境变量（.env）注入。"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # MinIO 对象存储配置（endpoint 可带 http:// 前缀，会自动剥离）
    MINIO_ENDPOINT: str = "openim-minio-service:9000"
    MINIO_ROOT_USER: str = "openim"
    MINIO_ROOT_PASSWORD: str = "openim12345"
    # 是否使用 HTTPS 访问 MinIO（若 endpoint 以 https:// 开头则自动置 True）
    MINIO_SECURE: bool = False

    @field_validator("MINIO_ENDPOINT")
    @classmethod
    def _normalize_endpoint(cls, v: str) -> str:
        """剥离 endpoint 中的 scheme，MinIO SDK 只接受 host:port。"""
        v = v.strip()
        low = v.lower()
        if low.startswith("https://"):
            return v[len("https://"):]
        if low.startswith("http://"):
            return v[len("http://"):]
        return v

    # Redis 配置（预留，用于后续缓存/限流）
    REDIS_HOST: str = "openim-redis-service"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = "openim123"
    REDIS_DB: int = 0

    # 文件上传限制（MB）
    FILE_MAX_SIZE_MB: int = 100
    # 图片压缩质量（1-95）
    FILE_IMAGE_QUALITY: int = 85

    # 对外访问的基础 URL（用于拼接可下载链接）
    # 默认走本服务的 /api/file/download 代理下载
    PUBLIC_BASE_URL: str = ""

    @property
    def file_max_size_bytes(self) -> int:
        """文件最大字节数。"""
        return self.FILE_MAX_SIZE_MB * 1024 * 1024


# 全局单例配置
settings = Settings()
