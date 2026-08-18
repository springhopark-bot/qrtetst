import uuid
import requests
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

app = FastAPI(title="Kiosk Payment Service")

# --------------------------------------------------
# 🔑 KICC 설정 및 충전 단가
# --------------------------------------------------
MALL_ID = "T0022488"
KICC_API_URL = "https://testpgapi.easypay.co.kr/directapi/trades/directSmsUrlPayReg"
BASE_URL = "https://qrtetst.onrender.com"

# 충전 단가 설정 (원/kWh)
UNIT_PRICE = 350

order_db = {}
latest_payment = {
    "status": "PENDING",
    "amount": 0,
    "volume": "",
    "card_name": "",
    "card_no": ""
}

class PayRequest(BaseModel):
    amount: int
    volume: str

# ==================================================
# 1. 키오스크 메인 UI (캐시 방지 헤더 적용)
# ==================================================
@app.get("/", response_class=HTMLResponse)
async def read_root():
    content = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate" />
    <meta http-equiv="Pragma" content="no-cache" />
    <meta http-equiv="Expires" content="0" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>전기차 충전 결제 키오스크</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; text-align: center; padding: 40px 20px; background: #f0f2f5; margin: 0; }}
        .card {{ max-width: 500px; margin: 0 auto; background: white; padding: 35px 25px; border-radius: 16px; box-shadow: 0 8px 24px rgba(0,0,0,0.08); }}
        h2 {{ margin-top: 0; color: #1a1a1a; font-size: 24px; font-weight: 700; }}
        .unit-price-badge {{ display: inline-block; background: #e7f1ff; color: #007bff; font-weight: 600; font-size: 14px; padding: 6px 14px; border-radius: 20px; margin-bottom: 20px; }}
        
        .btn-group {{ display: flex; gap: 12px; justify-content: center; margin-bottom: 15px; }}
        .option-btn {{ flex: 1; padding: 18px 10px; border: 2px solid #e1e4e8; background: #fff; border-radius: 12px; cursor: pointer; font-weight: 700; font-size: 17px; color: #333; transition: all 0.2s ease; }}
        .option-btn:hover {{ border-color: #007bff; color: #007bff; }}
        .option-btn.active {{ background: #007bff; color: white; border-color: #007bff; box-shadow: 0 4px 12px rgba(0,123,255,0.3); }}
        .price-text {{ font-size: 13.5px; opacity: 0.9; margin-top: 6px; font-weight: 500; }}
        
        .notice-box {{ font-size: 13px; color: #555; margin-bottom: 24px; text-align: left; word-break: keep-all; line-height: 1.5; background: #f8f9fa; border-left: 4px solid #007bff; padding: 12px 14px; border-radius: 4px; }}
        
        .pay-btn {{ width: 100%; padding: 18px; background: #28a745; color: white; font-size: 18px; font-weight: 700; border: none; border-radius: 12px; cursor: pointer; transition: background 0.2s ease; box-shadow: 0 4px 12px rgba(40,167,69,0.3); }}
        .pay-btn:hover {{ background: #218838; }}
        
        .status-box {{ display: none; margin-top: 25px; padding: 20px; border-radius: 12px; background: #f8f9fa; border: 1px solid #e9ecef; }}
        .qr-img {{ width: 220px; height: 220px; margin: 15px auto; border: 4px solid #fff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); display: block; }}
        .spinner {{ border: 4px solid #f3f3f3; border-top: 4px solid #007bff; border-radius: 50%; width: 20px; height: 20px; animation: spin 1s linear infinite; display: inline-block; vertical-align: middle; margin-right: 8px; }}
        @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}

        .qr-timer {{ font-size: 14px; color: #dc3545; font-weight: 700; margin-top: 12px; }}

        .result-box {{ display: none; background: #f0fff4; border: 2px solid #28a745; border-radius: 12px; padding: 25px 20px; margin-top: 25px; animation: fadeIn 0.3s ease-in-out; }}
        @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: translateY(0); }} }}
        .result-box h3 {{ color: #28a745; margin: 0 0 15px 0; font-size: 20px; }}
        .card-info {{ font-size: 15px; color: #333; margin: 15px 0; background: white; padding: 15px; border-radius: 8px; border: 1px solid #d4edda; text-align: left; line-height: 1.8; }}
        .card-info p {{ margin: 4px 0; display: flex; justify-content: space-between; }}
        .card-info span.value {{ font-weight: 600; color: #1a1a1a; }}
        .charging-msg {{ font-size: 19px; font-weight: 700; color: #007bff; margin-top: 20px; letter-spacing: -0.5px; }}
        .timer {{ font-size: 14px; color: #666; margin-top: 8px; }}
        .timer-num {{ font-weight: bold; color: #dc3545; font-size: 16px; }}
    </style>
</head>
<body>

<div class="card">
    <h2>⚡ 충전 목표량 선택</h2>
    <div class="unit-price-badge">현재 충전 단가: {UNIT_PRICE:,}원 / kWh</div>
    
    <div class="btn-group">
        <button class="option-btn active" onclick="selectOption(this, '20kWh', {20 * UNIT_PRICE})">
            20 kWh
            <div class="price-text">{(20 * UNIT_PRICE):,}원</div>
        </button>
        <button class="option-btn" onclick="selectOption(this, '40kWh', {40 * UNIT_PRICE})">
            40 kWh
            <div class="price-text">{(40 * UNIT_PRICE):,}원</div>
        </button>
        <button class="option-btn" onclick="selectOption(this, '60kWh', {60 * UNIT_PRICE})">
            60 kWh
            <div class="price-text">{(60 * UNIT_PRICE):,}원</div>
        </button>
    </div>

    <div class="notice-box">
        💡 <b>안내사항</b><br>
        목표 충전량에 도달하지 않고 중단된 경우, 실제 충전된 양만큼만 최종 정산되며 남은 금액은 자동으로 부분취소 처리됩니다.
    </div>

    <button id="payStartBtn" class="pay-btn" onclick="startPayment()">결제 및 충전 시작</button>

    <div id="statusBox" class="status-box">
        <h4 style="margin:0; color:#333;">스마트폰 카메라 또는 앱카드로 QR을 스캔하세요</h4>
        <img id="qrImage" class="qr-img" src="" alt="KICC 결제 QR코드">
        <p style="margin: 8px 0 0 0; font-size: 14px; color: #495057; font-weight: 600;">
            <span class="spinner"></span>KICC 결제 승인 확인 중...
        </p>
        <div class="qr-timer">⏱️ <span id="qrCountdown">60</span>초 내에 결제를 완료해 주세요</div>
    </div>

    <div id="resultBox" class="result-box">
        <h3>✅ 결제가 완료되었습니다!</h3>
        <div class="card-info">
            <p><span>결제 카드</span><span id="cardName" class="value">-</span></p>
            <p><span>카드 번호</span><span id="cardNo" class="value">-</span></p>
            <p><span>목표 충전량</span><span id="payVolume" class="value">-</span></p>
            <p><span>선결제 금액</span><span id="payAmount" class="value">-</span></p>
        </div>
        <div class="charging-msg">🔌 5초 후 커넥터 승인이 시작됩니다...</div>
        <div class="timer"><span id="countdown" class="timer-num">5</span>초 후 화면이 리셋됩니다.</div>
    </div>
</div>

<script>
    let selectedVolume = "20kWh";
    let selectedAmount = {20 * UNIT_PRICE};
    let pollInterval = null;
    let qrTimeoutTimer = null;
    let qrLeftSeconds = 60;

    function selectOption(btn, volume, amount) {{
        document.querySelectorAll('.option-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        selectedVolume = volume;
        selectedAmount = amount;
    }}

    function resetAllTimers() {{
        if (pollInterval) clearInterval(pollInterval);
        if (qrTimeoutTimer) clearInterval(qrTimeoutTimer);
    }}

    async function startPayment() {{
        await fetch('/api/payment/reset', {{ method: 'POST' }});
        resetAllTimers();
        
        try {{
            const response = await fetch('/api/kicc/create-order', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ amount: selectedAmount, volume: selectedVolume }})
            }});

            const data = await response.json();

            if (data.success && data.payUrl) {{
                const qrData = encodeURIComponent(data.payUrl);
                document.getElementById('qrImage').src = `https://api.qrserver.com/v1/create-qr-code/?size=220x220&data=${{qrData}}`;
                
                document.getElementById('statusBox').style.display = 'block';
                document.getElementById('resultBox').style.display = 'none';
                document.getElementById('payStartBtn').style.display = 'none';
                
                // 1분(60초) 타임아웃 카운트다운 시작
                qrLeftSeconds = 60;
                document.getElementById('qrCountdown').innerText = qrLeftSeconds;

                qrTimeoutTimer = setInterval(() => {{
                    qrLeftSeconds--;
                    document.getElementById('qrCountdown').innerText = qrLeftSeconds;

                    if (qrLeftSeconds <= 0) {{
                        resetAllTimers();
                        alert("⏱️ 결제 시간이 초과되었습니다. 초기 화면으로 이동합니다.");
                        location.reload();
                    }}
                }}, 1000);

                // 결제 승인 폴링 (1초 주기)
                pollInterval = setInterval(checkPaymentStatus, 1000);
            }} else {{
                alert("KICC 결제 URL 생성 실패: " + (data.msg || "오류 발생"));
            }}
        }} catch (e) {{
            alert("서버 통신 실패: " + e.message);
        }}
    }}

    async function checkPaymentStatus() {{
        try {{
            const res = await fetch('/api/payment/status');
            const data = await res.json();

            if (data.status === "SUCCESS") {{
                resetAllTimers();
                document.getElementById('statusBox').style.display = 'none';
                showSuccessUI(data);
            }}
        }} catch (e) {{
            console.error("상태 확인 오류:", e);
        }}
    }}

    function showSuccessUI(data) {{
        // acquirerName 또는 노티에서 파싱된 카드 정보 주입
        const cardNameElem = document.getElementById('cardName');
        cardNameElem.innerText = (data.card_name && data.card_name.trim() !== "") ? data.card_name : "신용카드";

        document.getElementById('cardNo').innerText = data.card_no || "****-****-****-****";
        document.getElementById('payAmount').innerText = (data.amount || selectedAmount).toLocaleString() + "원";
        document.getElementById('payVolume').innerText = data.volume || selectedVolume;

        document.getElementById('resultBox').style.display = 'block';

        let seconds = 5;
        const countElem = document.getElementById('countdown');

        const timer = setInterval(() => {{
            seconds--;
            countElem.innerText = seconds;

            if (seconds <= 0) {{
                clearInterval(timer);
                alert("⚡ 충전이 시작되었습니다!");
                location.reload();
            }}
        }}, 1000);
    }}
</script>

</body>
</html>"""
    return HTMLResponse(content=content, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

# ==================================================
# 2. KICC 결제 URL 생성 API
# ==================================================
@app.post("/api/kicc/create-order")
async def create_kicc_order(pay_req: PayRequest):
    global latest_payment
    latest_payment["amount"] = pay_req.amount
    latest_payment["volume"] = pay_req.volume
    
    order_no = f"ORD_{uuid.uuid4().hex[:12].upper()}"
    
    payload = {
        "directRegInfo": {
            "mallId": MALL_ID,
            "regTxtype": "52",
            "regSubtype": "10",
            "amount": pay_req.amount,
            "currency": "00",
            "payCode": "00",
            "sndUrl": f"{BASE_URL}/pay-complete",
            "notiUrl": f"{BASE_URL}/api/kicc/webhook"
        },
        "directOrderInfo": {
            "shopOrderNo": order_no,
            "goodsName": f"EV_{pay_req.volume}",
            "goodsAmount": pay_req.amount
        }
    }

    try:
        response = requests.post(KICC_API_URL, json=payload, timeout=10)
        res_data = response.json()

        print("[KICC DirectReg Response]:", res_data)

        if res_data.get("resCd") == "0000":
            order_db[order_no] = {
                "status": "PENDING", 
                "amount": pay_req.amount,
                "volume": pay_req.volume
            }
            return {
                "success": True,
                "orderNo": order_no,
                "payUrl": res_data.get("authPageUrl")
            }
        else:
            return {
                "success": False, 
                "msg": f"[{res_data.get('resCd')}] {res_data.get('resMsg')}"
            }
    except Exception as e:
        return {"success": False, "msg": str(e)}

# ==================================================
# 3. KICC 결제 완료 랜딩 페이지 (모바일 화면용)
# ==================================================
@app.api_route("/pay-complete", methods=["GET", "POST"], response_class=HTMLResponse)
async def pay_complete():
    return """<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>결제 완료</title>
    <style>
        body { font-family: sans-serif; text-align: center; padding: 50px 20px; background: #f8f9fa; }
        .box { background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); max-width: 360px; margin: 0 auto; }
        h2 { color: #28a745; margin-bottom: 10px; }
        p { color: #666; font-size: 14px; }
    </style>
</head>
<body>
    <div class="box">
        <h2>✅ 결제 요청 완료</h2>
        <p>결제가 정상 처리되었습니다.<br>키오스크 화면을 확인해 주세요.</p>
    </div>
</body>
</html>"""

# ==================================================
# 4. KICC Webhook(노티) 수신 API (acquirerName 최우선 파싱)
# ==================================================
@app.post("/api/kicc/webhook")
async def kicc_webhook(request: Request):
    global latest_payment
    try:
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            data = await request.json()
        else:
            form_data = await request.form()
            data = dict(form_data)

        print("\n====== [KICC Webhook Received Data] ======")
        print(data)
        print("==========================================\n")

        # 대소문자 구분을 없애기 위한 소문자 정규화 딕셔너리
        lower_data = {str(k).lower(): v for k, v in data.items() if v}

        res_cd = lower_data.get("rescd") or lower_data.get("res_cd")
        shop_order_no = lower_data.get("shoporderno") or lower_data.get("shop_order_no")
        
        # acquirerName 최우선 추출 -> 없으면 대체 매입사명 필드 추출
        card_name = (
            lower_data.get("acquirername")       # acquirerName
            or lower_data.get("acquirer_name")
            or lower_data.get("cardmgbnm")       # cardMgbNm (매입사명)
            or lower_data.get("card_mgb_nm")
            or lower_data.get("cardpubnm")       # cardPubNm (발급사명)
            or lower_data.get("card_pub_nm")
            or lower_data.get("cardname")
            or lower_data.get("card_name")
            or lower_data.get("cardnm")
            or "신용카드"
        )
        
        card_no = (
            lower_data.get("cardno") 
            or lower_data.get("card_no") 
            or lower_data.get("cardnum") 
            or "****-****-****-****"
        )

        if res_cd == "0000":
            latest_payment["status"] = "SUCCESS"
            latest_payment["card_name"] = str(card_name)
            latest_payment["card_no"] = str(card_no)

            if shop_order_no and shop_order_no in order_db:
                order_db[shop_order_no]["status"] = "PAID"

        return PlainTextResponse("res_cd=0000&res_msg=SUCCESS")

    except Exception as e:
        print(f"[Webhook Error]: {e}")
        return PlainTextResponse("res_cd=0000&res_msg=SUCCESS")

# ==================================================
# 5. 상태 조회 및 리셋 API
# ==================================================
@app.get("/api/payment/status")
async def get_payment_status():
    return latest_payment

@app.post("/api/payment/reset")
async def reset_payment():
    global latest_payment
    latest_payment = {
        "status": "PENDING",
        "amount": 0,
        "volume": "",
        "card_name": "",
        "card_no": ""
    }
    return {"result": "ok"}
