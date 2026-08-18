import uuid
import json
import datetime
from typing import Optional
from urllib.parse import parse_qs

import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

app = FastAPI(title="KICC Dual-Mode Kiosk Service (regTxtype 52 & 51 / payCode 11 / 120s Timeout)")

# ==================================================
# 인메모리 데이터베이스 및 상태 관리
# ==================================================
order_db = {}

# KICC PG 설정
KICC_PAY_REQ_URL = "https://testpg.easypay.co.kr/api/trade/request"  # KICC 전문 요청 URL
KICC_MID = "T0022488"                                                 # 👈 가맹점 MID 변경 완료
PAYMENT_TIMEOUT_SECONDS = 120                                         # ⏱️ 대기시간 120초

# ==================================================
# Pydantic 요청 모델
# ==================================================
class CreateQrRequest(BaseModel):
    kiosk_id: str          # 키오스크 일련번호 (예: "01", "02")
    amount: int            # 결제 금액
    goods_name: str        # 상품명

class SmsSendRequest(BaseModel):
    shop_order_no: str     # 생성된 주문번호
    phone_number: str      # 수신받을 고객 휴대폰 번호

# ==================================================
# 유틸리티 함수
# ==================================================
def generate_order_no(kiosk_id: str) -> str:
    now_str = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    short_uuid = str(uuid.uuid4()).split("-")[0][:4].upper()
    clean_kiosk_id = kiosk_id.replace("_", "").replace("-", "")
    return f"KSK_{clean_kiosk_id}_{now_str}_{short_uuid}"

def parse_payment_data(data: dict):
    shop_order_no = data.get("shopOrderNo") or data.get("shop_order_no") or data.get("ord_no") or data.get("Moid") or ""
    res_cd = data.get("resCd") or data.get("res_cd") or data.get("reply_cd") or ""
    card_name = data.get("cardName") or data.get("card_name") or ""
    card_no = data.get("cardNo") or data.get("card_no") or ""
    return str(shop_order_no), str(res_cd), str(card_name), str(card_no)

# ==================================================
# 1. [우선] regTxtype: 52 & payCode: 11 적용 QR 결제 생성 API
# ==================================================
@app.post("/api/payment/create-qr")
async def create_qr_payment(req: CreateQrRequest, request: Request):
    """
    1단계: KICC PG regTxtype="52", payCode="11" 전문을 호출하여 QR 결제 URL 생성 (120초 대기)
    """
    shop_order_no = generate_order_no(req.kiosk_id)
    base_url = str(request.base_url).rstrip("/")
    noti_url = f"{base_url}/api/kicc/webhook"

    now = datetime.datetime.now()
    expire_time = now + datetime.timedelta(seconds=PAYMENT_TIMEOUT_SECONDS)

    # KICC regTxtype: 52, payCode: 11 전문 구성
    kicc_qr_payload = {
        "mid": KICC_MID,
        "regTxtype": "52",                          # KICC QR/URL 결제 생성 전문 코드
        "payCode": "11",                            # 결제수단코드: 11 (신용카드)
        "shopOrderNo": shop_order_no,
        "amount": str(req.amount),
        "goodsName": req.goods_name,
        "mallName": "현장 키오스크",
        "notiUrl": noti_url
    }

    print(f"\n📌 [1. QR 결제 생성 요청 (regTxtype: 52, payCode: 11)]")
    print(f"키오스크 ID: {req.kiosk_id} | 주문번호: {shop_order_no} | 금액: {req.amount}원")

    payment_url = f"{base_url}/pay/page/{shop_order_no}"  # 기본 폴백 URL

    try:
        # KICC PG API 호출
        response = requests.post(
            KICC_PAY_REQ_URL,
            json=kicc_qr_payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=10
        )
        res_data = response.json()
        print(f"📥 [KICC regTxtype 52 응답]: {res_data}")

        # KICC에서 발급된 결제 URL이 있을 경우 적용
        if res_data.get("resCd") == "0000" and res_data.get("authUrl"):
            payment_url = res_data.get("authUrl")

    except Exception as e:
        print(f"⚠️ [KICC PG 통신 예외 발생, 로컬 URL 제공]: {e}")

    # DB에 주문 정보 및 120초 타임아웃 세팅
    order_db[shop_order_no] = {
        "kiosk_id": req.kiosk_id,
        "amount": req.amount,
        "goods_name": req.goods_name,
        "status": "WAITING",
        "created_at": now.isoformat(),
        "expires_at": expire_time.isoformat(),
        "card_name": "",
        "card_no": ""
    }

    return {
        "resCd": "0000",
        "resMsg": "성공",
        "kiosk_id": req.kiosk_id,
        "shop_order_no": shop_order_no,
        "payment_url": payment_url,
        "goods_name": req.goods_name,
        "amount": req.amount,
        "timeout_seconds": PAYMENT_TIMEOUT_SECONDS
    }

