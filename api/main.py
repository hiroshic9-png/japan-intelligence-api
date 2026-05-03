"""
Japan Intelligence API — メインサーバー

日本の公開情報を構造化し、エージェント向けに配信するAPIサーバー。

エンドポイント:
  GET  /api/v1/disclosures          - TDnet適時開示一覧
  GET  /api/v1/disclosures/{ticker} - 特定銘柄の適時開示
  GET  /api/v1/holdings             - EDINET大量保有報告
  GET  /api/v1/holdings/{ticker}    - 特定銘柄の大量保有
  GET  /api/v1/macro                - マクロ指標
  GET  /api/v1/macro/events         - マクロ異常変動イベント
  POST /api/v1/interpret            - AI解釈（Layer 2）
  GET  /api/v1/ticker/{ticker}      - 銘柄情報
  GET  /api/v1/health               - ヘルスチェック
"""
import sys
import os
import traceback
from datetime import datetime
from contextlib import asynccontextmanager

# パス解決
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Query, Path, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.config import API_VERSION, API_TITLE, API_DESCRIPTION
from core.ticker_resolver import resolve_name, resolve_names_batch
from sources.tdnet import TDnetSource
from sources.edinet import EDINETSource
from sources.macro import MacroSource
from intelligence.interpreter import Interpreter

# === データソース初期化 ===
tdnet = TDnetSource()
edinet = EDINETSource()
macro = MacroSource()
interpreter = Interpreter()


