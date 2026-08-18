import uuid
import requests
from urllib.parse import parse_qs
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

app = FastAPI(title="Kiosk Payment Service")

# --------------------------------------------------
# 🔑 KICC 설정 및 충전 단가 (기존 코드 유지)
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

# --------------------------------------------------
# 🛠️ 카드 정보 및 발급사명 파싱 함수 (기존 코드 유지)
# --------------------------------------------------
def parse_payment_data(data: dict):
    lower_data = {str(k).lower(): str(v).strip() for k, v in data.items() if v}
    
    card_name = (
        lower_data.get("issuername")
        or lower_data.get("issuer_name")
        or lower_data.get("cardpubnm")
        or lower_data.get("card_pub_nm")
        or lower_data.get("cardmgbnm")
        or lower_data.get("card_mgb_nm")
        or lower_data.get("acquirername")
        or lower_data.get("acquirer_name")
        or lower_data.get("cardname")
        or lower_data.get("card_name")
        or lower_data.get("cardnm")
    )

    if not card_name:
        fn_cd = lower_data.get("fn_cd") or lower_data.get("card_code") or lower_data.get("fn_code")
        card_code_map = {
            "01": "비씨카드", "02": "국민카드", "03": "하나카드",
            "04": "삼성카드", "06": "신한카드", "07": "현대카드",
            "08": "롯데카드", "11": "농협카드", "12": "수협카드"
        }
        card_name = card_code_map.get(fn_cd, "신용카드")

    card_no = (
        lower_data.get("cardno") 
        or lower_data.get("card_no") 
        or lower_data.get("cardnum") 
        or "****-****-****-****"
    )

    res_cd = lower_data.get("rescd") or lower_data.get("res_cd")
    shop_order_no = lower_data.get("shoporderno") or lower_data.get("shop_order_no")

    return shop_order_no, res_cd, card_name, card_no

