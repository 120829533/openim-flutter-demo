"""多语言文本接口。"""
import logging

from fastapi import APIRouter, Query

from app.database import fetch
from app.schemas.common import error, success

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/texts")
async def get_texts(lang: str = Query(..., description="语言代码，如 zh-CN")):
    """返回 i18n_texts 中该语言所有 key-value。"""
    lang = lang.strip()
    if not lang:
        return error(code=400, msg="lang 不能为空")

    rows = await fetch(
        "SELECT key_name, value FROM i18n_texts WHERE lang = %s",
        (lang,),
    )
    # 组装为 {key: value} 字典
    texts = {row["key_name"]: row["value"] for row in rows}
    return success(data={"lang": lang, "texts": texts})
