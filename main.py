import json
import time
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

app = FastAPI(title="Kiosk Payment Service")

# 메모리 데이터베이스 및 상태 관리
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

# 1. 키오스크 메인 웹 화면
@app.get("/", response_class=HTMLResponse)
async def read_root():
    return """<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>키오스크 충전 결제 서비스</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; text-align: center; padding: 40px 20px; background: #f0f2f5; margin: 0; }
        .card { max-width: 480px; margin: 0 auto; background: white; padding: 35px 25px; border-radius: 16px; box-shadow: 0 8px 24px rgba(0,0,0,0.08); }
        h2 { margin-top: 0; color: #1a1a1a; font-size: 24px; font-weight: 700; }
        .sub-text { color: #666; font-size: 15px; margin-bottom: 25px; }
        
        .btn-group { display: flex; gap: 12px; justify-content: center; margin-bottom: 12px; }
        .option-btn { flex: 1; padding: 16px 10px; border: 2px solid #e1e4e8; background: #fff; border-radius: 12px; cursor: pointer; font-weight: 600; font-size: 15px; color: #444; transition: all 0.2s ease; }
        .option-btn:hover { border-color: #007bff; color: #007bff; }
        .option-btn.active { background: #007bff; color: white; border-color: #007bff; box-shadow: 0 4px 12px rgba(0,123,255,0.3); }
        .price-text { font-size: 13px; opacity: 0.85; margin-top: 4px; font-weight: 400; }
        
        .notice-text { font-size: 12.5px; color: #888; margin-bottom: 24px; text-align: center; word-break: keep-all; line-height: 1.4; background: #f8f9fa; padding: 8px 12px; border-radius: 6px; }
        
        .pay-btn { width: 100%; padding: 18px; background: #28a745; color: white; font-size: 18px; font-weight: 700; border: none; border-radius: 12px; cursor: pointer; transition: background 0.2s ease; box-shadow: 0 4px 12px rgba(40,167,69,0.3); }
        .pay-btn:hover { background: #218838; }
        
        .status-box { display: none; margin-top: 25px; padding: 20px; border-radius: 12px; background: #f8f9fa; border: 1px solid #e9ecef; }
        .qr-img { width: 220px; height: 220px; margin: 15px auto; border: 4px solid #fff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); display: block; }
        .spinner { border: 4px solid #f3f3f3; border-top: 4px solid #007bff; border-radius: 50%; width: 24px; height: 24px; animation: spin 1s linear infinite; display: inline-block; vertical-align: middle; margin-right: 8px; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }

        .result-box { display: none; background: #f0fff4; border: 2px solid #28a745; border-radius: 12px; padding: 25px 20px; margin-top: 25px; animation: fadeIn 0.3s ease-in-out; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .result-box h3 { color: #28a745; margin: 0 0 15px 0; font-size: 20px; }
        .card-info { font-size: 15px; color: #333; margin: 15px 0; background: white; padding: 15px; border-radius: 8px; border: 1px solid #d4edda; text-align: left; line-height: 1.8; }
        .card-info p { margin: 4px 0; display: flex; justify-content: space-between; }
        .card-info span.value { font-weight: 600; color: #1a1a1a; }
        .charging-msg { font-size: 20px; font-weight: 700; color: #007bff; margin-top: 20px; letter-spacing: -0.5px; }
        .timer { font-size: 14px; color: #666; margin-top: 8px; }
        .timer-num { font-weight: bold; color: #dc3545; font-size: 16px; }
    </style>
</head>
<body>

<div class="card">
    <h2>⚡ 충전량 및 금액 선택</h2>
    <p class="sub-text">원하시는 충전 옵션을 선택한 후 결제를 진행해 주세요.</p>
    
    <div class="btn-group">
        <button class="option-btn active" onclick="selectOption(this, '20kWh', 10000)">
            20 kWh
            <div class="price-text">10,000원</div>
        </button>
        <button class="option-btn" onclick="selectOption(this, '40kWh', 20000)">
            40 kWh
            <div class="price-text">20,000원</div>
        </button>
        <button class="option-btn" onclick="selectOption(this, '60kWh', 30000)">
            60 kWh
            <div class="price-text">30,000원</div>
        </button>
    </div>

    <div class="notice-text">
        💡 목표 충전량에 도달하지 않은 경우, 남은 충전금액은 부분취소 됩니다.
    </div>

    <button id="payStartBtn" class="pay-btn" onclick="startPayment()">결제 및 충전 시작</button>

    <div id="statusBox" class="status-box">
        <h4 style="margin:0; color:#333;">스마트폰 카메라인 앱카드로 스캔하세요</h4>
        <img id="qrImage" class="qr-img" src="" alt="KICC 결제 QR코드">
        <p style="margin: 5px 0 0 0; font-size: 14px; color: #495057; font-weight: 600;">
            <span class="spinner"></span>KICC 결제 승인 수신 대기 중...
        </p>
    </div>

    <div id="resultBox" class="result-box">
        <h3>✅ 결제가 완료되었습니다!</h3>
        <div class="card-info">
            <p><span>결제 카드</span><span id="cardName" class="value">-</span></p>
            <p><span>카드 번호</span><span id="cardNo" class="value">-</span></p>
            <p><span>선택 충전량</span><span id="payVolume" class="value">-</span></p>
            <p><span>결제 금액</span><span id="payAmount" class="value">-</span></p>
        </div>
        <div class="charging-msg">🔌 5초 후 충전을 시작합니다...</div>
        <div class="timer"><span id="countdown" class="timer-num">5</span>초 후 화면이 자동으로 전환됩니다.</div>
    </div>
</div>

<script>
    let selectedVolume = "20kWh";
    let selectedAmount = 10000;
    let pollInterval = null;

    function selectOption(btn, volume, amount) {
        document.querySelectorAll('.option-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        selectedVolume = volume;
        selectedAmount = amount;
    }

    async function startPayment() {
        await fetch('/api/payment/reset', { method: 'POST' });
        
        try {
            const response = await fetch('/api/kicc/create-order', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ amount: selectedAmount, volume: selectedVolume })
            });
            const data = await response.json();

            if (data.pay_url) {
                const qrData = encodeURIComponent(data.pay_url);
                document.getElementById('qrImage').src = `https://api.qrserver.com/v1/create-qr-code/?size=220x220&data=${qrData}`;
                
                document.getElementById('statusBox').style.display = 'block';
                document.getElementById('resultBox').style.display = 'none';
                document.getElementById('payStartBtn').style.display = 'none';
                
                if(pollInterval) clearInterval(pollInterval);
                pollInterval = setInterval(checkPaymentStatus, 1000);
            }
        } catch (e) {
            alert("서버 연결 실패: " + e.message);
        }
    }

    async function checkPaymentStatus() {
        try {
            const res = await fetch('/api/payment/status');
            const data = await res.json();

            if (data.status === "SUCCESS") {
                clearInterval(pollInterval);
                document.getElementById('statusBox').style.display = 'none';
                showSuccessUI(data);
            }
        } catch (e) {
            console.error("상태 확인 실패:", e);
        }
    }

    function showSuccessUI(data) {
        document.getElementById('cardName').innerText = data.card_name || "신한카드";
        document.getElementById('cardNo').innerText = data.card_no || "4330-****-****-1234";
        document.getElementById('payAmount').innerText = selectedAmount.toLocaleString() + "원";
        document.getElementById('payVolume').innerText = selectedVolume;

        document.getElementById('resultBox').style.display = 'block';

        let seconds = 5;
        const countElem = document.getElementById('countdown');

        const timer = setInterval(() => {
            seconds--;
            countElem.innerText = seconds;

            if (seconds <= 0) {
                clearInterval(timer);
                alert("⚡ 충전이 시작되었습니다!");
                location.reload();
            }
        }, 1000);
    }
</script>

</body>
</html>"""

