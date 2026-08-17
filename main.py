from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse

app = FastAPI(title="Kiosk Payment Service")

# 결제 상태 보관용 메모리
latest_payment = {
    "status": "PENDING",
    "amount": 0,
    "volume": "",
    "card_name": "",
    "card_no": ""
}

# 1. 키오스크 메인 웹 화면 (QR 생성 로직 추가)
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
        
        /* QR 및 결제 진행 박스 */
        .status-box { display: none; margin-top: 25px; padding: 20px; border-radius: 12px; background: #f8f9fa; border: 1px solid #e9ecef; }
        .qr-img { width: 200px; height: 200px; margin: 15px auto; border: 4px solid #fff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        .spinner { border: 4px solid #f3f3f3; border-top: 4px solid #007bff; border-radius: 50%; width: 24px; height: 24px; animation: spin 1s linear infinite; display: inline-block; vertical-align: middle; margin-right: 8px; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }

        /* 결제 완료 레이어 */
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
        <h4 style="margin:0; color:#333;">스마트폰 앱카드로 스캔하세요</h4>
        <img id="qrImage" class="qr-img" src="" alt="결제 QR코드">
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
        
        // 시연용 QR 코드 생성 (실제 KICC 연동 시 KICC에서 받은 QR URL을 넣으면 됩니다)
        const qrData = encodeURIComponent(`KICC_PAYMENT_URL?amount=${selectedAmount}&volume=${selectedVolume}`);
        document.getElementById('qrImage').src = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${qrData}`;
        
        document.getElementById('statusBox').style.display = 'block';
        document.getElementById('resultBox').style.display = 'none';
        document.getElementById('payStartBtn').style.display = 'none';
        
        // 1초마다 백엔드 결제 상태 체크
        pollInterval = setInterval(checkPaymentStatus, 1000);
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

# 2. KICC 결제 노티(웹훅) 수신
