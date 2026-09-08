"""스캐너 연결 상태 (명세 F.2 대시보드 / G.1 스캔 페이지)."""
from fastapi import APIRouter

from app.services.scanner import check_scanner_status

router = APIRouter(prefix="/scanner", tags=["scan"])


@router.get("/status", summary="[F.2/G.1] 스캐너 연결 상태")
def scanner_status():
    connected = check_scanner_status()
    return {"connected": connected, "status": "ok" if connected else "unreachable"}
