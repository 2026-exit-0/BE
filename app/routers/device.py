"""HW(ESP32) 중계 서버 연동.

- /device/scans/*  — 기기 전용 인증(X-Device-Key)으로 스캔 세션 트리거/완료 처리.
- /device/link/*   — 로그인한 사용자가 "지금 이 기기는 내 것" 이라고 연결/해제.
  device_id → user_id 는 더 이상 .env 고정 매핑이 아니라 DeviceConnection(현재 연결 1건)으로 조회한다.
  트리거 시점에 연결된 user_id 로 세션 소유자가 확정되고, 이후 기기 연결이 바뀌어도
  이미 시작된 세션에는 영향 없다(세션에 user_id 를 그대로 저장해두기 때문).
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, verify_device_key, verify_device_or_user
from app.crud.scan import (expire_stale_sessions, get_device_connection,
                           get_latest_processing_session, get_latest_session)
from app.models.scan import DeviceConnection, ScanImage, ScanResult, ScanSession
from app.schemas.device import DeviceDoneIn, DeviceLinkOut, DeviceScanOut, DeviceTriggerIn

router = APIRouter(prefix="/device/scans", tags=["scan"],
                   dependencies=[Depends(verify_device_key)])
link_router = APIRouter(prefix="/device/link", tags=["scan"])


def _resolve_user_id(db: Session, device_id: str) -> str:
    connection = get_device_connection(db, device_id)
    if not connection:
        raise HTTPException(status_code=400, detail="연결된 사용자가 없습니다")
    return connection.user_id


@router.post("/trigger", response_model=DeviceScanOut, status_code=201,
             summary="[HW] 스캔 트리거 (기기 전용 세션 생성)")
def device_trigger(data: DeviceTriggerIn, db: Session = Depends(get_db)):
    user_id = _resolve_user_id(db, data.device_id)
    expire_stale_sessions(db, user_id)

    existing = get_latest_processing_session(db, user_id)
    if existing:
        # 이미 진행 중 — 새로 만들지 않고 기존 세션 정보를 담아 409
        raise HTTPException(status_code=409, detail={
            "message": "이미 진행 중인 스캔이 있습니다",
            "session_id": existing.session_id,
            "status": existing.status,
        })

    session = ScanSession(user_id=user_id, status="processing",
                          source="hardware", device_id=data.device_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.post("/done", response_model=DeviceScanOut,
             summary="[HW] 스캔 완료 콜백 (측정값·사진 저장)")
def device_done(data: DeviceDoneIn, db: Session = Depends(get_db)):
    user_id = _resolve_user_id(db, data.device_id)
    expire_stale_sessions(db, user_id)

    try:
        scanned_at = datetime.strptime(data.timestamp, "%Y%m%d_%H%M%S")
    except ValueError:
        raise HTTPException(status_code=422,
                            detail="timestamp 형식이 올바르지 않습니다 (예: 20260928_224509)")

    session = get_latest_processing_session(db, user_id)
    if not session:
        # 멱등성 — processing 이 없으면, 이미 done 처리된 "같은" 완료 알림의 재전송인지 확인.
        # session_id 가 페이로드에 없어서 device_id + timestamp 일치로 동일 이벤트임을 판별한다.
        latest = get_latest_session(db, user_id)
        if (latest and latest.status == "done" and latest.device_id == data.device_id
                and latest.scanned_at == scanned_at):
            return latest
        raise HTTPException(status_code=404, detail="진행 중인 스캔 세션을 찾을 수 없습니다")

    session.scanned_at = scanned_at
    if data.part:
        session.scan_area = data.part

    result = db.query(ScanResult).filter(ScanResult.session_id == session.session_id).first()
    if not result:
        result = ScanResult(session_id=session.session_id)
        db.add(result)
    result.moisture = data.moisture
    result.sebum = data.oil   # "유분" — 기존 sebum 컬럼과 동일 개념

    db.add(ScanImage(session_id=session.session_id, image_type="WHITE_LED",
                     image_url=data.white_img, region=data.part))
    db.add(ScanImage(session_id=session.session_id, image_type="UV_LED",
                     image_url=data.uv_img, region=data.part))

    session.status = "done"
    db.commit()
    db.refresh(session)
    return session


@link_router.post("", response_model=DeviceLinkOut, summary="[HW] 기기-사용자 연결")
def link_device(data: DeviceTriggerIn, db: Session = Depends(get_db),
               user=Depends(get_current_user)):
    connection = get_device_connection(db, data.device_id)
    now = datetime.now()
    if connection:
        connection.user_id = user.user_id
        connection.connected_at = now
    else:
        connection = DeviceConnection(device_id=data.device_id, user_id=user.user_id, connected_at=now)
        db.add(connection)
    db.commit()
    db.refresh(connection)
    return connection


@link_router.delete("/{device_id}", status_code=204, summary="[HW] 기기-사용자 연결 해제")
def unlink_device(device_id: str, db: Session = Depends(get_db),
                  user=Depends(get_current_user)):
    connection = get_device_connection(db, device_id)
    if not connection:
        raise HTTPException(status_code=404, detail="연결된 기기를 찾을 수 없습니다")
    if connection.user_id != user.user_id:
        raise HTTPException(status_code=403, detail="본인이 연결한 기기만 해제할 수 있습니다")
    db.delete(connection)
    db.commit()


@link_router.get("/{device_id}", response_model=DeviceLinkOut,
                 summary="[HW] 기기 연결 상태 조회 (기기 키 또는 로그인)")
def get_device_link(device_id: str, db: Session = Depends(get_db),
                    _=Depends(verify_device_or_user)):
    connection = get_device_connection(db, device_id)
    if not connection:
        return DeviceLinkOut(device_id=device_id, user_id=None, connected_at=None)
    return connection
