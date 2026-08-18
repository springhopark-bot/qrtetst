from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
import requests
import json
import uuid

app = FastAPI()

# KICC API 도메인 및 상점 정보 설정
KICC_API_URL = "https://testpgapi.easypay.co.kr/directapi/trades/directSmsUrlPayReg"
MALL_ID = "T0022488"

# 키오스크 주문 상태 저장소 (메모리 저장 방식)
order_db = {}


# 1. 메인 웹 화면 (HTML/JS)
@app.get("/", response_class=HTMLResponse)
def kiosk_ui():
    return """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>키오스크 QR 결제</title>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
        <style>
            body { font-family: 'Noto Sans KR', sans-serif; text-align: center; padding: 50px; background: #f0f2f5; }
            .card { background: white; padding: 40px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.1); display: inline-block; width: 360px; }
            h2 { margin-bottom: 20px; color: #333; }
            button { width: 100%; padding: 16px; font-size: 20px; font-weight: bold; background: #007bff; color: white; border: none; border-radius: 12px; cursor: pointer; transition: 0.2s; }
            button:hover { background: #0056b3; }
            #qr-area { margin-top: 30px; display: none; }
            #qrcode { margin: 20px auto; display: flex; justify-content: center; }
            .status-msg { color: #666; font-size: 14px; animation: blink 1.5s infinite; }
            @keyframes blink { 50% { opacity: 0.5; } }
            .success-msg { color: #28a745; font-size: 24px; font-weight: bold; margin-top: 20px; }
        </style>
    </head>
    <body>

    <div class="card" id="kiosk-card">
        <h2>⚡ 전기차 충전료 (1,004원)</h2>
        <button onclick="startPayment()">결제하기</button>

        <div id="qr-area">
            <h3>스마트폰으로 QR을 스캔하세요</h3>
            <div id="qrcode"></div>
            <p id="order-no-text" style="font-size: 13px; color: #888;"></p>
            <p class="status-msg">💳 결제 진행 대기 중...</p>
        </div>
    </div>

    <script>
    let pollTimer = null;

    async function startPayment() {
        document.querySelector('button').style.display = 'none'; // 버튼 숨김
        
        // 1. 서버에 QR 결제 링크 생성 요청
        const res = await fetch('/api/create-qr', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ amount: 1004, goods_name: '전기차 충전료' })
        });
        const data = await res.json();

        if (data.success) {
            document.getElementById('qr-area').style.display = 'block';
            document.getElementById('order-no-text').innerText = `주문번호: ${data.orderNo}`;

            // QR코드 그려주기
            document.getElementById('qrcode').innerHTML = "";
            new QRCode(document.getElementById("qrcode"), {
                text: data.payUrl,
                width: 220,
                height: 220
            });

            // 2. 결제 완료 상태 주기적 감지 (1.5초 간격 Polling)
            checkOrderStatus(data.orderNo);
        } else {
            alert('QR 결제 생성 실패: ' + data.msg);
            location.reload();
        }
    }

    function checkOrderStatus(orderNo) {
        if (pollTimer) clearInterval(pollTimer);

        pollTimer = setInterval(async () => {
            const res = await fetch(`/api/order-status/${orderNo}`);
            const data = await res.json();

            // KICC 노티를 수신해서 상태가 'PAID'로 바뀌었으면!
            if (data.status === 'PAID') {
                clearInterval(pollTimer);
                showSuccessScreen();
            }
        }, 1500);
    }

    function showSuccessScreen() {
        document.getElementById('kiosk-card').innerHTML = `
            <div class="success-msg">🎉 결제가 완료되었습니다!</div>
            <p style="margin-top: 15px; color: #555;">충전을 시작합니다.</p>
            <p style="font-size: 12px; color: #aaa; margin-top: 30px;">3초 후 첫 화면으로 돌아갑니다...</p>
        `;
        
        setTimeout(() => {
            location.reload();
        }, 3000);
    }
    </script>

    </body>
    </html>
    """


