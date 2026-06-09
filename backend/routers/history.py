"""
历史记录 CRUD 路由
"""

from fastapi import APIRouter, Query, Request

from deps import _get_client_ip, _load_history, _save_history

router = APIRouter()


@router.get("/api/history")
async def get_history(request: Request, limit: int = Query(50, ge=1, le=200)):
    ip = _get_client_ip(request)
    return {"history": _load_history(ip)[:limit]}


@router.delete("/api/history")
async def clear_history(request: Request):
    ip = _get_client_ip(request)
    _save_history(ip, [])
    return {"message": "历史记录已清空"}


@router.delete("/api/history/{record_id}")
async def delete_history_record(record_id: str, request: Request):
    ip = _get_client_ip(request)
    history = [h for h in _load_history(ip) if h.get("id") != record_id]
    _save_history(ip, history)
    return {"message": "已删除"}
