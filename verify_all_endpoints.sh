#!/bin/bash
# Japan Intelligence — 全エンドポイント自己検証スクリプト
# 全33EPをcurlでテストし、レスポンスステータスとデータ品質を確認する

BASE="http://localhost:8080"
API_KEY="ji_PsbSlXRsHXD72mMGK82as_dwi3YgKGGBdZWg_nRNCY0"
PASS=0
FAIL=0
WARN=0

check() {
    local name="$1"
    local url="$2"
    local method="${3:-GET}"
    local body="$4"

    if [ "$method" = "POST" ]; then
        RESULT=$(curl -s -w "\n%{http_code}" -X POST "$url" \
            -H "X-API-Key: $API_KEY" \
            -H "Content-Type: application/json" \
            -d "$body" 2>/dev/null)
    else
        RESULT=$(curl -s -w "\n%{http_code}" "$url" \
            -H "X-API-Key: $API_KEY" 2>/dev/null)
    fi

    HTTP_CODE=$(echo "$RESULT" | tail -1)
    BODY=$(echo "$RESULT" | sed '$d')

    # JSONのステータスチェック
    STATUS=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))" 2>/dev/null)
    COUNT=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('count','?'))" 2>/dev/null)

    if [ "$HTTP_CODE" = "200" ] && [ "$STATUS" = "ok" ]; then
        echo "✅ $name — HTTP $HTTP_CODE (count: $COUNT)"
        PASS=$((PASS + 1))
    elif [ "$HTTP_CODE" = "200" ]; then
        echo "⚠️  $name — HTTP $HTTP_CODE (status: $STATUS)"
        WARN=$((WARN + 1))
    else
        echo "❌ $name — HTTP $HTTP_CODE"
        echo "   Body: $(echo "$BODY" | head -c 200)"
        FAIL=$((FAIL + 1))
    fi
}

echo "=============================================="
echo "Japan Intelligence — Full Endpoint Verification"
echo "=============================================="
echo ""

echo "--- Reference ---"
check "health" "$BASE/api/v1/health"
check "ticker/7203" "$BASE/api/v1/ticker/7203"

echo ""
echo "--- Intelligence ---"
check "briefing" "$BASE/api/v1/briefing"
check "market/snapshot" "$BASE/api/v1/market/snapshot"
check "intelligence/7203" "$BASE/api/v1/intelligence/7203"
check "disclosures/stats" "$BASE/api/v1/disclosures/stats?days=3"

echo ""
echo "--- TDnet ---"
check "disclosures" "$BASE/api/v1/disclosures?days=3&limit=5"
check "disclosures/7203" "$BASE/api/v1/disclosures/7203"

echo ""
echo "--- EDINET ---"
check "holdings" "$BASE/api/v1/holdings?days=7&limit=5"
check "holdings/7203" "$BASE/api/v1/holdings/7203"

echo ""
echo "--- gBizINFO ---"
check "company/search" "$BASE/api/v1/company/search?name=トヨタ"
check "company/7203" "$BASE/api/v1/company/7203"
check "company/7203/subsidies" "$BASE/api/v1/company/7203/subsidies"
check "company/7203/certifications" "$BASE/api/v1/company/7203/certifications"
check "company/7203/patents" "$BASE/api/v1/company/7203/patents"
check "company/7203/finance" "$BASE/api/v1/company/7203/finance"

echo ""
echo "--- e-Stat ---"
check "stats/series" "$BASE/api/v1/stats/series"
check "stats/summary" "$BASE/api/v1/stats/summary"
check "stats/gdp" "$BASE/api/v1/stats/gdp?limit=5"
check "stats/cpi" "$BASE/api/v1/stats/cpi?limit=5"
check "stats/unemployment" "$BASE/api/v1/stats/unemployment?limit=5"
check "stats/economy_watchers" "$BASE/api/v1/stats/economy_watchers?limit=5"
check "stats/search/GDP" "$BASE/api/v1/stats/search/GDP?limit=3"

echo ""
echo "--- J-Quants ---"
check "stocks" "$BASE/api/v1/stocks?market=プライム"
check "earnings" "$BASE/api/v1/earnings"
check "financials/7203" "$BASE/api/v1/financials/7203"

echo ""
echo "--- FRED ---"
check "global/series" "$BASE/api/v1/global/series"
check "global/policy" "$BASE/api/v1/global/policy"
check "global/fed_funds_rate" "$BASE/api/v1/global/fed_funds_rate?limit=5"

echo ""
echo "--- BOJ ---"
check "tankan" "$BASE/api/v1/tankan"
check "tankan/series/list" "$BASE/api/v1/tankan/series/list"
check "tankan/tankan_large_manufacturing" "$BASE/api/v1/tankan/tankan_large_manufacturing?limit=5"

echo ""
echo "--- JPX ---"
check "investor-flows" "$BASE/api/v1/investor-flows"

echo ""
echo "--- Macro ---"
check "macro" "$BASE/api/v1/macro"
check "macro/events" "$BASE/api/v1/macro/events"

echo ""
echo "--- AI Interpret ---"
check "interpret" "$BASE/api/v1/interpret" "POST" '{"type":"disclosure","data":{"ticker":"7203.T","title":"test disclosure","category":"業績修正"}}'

echo ""
echo "=============================================="
echo "Results: ✅ $PASS passed / ⚠️ $WARN warnings / ❌ $FAIL failed"
echo "=============================================="
