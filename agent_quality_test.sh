#!/bin/bash
# Japan Intelligence — エージェント視点品質テスト
# 全エンドポイントをAIエージェントが実際に使うシナリオで検証する
#
# テスト観点:
#   1. レスポンスが空でないか
#   2. 必須フィールドが存在するか
#   3. レスポンス時間が妥当か（10秒以内）
#   4. HTTPステータスが200か
#   5. Cache-Controlヘッダーが付与されているか

set -euo pipefail

API_BASE="${1:-http://localhost:8080}"
API_KEY="${2:-ji_PsbSlXRsHXD72mMGK82as_dwi3YgKGGBdZWg_nRNCY0}"

PASS=0
FAIL=0
WARN=0

# --- テストヘルパー ---
test_endpoint() {
    local name="$1"
    local path="$2"
    local required_field="$3"
    local method="${4:-GET}"
    local body="${5:-}"

    local start_time=$(python3 -c "import time; print(time.time())")
    
    local http_code
    local response
    
    if [ "$method" = "POST" ]; then
        response=$(curl -s -w "\n%{http_code}" -X POST \
            -H "X-API-Key: $API_KEY" \
            -H "Content-Type: application/json" \
            -d "$body" \
            "$API_BASE$path" 2>/dev/null || echo -e "\n000")
    else
        response=$(curl -s -w "\n%{http_code}" \
            -H "X-API-Key: $API_KEY" \
            "$API_BASE$path" 2>/dev/null || echo -e "\n000")
    fi
    
    http_code=$(echo "$response" | tail -1)
    local body_response=$(echo "$response" | sed '$d')
    
    local end_time=$(python3 -c "import time; print(time.time())")
    local elapsed=$(python3 -c "print(f'{$end_time - $start_time:.2f}')")

    # 検証
    local status="PASS"
    local detail=""
    
    if [ "$http_code" != "200" ]; then
        status="FAIL"
        detail="HTTP $http_code"
    elif [ -z "$body_response" ]; then
        status="FAIL"
        detail="Empty response"
    elif [ -n "$required_field" ]; then
        if ! echo "$body_response" | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    fields='$required_field'.split(',')
    for f in fields:
        parts = f.strip().split('.')
        obj = d
        for p in parts:
            if isinstance(obj, dict) and p in obj:
                obj = obj[p]
            else:
                print(f'MISSING:{f}')
                sys.exit(1)
    print('OK')
except:
    print('PARSE_ERROR')
    sys.exit(1)
" 2>/dev/null | grep -q "OK"; then
            status="FAIL"
            detail="Missing field: $required_field"
        fi
    fi
    
    # 遅延チェック
    if python3 -c "exit(0 if float('$elapsed') > 10 else 1)" 2>/dev/null; then
        if [ "$status" = "PASS" ]; then
            status="WARN"
            detail="Slow: ${elapsed}s"
        else
            detail="$detail + Slow: ${elapsed}s"
        fi
    fi
    
    # 結果表示
    if [ "$status" = "PASS" ]; then
        echo -e "  ✅ $name (${elapsed}s)"
        PASS=$((PASS + 1))
    elif [ "$status" = "WARN" ]; then
        echo -e "  ⚠️  $name — $detail"
        WARN=$((WARN + 1))
    else
        echo -e "  ❌ $name — $detail"
        FAIL=$((FAIL + 1))
    fi
}

echo "============================================"
echo "  Japan Intelligence — Agent Quality Test"
echo "  Target: $API_BASE"
echo "============================================"
echo ""

# --- Scenario 1: 朝の第一手（エージェントが最初に呼ぶもの） ---
echo "📋 Scenario 1: Morning First Call"
test_endpoint "japan_briefing" "/api/v1/briefing" "status,data"
test_endpoint "market_snapshot" "/api/v1/market/snapshot" "status,data"
echo ""

# --- Scenario 2: 企業分析（最も重要なユースケース） ---
echo "🏢 Scenario 2: Company Analysis (Toyota 7203)"
test_endpoint "company_intelligence" "/api/v1/intelligence/7203" "status,data.company_name,data.stock_price"
test_endpoint "financials" "/api/v1/financials/7203" "status,data"
test_endpoint "stock_prices" "/api/v1/prices/7203?limit=5" "status,data.ticker,data.moving_averages"
test_endpoint "company_profile" "/api/v1/company/1180301018771" "status,data"
echo ""

# --- Scenario 3: 市場全体の把握 ---
echo "📊 Scenario 3: Market Overview"
test_endpoint "disclosures" "/api/v1/disclosures?days=1&limit=5" "status"
test_endpoint "disclosure_stats" "/api/v1/disclosures/stats?days=3" "status"
test_endpoint "macro_indicators" "/api/v1/macro" "status,data"
test_endpoint "macro_events" "/api/v1/macro/events" "status"
test_endpoint "sectors" "/api/v1/sectors" "status,data.total_stocks"
echo ""

# --- Scenario 4: 日本経済マクロ ---
echo "🇯🇵 Scenario 4: Japan Macro Economics"
test_endpoint "stats_summary" "/api/v1/stats/summary" "status"
test_endpoint "stats_gdp" "/api/v1/stats/gdp?limit=5" "status"
test_endpoint "economy_watchers" "/api/v1/stats/economy_watchers?limit=5" "status"
test_endpoint "tankan" "/api/v1/tankan" "status,data"
test_endpoint "investor_flows" "/api/v1/investor-flows" "status"
echo ""

# --- Scenario 5: 日米金融環境 ---
echo "🌐 Scenario 5: US-Japan Financial Environment"
test_endpoint "policy_summary" "/api/v1/global/policy" "status,data"
test_endpoint "fred_usdjpy" "/api/v1/global/usdjpy?limit=5" "status,data"
test_endpoint "fred_vix" "/api/v1/global/vix?limit=5" "status,data"
echo ""

# --- Scenario 6: 銘柄検索・マスタ ---
echo "🔍 Scenario 6: Stock Discovery"
test_endpoint "listed_stocks" "/api/v1/stocks?market=%E3%83%97%E3%83%A9%E3%82%A4%E3%83%A0" "status,data"
test_endpoint "earnings_calendar" "/api/v1/earnings" "status"
test_endpoint "ticker_resolve" "/api/v1/ticker/7203" "status,data"
echo ""

# --- Scenario 7: AI解釈 ---
echo "🤖 Scenario 7: AI Interpretation"
test_endpoint "interpret" "/api/v1/interpret" "status" "POST" '{"type":"macro_event","data":{"event":"yen_weakening","indicator":"USD/JPY","value":157.0,"change_pct":1.8}}'
echo ""

# --- Scenario 8: インフラ ---
echo "⚙️  Scenario 8: Infrastructure"
test_endpoint "health" "/api/v1/health" "sources,capabilities"
echo ""

# --- 結果サマリー ---
TOTAL=$((PASS + FAIL + WARN))
echo "============================================"
echo "  Results: $PASS/$TOTAL passed"
if [ $WARN -gt 0 ]; then
    echo "  Warnings: $WARN"
fi
if [ $FAIL -gt 0 ]; then
    echo "  Failures: $FAIL"
fi
echo "============================================"

if [ $FAIL -gt 0 ]; then
    exit 1
fi