# === OpenAPI タグ定義 ===
TAGS = [
    {"name": "Disclosures", "description": "TDnet適時開示情報 — 業績修正・M&A・自社株買い等の分類済みデータ"},
    {"name": "Holdings", "description": "EDINET大量保有報告書 — 機関投資家の持分変動追跡"},
    {"name": "Macro", "description": "マクロ指標 — 原油・金・ドル円・VIX・日経・S&P500の異常変動検知"},
    {"name": "Intelligence", "description": "AI解釈エンジン（Layer 2）— 構造化データへの意味付けと投資示唆"},
    {"name": "Reference", "description": "銘柄情報・ヘルスチェック等のユーティリティ"},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリケーション起動時に初期データをプリフェッチ"""
    print(f"[Japan Intelligence] Starting API server v{API_VERSION}")
    yield
    print("[Japan Intelligence] Shutting down")


app = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version=API_VERSION,
    lifespan=lifespan,
    openapi_tags=TAGS,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# === グローバル例外ハンドラ ===

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """未捕捉例外を統一フォーマットで返却"""
    print(f"[ERROR] {request.method} {request.url}: {exc}")
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "error": "Internal server error",
            "detail": str(exc) if os.getenv("DEBUG") else None,
            "timestamp": datetime.now().isoformat(),
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "error": exc.detail,
            "detail": None,
            "timestamp": datetime.now().isoformat(),
        },
    )


# === レスポンスヘルパー ===

def _wrap_response(source: str, data, total: int = None,
                   offset: int = 0, limit: int = 100):
    """共通レスポンスラッパー（ページネーション対応）"""
    if isinstance(data, list):
        actual_total = total if total is not None else len(data)
        paginated = data[offset:offset + limit]
        count = len(paginated)
        has_more = (offset + limit) < actual_total
        pagination = {
            "offset": offset,
            "limit": limit,
            "total": actual_total,
            "has_more": has_more,
        }
        response_data = paginated
    else:
        count = 1
        pagination = None
        response_data = data

    return {
        "status": "ok",
        "source": source,
        "updated_at": datetime.now().isoformat(),
        "count": count,
        "data": response_data,
        "pagination": pagination,
        "meta": {
            "api_version": API_VERSION,
        },
    }


def _normalize_ticker(ticker: str) -> str:
    """ティッカー正規化 — .T付与"""
    if not ticker.endswith('.T'):
        return f"{ticker}.T"
    return ticker


# ===========================
#  ヘルスチェック
# ===========================
@app.get("/api/v1/health", tags=["Reference"])
async def health():
    """APIサーバーのヘルスチェック"""
    return {
        "status": "ok",
        "service": "japan-intelligence",
        "version": API_VERSION,
        "timestamp": datetime.now().isoformat(),
        "sources": {
            "tdnet": "available",
            "edinet": "available" if edinet.api_key else "no_api_key",
            "macro": "available",
            "interpreter": "available" if interpreter.client else "no_api_key",
        },
        "endpoints": {
            "disclosures": "/api/v1/disclosures",
            "holdings": "/api/v1/holdings",
            "macro": "/api/v1/macro",
            "events": "/api/v1/macro/events",
            "interpret": "/api/v1/interpret",
            "ticker": "/api/v1/ticker/{ticker}",
            "docs": "/docs",
        },
    }


# ===========================
#  TDnet 適時開示
# ===========================
@app.get("/api/v1/disclosures", tags=["Disclosures"])
async def get_disclosures(
    days: int = Query(default=3, ge=1, le=30, description="取得期間（日数）"),
    category: str = Query(default=None, description="カテゴリフィルタ（例: 業績修正, M&A・提携, 自社株買い）"),
    impact: str = Query(default=None, description="インパクトフィルタ（POSITIVE/NEGATIVE/NEUTRAL/MILD_POSITIVE）"),
    offset: int = Query(default=0, ge=0, description="ページネーション開始位置"),
    limit: int = Query(default=100, ge=1, le=500, description="取得件数上限"),
):
    """
    TDnet適時開示情報を構造化して返す。

    - 業績修正、M&A、自社株買い、配当変更等の **15カテゴリ** に自動分類
    - 各開示に対して **株価インパクト判定** (POSITIVE/NEGATIVE/NEUTRAL/MILD_POSITIVE) を付与
    - 対象: 東証全上場企業
    - 更新頻度: 30分キャッシュ
    """
    disclosures = tdnet.get_disclosures(days=days)

    # 会社名を付与
    for d in disclosures:
        if not d.get('company_name'):
            d['company_name'] = resolve_name(d['ticker'])

    # フィルタ
    if category:
        disclosures = [d for d in disclosures if d['category'] == category]
    if impact:
        disclosures = [d for d in disclosures if d['impact'] == impact.upper()]

    return _wrap_response("tdnet", disclosures, offset=offset, limit=limit)


@app.get("/api/v1/disclosures/stats", tags=["Intelligence"])
async def get_disclosure_stats(
    days: int = Query(default=3, ge=1, le=30, description="集計期間（日数）"),
):
    """
    適時開示のカテゴリ別・インパクト別統計を返す。

    エージェントが市場の「温度感」を把握するために使用。
    どのカテゴリの開示が多いか、ポジティブ/ネガティブの比率はどうかを一目で判断可能。
    """
    disclosures = tdnet.get_disclosures(days=days)

    # カテゴリ別集計
    category_counts = {}
    impact_counts = {"POSITIVE": 0, "NEGATIVE": 0, "NEUTRAL": 0, "MILD_POSITIVE": 0}
    notable = []  # POSITIVE/NEGATIVE のみ

    for d in disclosures:
        cat = d.get('category', 'その他')
        imp = d.get('impact', 'NEUTRAL')
        category_counts[cat] = category_counts.get(cat, 0) + 1
        if imp in impact_counts:
            impact_counts[imp] += 1

        if imp in ('POSITIVE', 'NEGATIVE'):
            if not d.get('company_name'):
                d['company_name'] = resolve_name(d['ticker'])
            notable.append({
                'ticker': d['ticker'],
                'company_name': d['company_name'],
                'title': d['title'],
                'category': cat,
                'impact': imp,
            })

    # カテゴリをcount降順でソート
    sorted_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)

    return _wrap_response("disclosure_stats", {
        "period_days": days,
        "total_disclosures": len(disclosures),
        "category_breakdown": [{"category": k, "count": v} for k, v in sorted_categories],
        "impact_breakdown": impact_counts,
        "positive_ratio": round(
            (impact_counts["POSITIVE"] + impact_counts["MILD_POSITIVE"]) / max(len(disclosures), 1) * 100, 1
        ),
        "notable_disclosures": notable[:20],
    })


@app.get("/api/v1/disclosures/{ticker}", tags=["Disclosures"])
async def get_disclosure_by_ticker(
    ticker: str = Path(description="銘柄コード（例: 7203 または 7203.T）"),
    interpret: bool = Query(default=False, description="AI解釈を含めるか（Layer 2）"),
):
    """
    特定銘柄の直近適時開示を返す。

    `interpret=true` でGemini 2.5によるAI解釈（重要度・株価影響・投資家向けポイント）を付与。
    """
    ticker = _normalize_ticker(ticker)
    disclosures = tdnet.get_disclosures(ticker=ticker)

    if not disclosures:
        return _wrap_response("tdnet", {
            'ticker': ticker,
            'company_name': resolve_name(ticker),
            'disclosures': [],
            'ai_interpretation': None,
        })

    # 会社名付与
    company = resolve_name(ticker)
    for d in disclosures:
        d['company_name'] = company

    result = {
        'ticker': ticker,
        'company_name': company,
        'disclosures': disclosures,
    }

    # AI解釈（Layer 2）
    if interpret and disclosures:
        ai_result = interpreter.interpret_disclosure(disclosures[0])
        result['ai_interpretation'] = ai_result

    return _wrap_response("tdnet", result)


# ===========================
#  EDINET 大量保有報告
# ===========================
@app.get("/api/v1/holdings", tags=["Holdings"])
async def get_holdings(
    days: int = Query(default=7, ge=1, le=30, description="取得期間（日数）"),
    offset: int = Query(default=0, ge=0, description="ページネーション開始位置"),
    limit: int = Query(default=100, ge=1, le=500, description="取得件数上限"),
):
    """
    EDINET大量保有報告書・変更報告書を構造化して返す。

    機関投資家の持分変動を追跡可能。5%以上の保有変動を検出。
    **注意**: EDINET_API_KEY が必要です。
    """
    holdings = edinet.get_holdings(days=days)

    for h in holdings:
        h['company_name'] = resolve_name(h['ticker'])

    return _wrap_response("edinet", holdings, offset=offset, limit=limit)


@app.get("/api/v1/holdings/{ticker}", tags=["Holdings"])
async def get_holdings_by_ticker(
    ticker: str = Path(description="銘柄コード（例: 7203 または 7203.T）"),
):
    """特定銘柄の大量保有報告書を返す。"""
    ticker = _normalize_ticker(ticker)
    holdings = edinet.get_holdings(ticker=ticker)

    for h in holdings:
        h['company_name'] = resolve_name(h['ticker'])

    return _wrap_response("edinet", holdings)


# ===========================
#  マクロ指標
# ===========================
@app.get("/api/v1/macro", tags=["Macro"])
async def get_macro():
    """
    主要マクロ指標の最新値を返す。

    対象指標: 原油WTI, 金先物, ドル円, VIX恐怖指数, 日経225, S&P500
    """
    indicators = macro.get_indicators()
    return _wrap_response("macro", indicators)


@app.get("/api/v1/macro/events", tags=["Macro"])
async def get_macro_events(
    interpret: bool = Query(default=False, description="AI解釈を含めるか（Layer 2）"),
):
    """
    マクロ指標の異常変動イベントを検出して返す。

    - 原油急騰/急落 (±5%)
    - 金急騰 (3%+)
    - 円高/円安 (±1.5%)
    - VIX急騰 (15%+)

    各イベントに **恩恵/逆風銘柄マッピング** を付与。
    `interpret=true` でAI解釈付き。
    """
    events = macro.detect_events()

    # 銘柄名を解決
    for e in events:
        e['positive_details'] = [
            {'ticker': t, 'company_name': resolve_name(t)} for t in e.get('positive_tickers', [])
        ]
        e['negative_details'] = [
            {'ticker': t, 'company_name': resolve_name(t)} for t in e.get('negative_tickers', [])
        ]

    # AI解釈
    if interpret:
        for e in events:
            e['ai_interpretation'] = interpreter.interpret_macro_event(e)

    return _wrap_response("macro_events", events)


# ===========================
#  AI解釈（Layer 2）
# ===========================
@app.post("/api/v1/interpret", tags=["Intelligence"])
async def interpret_data(data: dict):
    """
    任意の構造化データに対してAI解釈を生成する（Layer 2）。

    入力形式:
    ```json
    {"type": "disclosure", "data": {"ticker": "7203.T", "title": "...", ...}}
    {"type": "macro_event", "data": {"label": "円高加速", "change_pct": -2.0, ...}}
    ```
    """
    data_type = data.get("type", "")
    payload = data.get("data", {})

    if not data_type:
        raise HTTPException(status_code=400, detail="'type' field is required (disclosure / macro_event)")
    if not payload:
        raise HTTPException(status_code=400, detail="'data' field is required")

    if data_type == "disclosure":
        result = interpreter.interpret_disclosure(payload)
    elif data_type == "macro_event":
        result = interpreter.interpret_macro_event(payload)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown type: '{data_type}'. Use 'disclosure' or 'macro_event'")

    return _wrap_response("interpreter", result)


# ===========================
#  銘柄情報
# ===========================
@app.get("/api/v1/ticker/{ticker}", tags=["Reference"])
async def get_ticker_info(
    ticker: str = Path(description="銘柄コード（例: 7203 または 7203.T）"),
):
    """銘柄コードから会社名等の基本情報を返す。"""
    ticker = _normalize_ticker(ticker)

    return _wrap_response("ticker", {
        'ticker': ticker,
        'company_name': resolve_name(ticker),
    })


# ===========================
#  インサイト系エンドポイント
# ===========================

@app.get("/api/v1/market/snapshot", tags=["Intelligence"])
async def get_market_snapshot():
    """
    マーケットスナップショット — 1リクエストで市場全体の状態を取得。

    エージェントの最も基本的な使い方:
    「今、日本市場で何が起きているか？」を1回のAPI呼び出しで把握する。

    含まれるデータ:
    - マクロ指標6種の最新値
    - 検出されたマクロ異常変動イベント
    - 直近の適時開示統計（カテゴリ・インパクト分布）
    - 注目開示（POSITIVE/NEGATIVEのみ）
    """
    # マクロ指標
    indicators = macro.get_indicators()
    events = macro.detect_events()

    # 開示統計
    disclosures = tdnet.get_disclosures(days=1)
    impact_counts = {"POSITIVE": 0, "NEGATIVE": 0, "NEUTRAL": 0, "MILD_POSITIVE": 0}
    notable = []

    for d in disclosures:
        imp = d.get('impact', 'NEUTRAL')
        if imp in impact_counts:
            impact_counts[imp] += 1
        if imp in ('POSITIVE', 'NEGATIVE'):
            if not d.get('company_name'):
                d['company_name'] = resolve_name(d['ticker'])
            notable.append({
                'ticker': d['ticker'],
                'company_name': d['company_name'],
                'title': d['title'][:80],
                'category': d.get('category', ''),
                'impact': imp,
            })

    # イベントの銘柄名解決
    for e in events:
        e['positive_details'] = [
            {'ticker': t, 'company_name': resolve_name(t)} for t in e.get('positive_tickers', [])
        ]
        e['negative_details'] = [
            {'ticker': t, 'company_name': resolve_name(t)} for t in e.get('negative_tickers', [])
        ]

    return _wrap_response("market_snapshot", {
        "timestamp": datetime.now().isoformat(),
        "macro": {
            "indicators": indicators,
            "events": events,
            "event_count": len(events),
        },
        "disclosures": {
            "today_count": len(disclosures),
            "impact_breakdown": impact_counts,
            "notable": notable[:10],
        },
    })


# ===========================
#  エントリポイント
# ===========================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