# ==================================================
# 1. 키오스크 메인 UI (충전 중 및 부분취소 화면 추가)
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
        body {{ font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; text-align: center; padding: 40px 20px; background: #f0f2f5; margin: 0; }}
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

        /* 충전 중 화면 스타일 */
        .charging-box {{ display: none; background: #f0f8ff; border: 2px solid #007bff; border-radius: 12px; padding: 25px 20px; margin-top: 25px; }}
        .charging-stats {{ background: white; padding: 15px; border-radius: 8px; border: 1px solid #b8daff; text-align: left; margin: 15px 0; line-height: 1.8; }}
        .charging-stats p {{ margin: 6px 0; display: flex; justify-content: space-between; font-size: 15px; }}
        .charging-stats span.value {{ font-weight: 700; color: #007bff; }}
        .stop-btn {{ width: 100%; padding: 15px; background: #dc3545; color: white; font-size: 17px; font-weight: 700; border: none; border-radius: 10px; cursor: pointer; margin-top: 10px; box-shadow: 0 4px 10px rgba(220,53,69,0.3); }}
        .stop-btn:hover {{ background: #c82333; }}

        /* 충전 중지 / 부분취소 안내 화면 스타일 */
        .refund-box {{ display: none; background: #fff3cd; border: 2px solid #ffc107; border-radius: 12px; padding: 25px 20px; margin-top: 25px; }}
        .refund-stats {{ background: white; padding: 15px; border-radius: 8px; border: 1px solid #ffeeba; text-align: left; margin: 15px 0; line-height: 1.8; }}
        .refund-stats p {{ margin: 6px 0; display: flex; justify-content: space-between; font-size: 15px; }}
        .refund-stats span.value {{ font-weight: 700; color: #333; }}
        .refund-stats span.cancel-val {{ font-weight: 700; color: #dc3545; font-size: 17px; }}
        .refund-timer {{ font-size: 14px; color: #666; margin-top: 12px; }}
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

    <!-- QR 스캔 대기 화면 -->
    <div id="statusBox" class="status-box">
        <h4 style="margin:0; color:#333;">스마트폰 카메라로 QR을 스캔하세요</h4>
        <img id="qrImage" class="qr-img" src="" alt="KICC 결제 QR코드">
        <p style="margin: 8px 0 0 0; font-size: 14px; color: #495057; font-weight: 600;">
            <span class="spinner"></span>KICC 결제 승인 확인 중...
        </p>
        <div class="qr-timer">⏱️ <span id="qrCountdown">120</span>초 내에 결제를 완료해 주세요</div>
    </div>

    <!-- 🔌 실시간 충전 중 화면 -->
    <div id="chargingBox" class="charging-box">
        <h3 id="chargingTitle" style="color: #007bff; margin: 0 0 10px 0;">⚡ 전기차 충전 중...</h3>
        <div class="charging-stats">
            <p><span>결제 카드 (발급사)</span><span id="chgCardName" class="value">-</span></p>
            <p><span>선결제 금액</span><span id="chgInitialAmount" class="value">-</span></p>
            <p><span>목표 충전량</span><span id="chgTargetKwh" class="value">-</span></p>
            <p><span>현재 충전량</span><span id="currentKwh" class="value">0.0 kWh</span></p>
            <p><span>현재 충전 요금</span><span id="currentCost" class="value">0원</span></p>
            <p><span>경과 시간</span><span id="chargingTime" class="value">0초</span></p>
        </div>
        <button class="stop-btn" onclick="stopCharging(false)">🛑 충전 중지</button>
    </div>

    <!-- 🛑 충전 중지 / 부분취소 안내 화면 (10초 노출) -->
    <div id="refundBox" class="refund-box">
        <h3 id="refundTitle" style="color: #856404; margin: 0 0 10px 0;">🛑 충전이 중지되었습니다</h3>
        <div class="refund-stats">
            <p><span>선결제 금액</span><span id="refInitialAmount" class="value">-</span></p>
            <p><span>실제 충전량</span><span id="refKwh" class="value">-</span></p>
            <p><span>실제 충전 요금</span><span id="refUsedCost" class="value">-</span></p>
            <p><span>부분취소(환불) 예정 금액</span><span id="refCancelAmount" class="cancel-val">-</span></p>
        </div>
        <div class="refund-timer"><span id="refundCountdown" class="timer-num">10</span>초 후 초기 화면으로 이동합니다.</div>
    </div>
</div>

<script>
    const UNIT_PRICE = {UNIT_PRICE};
    let selectedVolume = "20kWh";
    let selectedAmount = {20 * UNIT_PRICE};
    let pollInterval = null;
    let qrTimeoutTimer = null;
    let chargingInterval = null;
    let refundTimer = null;
    let qrLeftSeconds = 60;

    let currentKwh = 0.0;
    let elapsedSeconds = 0;
    let maxKwh = 20;
    let cardInfoName = "-";

    function selectOption(btn, volume, amount) {{
        document.querySelectorAll('.option-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        selectedVolume = volume;
        selectedAmount = amount;
    }}

    function resetAllTimers() {{
        if (pollInterval) clearInterval(pollInterval);
        if (qrTimeoutTimer) clearInterval(qrTimeoutTimer);
        if (chargingInterval) clearInterval(chargingInterval);
        if (refundTimer) clearInterval(refundTimer);
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
                document.getElementById('chargingBox').style.display = 'none';
                document.getElementById('refundBox').style.display = 'none';
                document.getElementById('payStartBtn').style.display = 'none';
                
                qrLeftSeconds = 120;
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
                cardInfoName = (data.card_name && data.card_name.trim() !== "") ? data.card_name : "신용카드";
                startChargingSimulation(selectedVolume, selectedAmount);
            }}
        }} catch (e) {{
            console.error("상태 확인 오류:", e);
        }}
    }}

    // ⚡ 1초당 0.1 kWh씩 충전되는 시뮬레이션 시작
    function startChargingSimulation(volumeStr, paidAmount) {{
        maxKwh = parseFloat(volumeStr.replace('kWh', ''));
        currentKwh = 0.0;
        elapsedSeconds = 0;

        document.getElementById('chgCardName').innerText = cardInfoName;
        document.getElementById('chgInitialAmount').innerText = paidAmount.toLocaleString() + "원";
        document.getElementById('chgTargetKwh').innerText = volumeStr;
        
        document.getElementById('chargingBox').style.display = 'block';

        chargingInterval = setInterval(() => {{
            elapsedSeconds++;
            // 1초당 0.1 kWh 증가
            currentKwh = parseFloat((currentKwh + 0.1).toFixed(1));
            let currentCost = Math.round(currentKwh * UNIT_PRICE);

            document.getElementById('currentKwh').innerText = currentKwh.toFixed(1) + " kWh";
            document.getElementById('currentCost').innerText = currentCost.toLocaleString() + "원";
            document.getElementById('chargingTime').innerText = elapsedSeconds + "초";

            // 목표 충전량(예: 20kWh)에 도달하면 자동 완료 처리
            if (currentKwh >= maxKwh) {{
                currentKwh = maxKwh;
                stopCharging(true);
            }}
        }}, 1000);
    }}

    // 🛑 충전 중지 버튼 클릭 또는 목표 달성 시 호출
    function stopCharging(isCompleted = false) {{
        if (chargingInterval) clearInterval(chargingInterval);

        document.getElementById('chargingBox').style.display = 'none';
        document.getElementById('refundBox').style.display = 'block';

        let initialAmount = selectedAmount; // 선결제 금액
        let usedCost = Math.round(currentKwh * UNIT_PRICE); // 실제 충전 요금
        let cancelAmount = initialAmount - usedCost;       // 부분취소(환불) 금액
        if (cancelAmount < 0) cancelAmount = 0;

        document.getElementById('refInitialAmount').innerText = initialAmount.toLocaleString() + "원";
        document.getElementById('refKwh').innerText = currentKwh.toFixed(1) + " kWh";
        document.getElementById('refUsedCost').innerText = usedCost.toLocaleString() + "원";
        document.getElementById('refCancelAmount').innerText = cancelAmount.toLocaleString() + "원";

        if (isCompleted) {{
            document.getElementById('refundTitle').innerText = "✅ 목표 충전량이 완료되었습니다!";
        }} else {{
            document.getElementById('refundTitle').innerText = "🛑 충전이 중지되었습니다 (부분취소 안내)";
        }}

        // 10초 동안 부분취소 안내 화면 유지 후 리셋
        let refundSec = 10;
        document.getElementById('refundCountdown').innerText = refundSec;
        
        refundTimer = setInterval(() => {{
            refundSec--;
            document.getElementById('refundCountdown').innerText = refundSec;

            if (refundSec <= 0) {{
                clearInterval(refundTimer);
                location.reload();
            }}
        }}, 1000);
    }}
</script>

</body>
</html>"""
    return HTMLResponse(content=content, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

# ==================================================
# 2. KICC 결제 URL 생성 API (기존 코드 유지)
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
            "payCode": "11",
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
# 3. KICC 결제 완료 랜딩 페이지 (기존 코드 유지)
# ==================================================
@app.api_route("/pay-complete", methods=["GET", "POST"], response_class=HTMLResponse)
async def pay_complete(request: Request):
    global latest_payment
    try:
        params = dict(request.query_params)

        if request.method == "POST":
            try:
                raw_body = await request.body()
                body_str = raw_body.decode("utf-8", errors="ignore")
                parsed = parse_qs(body_str)
                for k, v in parsed.items():
                    if v:
                        params[k] = v[0]
            except Exception as pe:
                print(f"[sndUrl Body Parse Error]: {pe}")

        print("\n====== [sndUrl /pay-complete Received Data] ======")
        print(params)
        print("==================================================\n")

        shop_order_no, res_cd, card_name, card_no = parse_payment_data(params)

        latest_payment["status"] = "SUCCESS"
        if card_name:
            latest_payment["card_name"] = str(card_name)
        if card_no:
            latest_payment["card_no"] = str(card_no)

        if shop_order_no and shop_order_no in order_db:
            order_db[shop_order_no]["status"] = "PAID"

    except Exception as e:
        print(f"[pay-complete handling error]: {e}")

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
# 4. KICC Webhook(노티) 수신 API (JSON 응답 규격 적용)
# ==================================================
@app.post("/api/kicc/webhook")
async def kicc_webhook(request: Request):
    global latest_payment
    try:
        content_type = request.headers.get("content-type", "")
        data = {}
        
        # 1. Body 파싱 (JSON 또는 Form 데이터)
        if "application/json" in content_type:
            data = await request.json()
        else:
            raw_body = await request.body()
            body_str = raw_body.decode("utf-8", errors="ignore")
            parsed = parse_qs(body_str)
            data = {k: v[0] for k, v in parsed.items() if v}

        print("\n====== [KICC Webhook Received Data] ======")
        print(data)
        print("==========================================\n")

        # 2. 결제 정보 검증
        shop_order_no, res_cd, card_name, card_no = parse_payment_data(data)

        # 3. res_cd가 '0000'(정상 결제 승인)일 때만 SUCCESS 처리
        if res_cd == "0000":
            latest_payment["status"] = "SUCCESS"
            latest_payment["card_name"] = str(card_name)
            latest_payment["card_no"] = str(card_no)

            if shop_order_no and shop_order_no in order_db:
                order_db[shop_order_no]["status"] = "PAID"
            print(f"✅ [KICC Webhook 성공] 주문번호: {shop_order_no}, 카드사: {card_name}")
            
            # KICC 규격에 맞춘 성공 JSON 응답
            return JSONResponse(
                content={"resCd": "0000", "resMsg": "정상"},
                status_code=200
            )
        else:
            print(f"⚠️ [KICC Webhook 결제실패/취소건] res_cd: {res_cd}")
            # 결제 성공 건이 아닌 경우 실패 응답 전달
            return JSONResponse(
                content={"resCd": "5001", "resMsg": "처리실패"},
                status_code=200
            )

    except Exception as e:
        print(f"❌ [Webhook Processing Error]: {e}")
        # 예외 발생 시 실패 JSON 응답 반환
        return JSONResponse(
            content={"resCd": "5001", "resMsg": "처리실패"},
            status_code=200
        )

# ==================================================
# 5. 상태 조회 및 리셋 API (기존 코드 유지)
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
