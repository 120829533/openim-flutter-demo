"""FastAPI 文件服务入口。

服务名: openim-file-service
端口: 8083
职责: OpenIM 文件处理与存储适配（文件上传、图片压缩、MinIO 对象存储交互）

启动时初始化 MinIO bucket。
"""
from __future__ import annotations

import logging

from fastapi import FastAPI

from .minio_client import REQUIRED_BUCKETS, storage_client
from .routers import file as file_router

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="OpenIM File Service",
    description="OpenIM 文件处理与存储适配服务",
    version="1.0.0",
)


@app.on_event("startup")
async def startup_event() -> None:
    """应用启动时初始化 MinIO bucket。"""
    logger.info("正在初始化 MinIO bucket ...")
    try:
        storage_client.ensure_all_buckets(REQUIRED_BUCKETS)
        logger.info("MinIO bucket 初始化完成: %s", REQUIRED_BUCKETS)
    except Exception as e:  # noqa: BLE001
        # bucket 初始化失败不阻断启动，便于在 MinIO 未就绪时也能启动
        # 后续上传请求会再次触发 ensure_bucket
        logger.error("MinIO bucket 初始化失败（服务仍将启动）: %s", e)


@app.get("/health")
async def health_check():
    """健康检查接口。"""
    return {"code": 0, "msg": "ok", "data": {"status": "healthy"}}


@app.get("/")
async def root():
    """根路径，返回服务信息。"""
    return {
        "code": 0,
        "msg": "ok",
        "data": {
            "service": "openim-file-service",
            "version": "1.0.0",
            "docs": "/docs",
        },
    }


# 注册路由
app.include_router(file_router.router)