# 2. KICC 결제 URL 생성 요청 API
@app.post("/api/create-qr")
async def create_qr(request: Request):
    body = await request.json()
    amount = body.get("amount", 1004)
    goods_name = body.get("goods_name", "전기차 충전료")
    
    # 고유 주문번호 생성
    order_no = f"ORD_{uuid.uuid4().hex[:12].upper()}"

    payload = {
        "directRegInfo": {
            "mallId": MALL_ID,      # ★ 수정 완료: 문자열 변수로 지정
            "regTxtype": "52",       # 52: 결제 URL 생성요청
            "regSubtype": "10",      # 10: 신규등록
            "amount": amount,
            "currency": "00",
            "payCode": "00"
        },
        "directOrderInfo": {
            "shopOrderNo": order_no,
            "goodsName": goods_name,
            "goodsAmount": amount
        }
    }

    try:
        response = requests.post(KICC_API_URL, json=payload, timeout=10)
        res_data = response.json()

        if res_data.get("resCd") == "0000":
            # 메모리에 주문 대기 상태 저장
            order_db[order_no] = {"status": "PENDING", "amount": amount}
            return {
                "success": True,
                "orderNo": order_no,
                "payUrl": res_data.get("authPageUrl")
            }
        else:
            return {"success": False, "msg": res_data.get("resMsg")}
    except Exception as e:
        return {"success": False, "msg": str(e)}


from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
import requests
import json
import uuid

app = FastAPI()

# KICC API 도메인 및 상점 정보 설정
KICC_API_URL = "https://testpgapi.easypay.co.kr/directapi/trades/directSmsUrlPayReg"
MALL_ID = "T0022488"

# 키오스크 주문 상태 저장소 (메모리 저장 방식)
order_db = {}


# 1. 메인 웹 화면 (HTML/JS)
@app.get("/", response_class=HTMLResponse)
def kiosk_ui():
    return """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>키오스크 QR 결제</title>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
        <style>
            body { font-family: 'Noto Sans KR', sans-serif; text-align: center; padding: 50px; background: #f0f2f5; }
            .card { background: white; padding: 40px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.1); display: inline-block; width: 360px; }
            h2 { margin-bottom: 20px; color: #333; }
            button { width: 100%; padding: 16px; font-size: 20px; font-weight: bold; background: #007bff; color: white; border: none; border-radius: 12px; cursor: pointer; transition: 0.2s; }
            button:hover { background: #0056b3; }
            #qr-area { margin-top: 30px; display: none; }
            #qrcode { margin: 20px auto; display: flex; justify-content: center; }
            .status-msg { color: #666; font-size: 14px; animation: blink 1.5s infinite; }
            @keyframes blink { 50% { opacity: 0.5; } }
            .success-msg { color: #28a745; font-size: 24px; font-weight: bold; margin-top: 20px; }
        </style>
    </head>
    <body>

    <div class="card" id="kiosk-card">
        <h2>⚡ 전기차 충전료 (1,004원)</h2>
        <button onclick="startPayment()">결제하기</button>

        <div id="qr-area">
            <h3>스마트폰으로 QR을 스캔하세요</h3>
            <div id="qrcode"></div>
            <p id="order-no-text" style="font-size: 13px; color: #888;"></p>
            <p class="status-msg">💳 결제 진행 대기 중...</p>
        </div>
    </div>

    <script>
    let pollTimer = null;

    async function startPayment() {
        document.querySelector('button').style.display = 'none'; // 버튼 숨김
        
        // 1. 서버에 QR 결제 링크 생성 요청
        const res = await fetch('/api/create-qr', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ amount: 1004, goods_name: '전기차 충전료' })
        });
        const data = await res.json();

        if (data.success) {
            document.getElementById('qr-area').style.display = 'block';
            document.getElementById('order-no-text').innerText = `주문번호: ${data.orderNo}`;

            // QR코드 그려주기
            document.getElementById('qrcode').innerHTML = "";
            new QRCode(document.getElementById("qrcode"), {
                text: data.payUrl,
                width: 220,
                height: 220
            });

            // 2. 결제 완료 상태 주기적 감지 (1.5초 간격 Polling)
            checkOrderStatus(data.orderNo);
        } else {
            alert('QR 결제 생성 실패: ' + data.msg);
            location.reload();
        }
    }

    function checkOrderStatus(orderNo) {
        if (pollTimer) clearInterval(pollTimer);

        pollTimer = setInterval(async () => {
            const res = await fetch(`/api/order-status/${orderNo}`);
            const data = await res.json();

            // KICC 노티를 수신해서 상태가 'PAID'로 바뀌었으면!
            if (data.status === 'PAID') {
                clearInterval(pollTimer);
                showSuccessScreen();
            }
        }, 1500);
    }

    function showSuccessScreen() {
        document.getElementById('kiosk-card').innerHTML = `
            <div class="success-msg">🎉 결제가 완료되었습니다!</div>
            <p style="margin-top: 15px; color: #555;">충전을 시작합니다.</p>
            <p style="font-size: 12px; color: #aaa; margin-top: 30px;">3초 후 첫 화면으로 돌아갑니다...</p>
        `;
        
        setTimeout(() => {
            location.reload();
        }, 3000);
    }
    </script>

    </body>
    </html>
    """


