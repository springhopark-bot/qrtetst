import json
import time
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

app = FastAPI(title="Kiosk Payment Service")

# --------------------------------------------------
# 🔑 KICC 가이드 문서 규격 설정 및 충전 단가 설정
# --------------------------------------------------
KICC_MID = "T2506894"  # 가맹점 MID
KICC_URL_PAY_REG_API = "https://testpgapi.easypay.co.kr/directapi/trades/directSmsUrlPayReg"
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

# 1. 키오스크 메인 UI
@app.get("/", response_class=HTMLResponse)
async def read_root():
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
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

    function selectOption(btn, volume, amount) {{
        document.querySelectorAll('.option-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        selectedVolume = volume;
        selectedAmount = amount;
    }}

    async function startPayment() {{
        await fetch('/api/payment/reset', {{ method: 'POST' }});
        
        try {{
            const response = await fetch('/api/kicc/create-order', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ amount: selectedAmount, volume: selectedVolume }})
            }});
            const data = await response.json();

            if (data.pay_url) {{
                const qrData = encodeURIComponent(data.pay_url);
                document.getElementById('qrImage').src = `https://api.qrserver.com/v1/create-qr-code/?size=220x220&data=${{qrData}}`;
                
                document.getElementById('statusBox').style.display = 'block';
                document.getElementById('resultBox').style.display = 'none';
                document.getElementById('payStartBtn').style.display = 'none';
                
                if(pollInterval) clearInterval(pollInterval);
                pollInterval = setInterval(checkPaymentStatus, 1000);
            }} else {{
                alert("KICC 결제 URL 생성 실패: " + (data.msg || "응답 오류"));
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
                clearInterval(pollInterval);
                document.getElementById('statusBox').style.display = 'none';
                showSuccessUI(data);
            }}
        }} catch (e) {{
            console.error("상태 확인 오류:", e);
        }}
    }}

    function showSuccessUI(data) {{
        document.getElementById('cardName').innerText = data.card_name || "신용카드";
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

# 2. KICC 결제 등록 API
@app.post("/api/kicc/create-order")
async def create_kicc_order(pay_req: PayRequest):
    global latest_payment
    latest_payment["amount"] = pay_req.amount
    latest_payment["volume"] = pay_req.volume
    
    order_no = f"ORD{int(time.time())}"
    order_db[order_no] = {
        "amount": pay_req.amount,
        "volume": pay_req.volume,
        "status": "PENDING"
    }

    payload = {
        "mall_id": KICC_MID,
        "shop_order_no": order_no,
        "amount": str(pay_req.amount),
        "goods_name": f"전기차 충전 {pay_req.volume}",
        "pay_method": "11",
        "msg_type": "URL",
        "char_set": "UTF-8",
        "currency": "00",
        "noti_url": f"{BASE_URL}/api/kicc/webhook",
        "return_url": f"{BASE_URL}/pay-complete",
        "trans_type": "00"
    }

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(KICC_URL_PAY_REG_API, json=payload, headers=headers)
            res_data = response.json()

            pay_url = res_data.get("auth_pay_url") or res_data.get("pay_url") or res_data.get("authPayUrl") or res_data.get("res_data", {}).get("auth_pay_url")

            if pay_url:
                return {"result": "SUCCESS", "pay_url": pay_url}
            else:
                res_cd = res_data.get("res_cd") or res_data.get("resCd") or "FAIL"
                res_msg = res_data.get("res_msg") or res_data.get("resMsg") or "URL 생성 오류"
                return {"result": "FAIL", "msg": f"[{res_cd}] {res_msg}"}

    except Exception as e:
        return {"result": "FAIL", "msg": str(e)}

# 3. KICC 결제 완료 랜딩
@app.all("/pay-complete", response_class=HTMLResponse)
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

# 4. KICC Webhook(노티) 수신 - 카드 이름/번호 추출 보완
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

        print("\n📥 === [KICC 웹훅 수신] ===")
        print(json.dumps(data, indent=2, ensure_ascii=False))

        res_cd = data.get("resCd") or data.get("res_cd")
        shop_order_no = data.get("shopOrderNo") or data.get("shop_order_no")
        
        # KICC 파라미터 규격별 카드 정보 동적 매핑
        card_name = data.get("card_name") or data.get("cardName") or data.get("card_nm") or "신용카드"
        card_no = data.get("card_no") or data.get("cardNo") or data.get("card_num") or "****-****-****-****"

        if res_cd == "0000":
            latest_payment["status"] = "SUCCESS"
            latest_payment["card_name"] = card_name
            latest_payment["card_no"] = card_no

            if shop_order_no and shop_order_no in order_db:
                order_db[shop_order_no]["status"] = "PAID"

        return PlainTextResponse("res_cd=0000&res_msg=SUCCESS")

    except Exception as e:
        print(f"❌ [웹훅 에러]: {e}")
        return PlainTextResponse("res_cd=0000&res_msg=SUCCESS")

# 5. 상태 조회 및 리셋 API
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
