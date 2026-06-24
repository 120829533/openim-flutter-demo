"""版本检查接口。"""
import logging

from fastapi import APIRouter, Query

from app.database import fetchone
from app.schemas.common import error, success

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/check")
async def check_version(platform: str = Query(..., description="平台 android/ios")):
    """返回 app_versions 中该平台 version_code 最大的记录。"""
    platform = platform.strip().lower()
    if not platform:
        return error(code=400, msg="platform 不能为空")

    row = await fetchone(
        """
        SELECT id, platform, version, version_code, download_url, update_log, is_force, created_at
        FROM app_versions
        WHERE platform = %s
        ORDER BY version_code DESC
        LIMIT 1
        """,
        (platform,),
    )
    if not row:
        return error(code=404, msg="未找到该平台的版本信息")

    return success(data={
        "platform": row.get("platform"),
        "version": row.get("version"),
        "version_code": row.get("version_code"),
        "download_url": row.get("download_url"),
        "update_log": row.get("update_log"),
        "is_force": row.get("is_force"),
        "created_at": _dt_to_str(row.get("created_at")),
    })


def _dt_to_str(val):
    """datetime 转字符串。"""
    if val is None:
        return None
    return val.strftime("%Y-%m-%d %H:%M:%S") if hasattr(val, "strftime") else str(val)
