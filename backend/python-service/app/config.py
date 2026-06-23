"""应用配置模块。

使用 pydantic-settings 从环境变量（或 .env 文件）读取配置。
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置项。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # MySQL 配置
    MYSQL_HOST: str = "openim-mysql-service"
    MYSQL_PORT: int = 3306
    MYSQL_DATABASE: str = "openim"
    MYSQL_USER: str = "openim"
    MYSQL_PASSWORD: str = "openim123"
    MYSQL_POOL_SIZE: int = 10
    MYSQL_AUTOCOMMIT: bool = True

    # Redis 配置
    REDIS_HOST: str = "openim-redis-service"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = "openim123"
    REDIS_DB: int = 0

    # JWT 配置
    PYTHON_JWT_SECRET: str = "openim-jwt-secret-change-me"
    PYTHON_JWT_EXPIRE_HOURS: int = 168
    JWT_ALGORITHM: str = "HS256"

    # 短信验证码配置
    SMS_CODE_LENGTH: int = 6
    SMS_CODE_TTL_SECONDS: int = 300
    # 开发模式：固定返回 123456
    SMS_DEV_MODE: bool = True
    SMS_DEV_CODE: str = "123456"

    # 外部服务地址
    FILE_SERVICE_URL: str = "http://openim-file-service:8083"
    JAVA_SERVICE_URL: str = "http://openim-java-service:8082"

    # 客户端配置（OpenIM 兼容）
    DISCOVER_PAGE_URL: str = "discover"
    ALLOW_SEND_MSG_NOT_FRIEND: str = "1"

    # 在线状态 TTL（秒）
    ONLINE_TTL_SECONDS: int = 60


settings = Settings()
