"""FastAPI 应用入口。

挂载所有 router，配置 CORS，并在启动/关闭事件中初始化与释放资源。
"""
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.database import close_db, init_db
from app.redis_client import close_redis, init_redis
from app.routers import auth, conversation, i18n, openim_compat, settings as settings_router, user, version
from app.schemas.common import error

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="OpenIM Python Service",
    description="OpenIM 业务逻辑服务：账号、会话管理、设置、版本、多语言等",
    version="1.0.0",
)

# CORS 配置：允许所有来源（生产环境应按需收紧）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    """应用启动：初始化数据库连接池与 Redis 客户端。"""
    logger.info("应用启动中...")
    await init_db()
    await init_redis()
    logger.info("应用启动完成")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    """应用关闭：释放数据库与 Redis 资源。"""
    logger.info("应用关闭中...")
    await close_redis()
    await close_db()
    logger.info("应用已关闭")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理，返回统一响应体。"""
    logger.exception("未处理的异常: %s", exc)
    return JSONResponse(status_code=200, content=error(code=500, msg="服务器内部错误"))


@app.get("/health")
async def health():
    """健康检查接口。"""
    return {"code": 0, "msg": "ok", "data": {"status": "healthy"}}


# 挂载路由（统一前缀 /api）
app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(user.router, prefix="/api/user", tags=["用户"])
app.include_router(conversation.router, prefix="/api/conversation", tags=["会话"])
app.include_router(settings_router.router, prefix="/api/settings", tags=["设置"])
app.include_router(version.router, prefix="/api/version", tags=["版本"])
app.include_router(i18n.router, prefix="/api/i18n", tags=["多语言"])

# OpenIM Chat API 兼容层（无前缀，路径与 OpenIM Chat Server 一致）
app.include_router(openim_compat.router, tags=["OpenIM兼容"])
