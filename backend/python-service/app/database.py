"""数据库访问模块。

使用 aiomysql.create_pool 创建异步连接池，并封装
fetch / fetchone / execute 辅助函数，统一使用原生 SQL。
"""
import logging
from typing import Any, Optional, Sequence

import aiomysql

from app.config import settings

logger = logging.getLogger(__name__)

# 全局连接池（在应用启动事件中初始化）
_pool: Optional[aiomysql.Pool] = None


async def init_db() -> None:
    """初始化数据库连接池。"""
    global _pool
    if _pool is not None:
        return
    _pool = await aiomysql.create_pool(
        host=settings.MYSQL_HOST,
        port=settings.MYSQL_PORT,
        db=settings.MYSQL_DATABASE,
        user=settings.MYSQL_USER,
        password=settings.MYSQL_PASSWORD,
        minsize=1,
        maxsize=settings.MYSQL_POOL_SIZE,
        autocommit=settings.MYSQL_AUTOCOMMIT,
        charset="utf8mb4",
    )
    logger.info("MySQL 连接池已创建: %s:%s/%s", settings.MYSQL_HOST, settings.MYSQL_PORT, settings.MYSQL_DATABASE)


async def close_db() -> None:
    """关闭数据库连接池。"""
    global _pool
    if _pool is not None:
        _pool.close()
        await _pool.wait_closed()
        _pool = None
        logger.info("MySQL 连接池已关闭")


def get_pool() -> aiomysql.Pool:
    """获取当前连接池。"""
    if _pool is None:
        raise RuntimeError("数据库连接池尚未初始化，请先调用 init_db()")
    return _pool


async def fetch(sql: str, args: Sequence[Any] = ()) -> list[dict]:
    """执行查询，返回所有行（每行为 dict）。"""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql, args)
            rows = await cur.fetchall()
            return list(rows)


# 别名，兼容 openim_compat 等模块的导入
fetchall = fetch


async def fetchone(sql: str, args: Sequence[Any] = ()) -> Optional[dict]:
    """执行查询，返回单行（dict）或 None。"""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql, args)
            return await cur.fetchone()


async def execute(sql: str, args: Sequence[Any] = ()) -> int:
    """执行写操作（INSERT/UPDATE/DELETE），返回受影响行数。

    注意：默认连接 autocommit=True，写操作会自动提交。
    若需要获取自增主键，请使用 execute_returning 或在 SQL 中使用 LAST_INSERT_ID()。
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql, args)
            return cur.rowcount


async def execute_returning(sql: str, args: Sequence[Any] = ()) -> int:
    """执行 INSERT 并返回自增主键 lastrowid。"""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql, args)
            return cur.lastrowid
