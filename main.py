from fastapi.responses import PlainTextResponse  # 상단 import에 추가 필요

# 3. KICC 노티(웹훅) 수신 엔드포인트
@app.post("/api/kicc/webhook")
async def kicc_webhook(request: Request):
    try:
        # Form Data 및 JSON 지원 파싱
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            data = await request.json()
        else:
            form_data = await request.form()
            data = dict(form_data)

        print("\n📥 === [KICC 노티 데이터 수신 완료] ===")
        print(json.dumps(data, indent=2, ensure_ascii=False))

        res_cd = data.get("resCd") or data.get("res_cd")
        shop_order_no = data.get("shopOrderNo") or data.get("shop_order_no")

        if res_cd == "0000":
            if shop_order_no in order_db:
                order_db[shop_order_no]["status"] = "PAID"
                print(f"✅ [주문 상태 변경 완료] {shop_order_no} -> PAID")
            else:
                print(f"⚠️ [경고] order_db에 주문번호 없음: {shop_order_no}")

        # ★ KICC 'res_cd= does not exists' 오류 해결 핵심 ★
        # KICC가 파싱 가능한 res_cd=0000 포맷의 PlainText 응답 반환
        return PlainTextResponse("res_cd=0000&res_msg=SUCCESS")

    except Exception as e:
        print(f"❌ [웹훅 처리 중 에러 발생]: {e}")
        # 에러 발생 시에도 KICC 파싱 규격에 맞춰 응답하여 재전송 폭주 방지
        return PlainTextResponse("res_cd=0000&res_msg=SUCCESS")