# 2. 주문 번호 생성 및 랜딩 페이지 URL 반환
@app.post("/api/kicc/create-order")
async def create_kicc_order(pay_req: PayRequest, request: Request):
    global latest_payment
    latest_payment["amount"] = pay_req.amount
    latest_payment["volume"] = pay_req.volume
    
    host_url = str(request.base_url).rstrip('/')
    order_no = f"ORD{int(time.time())}"
    
    order_db[order_no] = {
        "amount": pay_req.amount,
        "volume": pay_req.volume,
        "status": "PENDING"
    }

    # QR스캔 전용 랜딩 URL 지정 (/pay-landing)
    target_pay_url = f"{host_url}/pay-landing?order_no={order_no}&amount={pay_req.amount}&volume={pay_req.volume}"

    return {"result": "SUCCESS", "pay_url": target_pay_url}

# 3. 모바일 전용 결제 페이지 (/pay-landing)
@app.get("/pay-landing", response_class=HTMLResponse)
async def pay_landing_page(order_no: str, amount: int, volume: str, request: Request):
    base_url = str(request.base_url).rstrip('/')
    noti_url = f"{base_url}/api/kicc/webhook"

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>KICC 카드 결제 창</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f4f6f8; margin:0; padding:20px; text-align: center; }}
        .box {{ background: white; border-radius: 16px; padding: 25px 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.08); max-width: 360px; margin: 30px auto 0 auto; }}
        h3 {{ color: #007bff; margin-top: 0; }}
        .btn {{ width: 100%; padding: 16px; background: #28a745; color: white; border: none; border-radius: 10px; font-weight: bold; font-size: 16px; margin-top: 20px; cursor: pointer; }}
        .info {{ text-align: left; background: #f8f9fa; padding: 12px 15px; border-radius: 8px; margin: 15px 0; font-size: 14px; line-height: 1.6; color: #333; }}
    </style>
</head>
<body>
    <div class="box">
        <h3>💳 KICC EasyPay 결제</h3>
        <div class="info">
            <p style="margin:4px 0;"><b>주문번호:</b> {order_no}</p>
            <p style="margin:4px 0;"><b>충전 옵션:</b> {volume}</p>
            <p style="margin:4px 0;"><b>결제 금액:</b> {amount:,}원</p>
        </div>
        <button class="btn" onclick="sendApproval()">카드 결제 승인 요청</button>
    </div>

    <script>
        async function sendApproval() {{
            const formData = new FormData();
            formData.append("res_cd", "0000");
            formData.append("shop_order_no", "{order_no}");
            formData.append("card_name", "신한카드");
            formData.append("card_no", "4330-****-****-1234");

            try {{
                await fetch('{noti_url}', {{ method: 'POST', body: formData }});
                alert("✅ 결제 승인이 완료되었습니다!");
                document.body.innerHTML = "<h2 style='margin-top:50px; color:#28a745;'>✅ 결제가 정상 처리되었습니다.<br><small style='font-size:14px; color:#666;'>키오스크 화면을 확인해 주세요.</small></h2>";
            }} catch(e) {{
                alert("결제 전송 실패: " + e);
            }}
        }}
    </script>
</body>
</html>"""

# 4. KICC 웹훅 수신 (저번주 검증 코드 유지)
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

        print("\n📥 === [KICC 웹훅 데이터 수신] ===")
        print(json.dumps(data, indent=2, ensure_ascii=False))

        res_cd = data.get("resCd") or data.get("res_cd")
        shop_order_no = data.get("shopOrderNo") or data.get("shop_order_no") or data.get("order_no")
        card_name = data.get("card_name") or data.get("cardName") or "신한카드"
        card_no = data.get("card_no") or data.get("cardNo") or "4330-****-****-1234"

        if res_cd == "0000":
            latest_payment["status"] = "SUCCESS"
            latest_payment["card_name"] = card_name
            latest_payment["card_no"] = card_no
            
            if shop_order_no and shop_order_no in order_db:
                order_db[shop_order_no]["status"] = "PAID"

        return PlainTextResponse("res_cd=0000&res_msg=SUCCESS")

    except Exception as e:
        print(f"❌ 웹훅 에러: {e}")
        return PlainTextResponse("res_cd=0000&res_msg=SUCCESS")

# 5. 프론트엔드 결제 확인
@app.get("/api/payment/status")
async def get_payment_status():
    return latest_payment

# 6. 결제 리셋
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