# ==================================================
# 2. [보조] regTxtype: 51 & payCode: 11 적용 SMS 발송 API
# ==================================================
@app.post("/api/payment/send-sms")
async def send_payment_sms(req: SmsSendRequest, request: Request):
    """
    2단계: KICC PG regTxtype="51", payCode="11" 전문을 호출하여 SMS 문자 발송
    """
    if req.shop_order_no not in order_db:
        raise HTTPException(status_code=404, detail="존재하지 않는 주문번호입니다.")

    order_info = order_db[req.shop_order_no]
    
    # 120초 타임아웃 검증
    expire_dt = datetime.datetime.fromisoformat(order_info["expires_at"])
    if datetime.datetime.now() > expire_dt:
        order_info["status"] = "EXPIRED"
        return {"resCd": "4010", "resMsg": "결제 가능 시간(120초)이 초과되었습니다."}

    clean_phone = req.phone_number.replace("-", "").strip()

    # KICC PG regTxtype: 51, payCode: 11 전문 구성
    kicc_sms_payload = {
        "mid": KICC_MID,
        "regTxtype": "51",                          # KICC SMS URL 결제 요청 전문 코드
        "payCode": "11",                            # 결제수단코드: 11 (신용카드)
        "shopOrderNo": req.shop_order_no,
        "amount": str(order_info["amount"]),
        "goodsName": order_info["goods_name"],
        "rcvrHpNo": clean_phone,
        "mallName": "현장 키오스크",
        "notiUrl": f"{str(request.base_url).rstrip('/')}/api/kicc/webhook"
    }

    print(f"\n📱 [2. SMS 발송 요청 (regTxtype: 51, payCode: 11)]")
    print(f"주문번호: {req.shop_order_no} | 수신번호: {clean_phone}")

    try:
        response = requests.post(
            KICC_PAY_REQ_URL,
            json=kicc_sms_payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=10
        )
        res_data = response.json()
        print(f"📥 [KICC regTxtype 51 응답]: {res_data}")

        if res_data.get("resCd") == "0000":
            return {
                "resCd": "0000",
                "resMsg": "SMS 결제문자가 성공적으로 발송되었습니다.",
                "shop_order_no": req.shop_order_no
            }
        else:
            return {
                "resCd": res_data.get("resCd", "5001"),
                "resMsg": f"SMS 발송 실패: {res_data.get('resMsg', 'PG 오류')}"
            }

    except Exception as e:
        print(f"❌ [KICC 통신 에러]: {e}")
        return {"resCd": "5001", "resMsg": "PG 통신 중 오류가 발생했습니다."}

# ==================================================
# 3. KICC Webhook (QR/SMS 공통 결제 완료 노티 수신)
# ==================================================
@app.post("/api/kicc/webhook")
@app.post("/api/kicc/webhook/")
async def kicc_webhook(request: Request):
    try:
        try:
            data = await request.json()
        except Exception:
            raw_body = await request.body()
            body_str = raw_body.decode("utf-8", errors="ignore")
            parsed = parse_qs(body_str)
            data = {k: v[0] for k, v in parsed.items() if v} if parsed else json.loads(body_str) if body_str else {}

        shop_order_no, res_cd, card_name, card_no = parse_payment_data(data)

        if shop_order_no in order_db and res_cd == "0000":
            order_db[shop_order_no]["status"] = "PAID"
            order_db[shop_order_no]["card_name"] = str(card_name)
            order_db[shop_order_no]["card_no"] = str(card_no)

            print(f"✅ [승인 완료] 키오스크: {order_db[shop_order_no]['kiosk_id']} | 주문번호: {shop_order_no}")

        return JSONResponse(content={"resCd": "0000", "resMsg": "정상"}, status_code=200)

    except Exception as e:
        print(f"❌ [Webhook Error]: {e}")
        return JSONResponse(content={"resCd": "0000", "resMsg": "정상"}, status_code=200)

# ==================================================
# 4. 키오스크 전용 결제 상태 조회 API (120초 타임아웃 감지)
# ==================================================
@app.get("/api/payment/status/{shop_order_no}")
async def get_payment_status(shop_order_no: str):
    if shop_order_no not in order_db:
        return {"status": "NOT_FOUND", "resCd": "4040"}

    order = order_db[shop_order_no]
    
    # 120초 초과 여부 체크
    expire_dt = datetime.datetime.fromisoformat(order["expires_at"])
    if order["status"] == "WAITING" and datetime.datetime.now() > expire_dt:
        order["status"] = "EXPIRED"

    return {
        "resCd": "0000",
        "kiosk_id": order["kiosk_id"],
        "shop_order_no": shop_order_no,
        "status": order["status"],  # WAITING, PAID, EXPIRED, FAILED
        "card_name": order["card_name"],
        "card_no": order["card_no"]
    }