# 2. KICC 결제 URL 생성 요청 API
@app.post("/api/create-qr")
async def create_qr(request: Request):
    body = await request.json()
    amount = body.get("amount", 1004)
    goods_name = body.get("goods_name", "전기차 충전료")
    
    # 고유 주문번호 생성
    order_no = f"ORD_{uuid.uuid4().hex[:12].upper()}"

    payload = {
        "directRegInfo": {
            "mallId": MALL_ID,      # ★ 수정 완료: 문자열 변수로 지정
            "regTxtype": "52",       # 52: 결제 URL 생성요청
            "regSubtype": "10",      # 10: 신규등록
            "amount": amount,
            "currency": "00",
            "payCode": "00"
        },
        "directOrderInfo": {
            "shopOrderNo": order_no,
            "goodsName": goods_name,
            "goodsAmount": amount
        }
    }

    try:
        response = requests.post(KICC_API_URL, json=payload, timeout=10)
        res_data = response.json()

        if res_data.get("resCd") == "0000":
            # 메모리에 주문 대기 상태 저장
            order_db[order_no] = {"status": "PENDING", "amount": amount}
            return {
                "success": True,
                "orderNo": order_no,
                "payUrl": res_data.get("authPageUrl")
            }
        else:
            return {"success": False, "msg": res_data.get("resMsg")}
    except Exception as e:
        return {"success": False, "msg": str(e)}


# 3. KICC 노티(웹훅) 수신 엔드포인트
@app.post("/api/kicc/webhook")
async def kicc_webhook(request: Request):
    try:
        data = await request.json()
        print("=== [KICC 노티 데이터 수신 완료] ===")
        print(json.dumps(data, indent=2, ensure_ascii=False))

        res_cd = data.get("resCd")
        shop_order_no = data.get("shopOrderNo")

        if res_cd == "0000":
            if shop_order_no in order_db:
                order_db[shop_order_no]["status"] = "PAID"
                print(f"✔ [상태변경 완료] {shop_order_no} -> PAID")

            return {"resCd": "0000", "resMsg": "정상처리"}
        else:
            return {"resCd": "9999", "resMsg": "결제 실패건"}

    except Exception as e:
        print(f"웹훅 처리 실패: {e}")
        return {"resCd": "9999", "resMsg": "Internal Error"}


# 4. 키오스크 결제 상태 확인 API (Polling)
@app.get("/api/order-status/{order_no}")
def get_order_status(order_no: str):
    order = order_db.get(order_no)
    if not order:
        return {"status": "NOT_FOUND"}
    return {"status": order["status"]}


# 4. 키오스크 결제 상태 확인 API (Polling)
@app.get("/api/order-status/{order_no}")
def get_order_status(order_no: str):
    order = order_db.get(order_no)
    if not order:
        return {"status": "NOT_FOUND"}
    return {"status": order["status"]}
