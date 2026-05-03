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
  GET  /api/v1/company/{id}         - gBizINFO企業プロフィール
  GET  /api/v1/company/{id}/subsidies    - 補助金履歴
  GET  /api/v1/company/{id}/certifications - 認定情報
  GET  /api/v1/company/{id}/patents  - 特許情報
  GET  /api/v1/company/search        - 企業名検索
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

from core.config import API_VERSION, API_TITLE, API_DESCRIPTION, TICKER_TO_CORPORATE_NUMBER
from core.ticker_resolver import resolve_name, resolve_names_batch
from core.cache_middleware import CacheControlMiddleware
from sources.tdnet import TDnetSource
from sources.edinet import EDINETSource
from sources.macro import MacroSource
from sources.gbizinfo import GBizInfoSource
from sources.estat import EStatSource
from sources.jquants import JQuantsSource
from sources.fred import FredSource
from sources.boj import BOJSource
from sources.jpx_investor import JPXInvestorFlowSource
from intelligence.interpreter import Interpreter

# === データソース初期化 ===
tdnet = TDnetSource()
edinet = EDINETSource()
macro = MacroSource()
gbizinfo = GBizInfoSource()
estat = EStatSource()
jquants = JQuantsSource()
fred = FredSource()
boj = BOJSource()
jpx_investor = JPXInvestorFlowSource()
interpreter = Interpreter()


# === OpenAPI タグ定義 ===
TAGS = [
    {"name": "Disclosures", "description": "TDnet適時開示情報 — 業績修正・M&A・自社株買い等の分類済みデータ"},
    {"name": "Holdings", "description": "EDINET大量保有報告書 — 機関投資家の持分変動追跡"},
    {"name": "Company", "description": "gBizINFO企業情報 — 500万法人の補助金・認定・特許・財務・調達データ"},
    {"name": "Statistics", "description": "e-Stat政府統計 — GDP・雇用・物価・鉱工業生産・小売・景気ウォッチャー・家計調査・貿易統計"},
    {"name": "Market", "description": "J-Quants市場データ — 全上場銘柄マスタ・決算カレンダー・財務サマリー"},
    {"name": "BOJ", "description": "日本銀行統計 — 短観（全国企業短期経済観測調査）業況判断DI"},
    {"name": "InvestorFlows", "description": "JPX投資部門別売買動向 — 外国人・個人・信託銀行等の週次売買データ"},
    {"name": "Global", "description": "FRED米国マクロ — 米金利・CPI・雇用・日銀政策金利・ドル円"},
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

# レスポンスキャッシュ — ソース特性別TTL
app.add_middleware(CacheControlMiddleware)


# === API認証 & レート制限 ===

# APIキー認証（JI_API_KEY環境変数が設定されている場合のみ有効化）
JI_API_KEY = os.getenv("JI_API_KEY", "")
RATE_LIMIT_PER_HOUR = int(os.getenv("RATE_LIMIT_PER_HOUR", "100"))
_rate_store: dict[str, list] = {}  # {client_id: [timestamps]}

# 認証免除パス
AUTH_EXEMPT_PATHS = {"/docs", "/redoc", "/openapi.json", "/api/v1/health"}


@app.middleware("http")
async def auth_and_rate_limit(request: Request, call_next):
    """APIキー認証 + 毎時レート制限"""
    path = request.url.path

    # 認証免除パス
    if path in AUTH_EXEMPT_PATHS:
        return await call_next(request)

    # APIキー認証（設定されている場合のみ）
    if JI_API_KEY:
        api_key = (
            request.headers.get("X-API-Key")
            or request.headers.get("Authorization", "").replace("Bearer ", "")
            or request.query_params.get("api_key")
        )
        if api_key != JI_API_KEY:
            return JSONResponse(
                status_code=401,
                content={
                    "status": "error",
                    "error": "Invalid or missing API key",
                    "detail": "Set X-API-Key header or api_key query parameter",
                    "timestamp": datetime.now().isoformat(),
                },
            )

    # レート制限（IPベース）
    client_ip = request.client.host if request.client else "unknown"
    client_id = api_key if JI_API_KEY and api_key else client_ip  # type: ignore
    now = datetime.now()

    if client_id not in _rate_store:
        _rate_store[client_id] = []

    # 1時間以内のリクエストのみ保持
    _rate_store[client_id] = [
        t for t in _rate_store[client_id]
        if (now - t).total_seconds() < 3600
    ]

    if len(_rate_store[client_id]) >= RATE_LIMIT_PER_HOUR:
        return JSONResponse(
            status_code=429,
            content={
                "status": "error",
                "error": "Rate limit exceeded",
                "detail": f"Max {RATE_LIMIT_PER_HOUR} requests per hour",
                "timestamp": now.isoformat(),
            },
        )

    _rate_store[client_id].append(now)
    response = await call_next(request)

    # レート制限ヘッダー
    remaining = RATE_LIMIT_PER_HOUR - len(_rate_store[client_id])
    response.headers["X-RateLimit-Limit"] = str(RATE_LIMIT_PER_HOUR)
    response.headers["X-RateLimit-Remaining"] = str(remaining)

    return response


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
            "gbizinfo": "available" if gbizinfo.api_token else "no_api_token",
            "estat": "available" if estat.app_id else "no_app_id",
            "jquants": "available" if jquants.api_key else "no_api_key",
            "fred": "available" if fred.api_key else "no_api_key",
            "boj": "available",
            "jpx_investor": "available",
            "macro": "available",
            "interpreter": "available" if interpreter.client else "no_api_key",
        },
        "capabilities": {
            "total_endpoints": 35,
            "total_mcp_tools": 22,
            "data_sources": 10,
            "authentication": bool(JI_API_KEY),
            "rate_limit": RATE_LIMIT_PER_HOUR,
            "dynamic_ticker_resolution": True,
            "cross_source_intelligence": True,
            "japan_briefing": True,
        },
        "endpoints": {
            "briefing": "/api/v1/briefing",
            "intelligence": "/api/v1/intelligence/{ticker}",
            "market_snapshot": "/api/v1/market/snapshot",
            "disclosures": "/api/v1/disclosures",
            "holdings": "/api/v1/holdings",
            "company": "/api/v1/company/{id}",
            "company_search": "/api/v1/company/search",
            "stats": "/api/v1/stats/{series_id}",
            "stats_summary": "/api/v1/stats/summary",
            "stocks": "/api/v1/stocks",
            "earnings": "/api/v1/earnings",
            "financials": "/api/v1/financials/{ticker}",
            "tankan": "/api/v1/tankan",
            "tankan_series": "/api/v1/tankan/{series_id}",
            "investor_flows": "/api/v1/investor-flows",
            "global_policy": "/api/v1/global/policy",
            "global_series": "/api/v1/global/{series_key}",
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
#  gBizINFO 企業情報
# ===========================

def _resolve_corporate_number(identifier: str) -> str:
    """
    銘柄コードまたは法人番号を法人番号に正規化する。

    解決順序:
    1. 静的マッピング（TICKER_TO_CORPORATE_NUMBER）
    2. 動的解決: J-Quants銘柄名 → gBizINFO検索 → 法人番号（結果キャッシュ）
    3. フォールバック: そのまま返す
    """
    # 4桁の銘柄コードの場合
    if len(identifier) == 4 and identifier.isdigit():
        ticker = f"{identifier}.T"
        if ticker in TICKER_TO_CORPORATE_NUMBER:
            return TICKER_TO_CORPORATE_NUMBER[ticker]
        # 動的解決を試みる
        resolved = _dynamic_resolve(identifier, ticker)
        if resolved:
            return resolved
    # .T付きティッカーの場合
    if identifier.endswith('.T'):
        if identifier in TICKER_TO_CORPORATE_NUMBER:
            return TICKER_TO_CORPORATE_NUMBER[identifier]
        code = identifier.replace('.T', '')
        resolved = _dynamic_resolve(code, identifier)
        if resolved:
            return resolved
    # そのまま法人番号として扱う
    return identifier


# 動的解決キャッシュ
_dynamic_corp_cache: dict = {}


def _dynamic_resolve(code: str, ticker: str):
    """
    J-Quantsで銘柄名を取得 → gBizINFOで法人番号を検索。
    結果をキャッシュしてTICKER_TO_CORPORATE_NUMBERに追加。
    """
    if ticker in _dynamic_corp_cache:
        return _dynamic_corp_cache[ticker]

    try:
        # Step 1: ticker_resolverから会社名を取得
        company_name = resolve_name(ticker)
        if not company_name or company_name == ticker:
            # J-Quants銘柄マスタから取得を試みる
            stocks = jquants.get_listed_stocks()
            for s in stocks:
                if s.get("code", "").startswith(code):
                    company_name = s.get("name", "")
                    break

        if not company_name or company_name == ticker:
            return None

        # Step 2: gBizINFOで企業名検索
        # 「株式会社」等を除去して検索精度を上げる
        search_name = (company_name
                       .replace("株式会社", "")
                       .replace("(株)", "")
                       .replace("（株）", "")
                       .strip())
        search_result = gbizinfo.search_companies(name=search_name, page=1)

        companies = []
        if isinstance(search_result, dict):
            companies = search_result.get("companies", [])
        elif isinstance(search_result, list):
            companies = search_result

        # 閉鎖済み・組合・子会社を除外し、最も一致する企業を選択
        best_match = None
        for c in companies:
            status = c.get("status", "")
            if status == "閉鎖":
                continue
            cname = c.get("name", "")
            # 労働組合・協同組合は除外
            if "組合" in cname or "協会" in cname or "財団" in cname:
                continue
            # 完全一致を最優先
            if search_name in cname and ("株式会社" in cname or "会社" in cname):
                best_match = c
                break
            # 部分一致のフォールバック
            if best_match is None:
                best_match = c

        if best_match:
            corp_num = best_match.get("corporate_number", "")
            if corp_num:
                _dynamic_corp_cache[ticker] = corp_num
                TICKER_TO_CORPORATE_NUMBER[ticker] = corp_num
                print(f"[Resolver] Dynamic: {ticker} ({company_name}) → {corp_num} ({best_match.get('name', '')})")
                return corp_num

    except Exception as e:
        print(f"[Resolver] Dynamic resolve failed for {ticker}: {e}")

    return None


@app.get("/api/v1/company/search", tags=["Company"])
async def search_companies(
    name: str = Query(description="企業名（部分一致検索）"),
    page: int = Query(default=1, ge=1, description="ページ番号"),
):
    """
    企業名で法人を検索する（gBizINFO 500万法人超）。

    部分一致で検索し、法人番号・企業名・所在地を返す。
    法人番号を使って `/company/{corporate_number}` で詳細取得可能。
    """
    result = gbizinfo.search_companies(name=name, page=page)
    return _wrap_response("gbizinfo", result)


@app.get("/api/v1/company/{identifier}", tags=["Company"])
async def get_company_profile(
    identifier: str = Path(description="法人番号（13桁）または銘柄コード（例: 7203, 7203.T）"),
    full: bool = Query(default=False, description="全情報統合（補助金+認定+特許+財務+調達）"),
):
    """
    企業プロフィールをgBizINFOから取得する。

    銘柄コード（4桁 or .T付き）または法人番号（13桁）で指定可能。
    `full=true` で補助金・認定・特許・財務・調達を統合した完全プロフィール。

    **銘柄コード → 法人番号の自動変換**: 主要30銘柄は自動マッピング。
    それ以外は法人番号を直接指定するか、`/company/search` で検索。
    """
    corp_num = _resolve_corporate_number(identifier)

    if full:
        result = gbizinfo.get_full_profile(corp_num)
    else:
        result = gbizinfo.get_company(corp_num)

    if not result:
        raise HTTPException(status_code=404, detail=f"Company not found: {identifier}")

    return _wrap_response("gbizinfo", result)


@app.get("/api/v1/company/{identifier}/subsidies", tags=["Company"])
async def get_company_subsidies(
    identifier: str = Path(description="法人番号（13桁）または銘柄コード"),
):
    """企業の補助金受給履歴を取得。政府からの資金援助は成長投資のシグナル。"""
    corp_num = _resolve_corporate_number(identifier)
    result = gbizinfo.get_subsidies(corp_num)
    return _wrap_response("gbizinfo", result)


@app.get("/api/v1/company/{identifier}/certifications", tags=["Company"])
async def get_company_certifications(
    identifier: str = Path(description="法人番号（13桁）または銘柄コード"),
):
    """企業の認定・届出情報を取得。DX認定・ISO等の政府認定履歴。"""
    corp_num = _resolve_corporate_number(identifier)
    result = gbizinfo.get_certifications(corp_num)
    return _wrap_response("gbizinfo", result)


@app.get("/api/v1/company/{identifier}/patents", tags=["Company"])
async def get_company_patents(
    identifier: str = Path(description="法人番号（13桁）または銘柄コード"),
):
    """企業の特許情報を取得。技術力の定量指標。"""
    corp_num = _resolve_corporate_number(identifier)
    result = gbizinfo.get_patents(corp_num)
    return _wrap_response("gbizinfo", result)


@app.get("/api/v1/company/{identifier}/finance", tags=["Company"])
async def get_company_finance(
    identifier: str = Path(description="法人番号（13桁）または銘柄コード"),
):
    """企業の財務情報を取得（gBizINFO由来）。"""
    corp_num = _resolve_corporate_number(identifier)
    result = gbizinfo.get_finance(corp_num)
    return _wrap_response("gbizinfo", result)


# ===========================
#  e-Stat 政府統計
# ===========================

@app.get("/api/v1/stats/series", tags=["Statistics"])
async def get_stat_series_list():
    """利用可能な統計系列の一覧を返す。"""
    return _wrap_response("e-stat", estat.get_available_series())


@app.get("/api/v1/stats/summary", tags=["Statistics"])
async def get_stats_summary():
    """
    主要マクロ統計サマリー — GDP・雇用・物価・生産・消費を一括取得。

    エージェントが日本経済の全体像を1コールで把握するためのエンドポイント。
    """
    result = estat.get_macro_summary()
    return _wrap_response("e-stat", result)


@app.get("/api/v1/stats/{series_id}", tags=["Statistics"])
async def get_stats(
    series_id: str = Path(description="統計系列ID（gdp, cpi, unemployment, industrial_production, retail_sales）"),
    limit: int = Query(default=20, ge=1, le=100, description="取得件数"),
):
    """
    指定した統計系列のデータを取得する。

    利用可能な系列: gdp, cpi, unemployment, industrial_production, retail_sales
    """
    result = estat.get_stats(series_id, limit=limit)
    return _wrap_response("e-stat", result)


@app.get("/api/v1/stats/search/{keyword}", tags=["Statistics"])
async def search_stats(
    keyword: str = Path(description="検索キーワード（例: GDP, 雇用, 物価）"),
    limit: int = Query(default=20, ge=1, le=50, description="取得件数"),
):
    """統計表をキーワードで検索する（750+統計テーブル）。"""
    result = estat.search_stats(keyword, limit=limit)
    return _wrap_response("e-stat", result)


# ===========================
#  J-Quants 市場データ
# ===========================

@app.get("/api/v1/stocks", tags=["Market"])
async def get_listed_stocks(
    market: str = Query(default=None, description="市場フィルタ（プライム/スタンダード/グロース）"),
):
    """
    全上場銘柄マスタを取得する（J-Quants）。

    銘柄コード、企業名、市場区分、セクター分類を含む。
    エージェントが銘柄のユニバースを把握するための基盤データ。
    """
    result = jquants.get_listed_stocks(market=market)
    return _wrap_response("jquants", result)


@app.get("/api/v1/earnings", tags=["Market"])
async def get_earnings_calendar(
    date_from: str = Query(default=None, description="開始日（YYYY-MM-DD）"),
    date_to: str = Query(default=None, description="終了日（YYYY-MM-DD）"),
):
    """
    決算発表予定カレンダーを取得する（J-Quants）。

    今後30日間の決算発表予定を一覧で返す。
    エージェントが決算イベントを先読みするためのデータ。
    """
    result = jquants.get_earnings_calendar(date_from=date_from, date_to=date_to)
    return _wrap_response("jquants", result)


@app.get("/api/v1/financials/{ticker}", tags=["Market"])
async def get_financial_statements(
    ticker: str = Path(description="銘柄コード（例: 7203 または 7203.T）"),
):
    """
    銘柄の財務サマリーを取得する（J-Quants）。

    売上・営業利益・純利益・EPS・BPS・自己資本比率と、
    会社予想（フォーキャスト）を含む。
    """
    result = jquants.get_financial_statements(ticker)
    return _wrap_response("jquants", result)


@app.get("/api/v1/prices/{ticker}", tags=["Market"])
async def get_stock_prices(
    ticker: str = Path(description="銘柄コード（例: 7203 または 7203.T）"),
    date_from: str = Query(default=None, description="開始日（YYYY-MM-DD）"),
    date_to: str = Query(default=None, description="終了日（YYYY-MM-DD）"),
    limit: int = Query(default=60, ge=1, le=200, description="返却バー数（デフォルト60）"),
):
    """
    株価ヒストリカルデータを取得する（J-Quants）。

    OHLCV（始値・高値・安値・終値・出来高）+ 調整済み価格。
    自動算出される付加データ:
    - 移動平均（5日/25日/75日）
    - 騰落率（日次/週次/月次）

    **注意**: Free Planのため12週間遅延データ。
    リアルタイム株価が必要な場合はPaid Planへのアップグレードが必要。
    """
    result = jquants.get_stock_prices(
        ticker, date_from=date_from, date_to=date_to, limit=limit
    )
    return _wrap_response("jquants", result)


@app.get("/api/v1/sectors", tags=["Market"])
async def get_sector_summary():
    """
    セクター別の銘柄数・市場構成を集計する。

    17業種分類・33業種分類・市場区分（プライム/スタンダード/グロース）
    別の銘柄数と構成比を返す。エージェントが日本市場の構造を把握するためのデータ。
    """
    result = jquants.get_sector_summary()
    return _wrap_response("jquants", result)


# ===========================
#  FRED 米国マクロ
# ===========================

@app.get("/api/v1/global/series", tags=["Global"])
async def get_fred_series_list():
    """利用可能なFRED系列一覧（米金利・CPI・雇用・日銀金利・ドル円等）。"""
    return _wrap_response("fred", fred.get_available_series())


@app.get("/api/v1/global/policy", tags=["Global"])
async def get_policy_summary():
    """
    日米金融政策サマリー — FF金利・日銀金利・米10Y/2Y・ドル円・VIX。

    エージェントが金融環境を1コールで把握するためのエンドポイント。
    """
    result = fred.get_policy_summary()
    return _wrap_response("fred", result)


@app.get("/api/v1/global/{series_key}", tags=["Global"])
async def get_fred_series(
    series_key: str = Path(description="系列キー（fed_funds_rate, boj_rate, usdjpy, us_cpi, vix等）"),
    limit: int = Query(default=30, ge=1, le=200, description="取得件数"),
):
    """指定したFRED系列のデータを取得する。"""
    result = fred.get_series(series_key, limit=limit)
    return _wrap_response("fred", result)


# ===========================
#  日銀短観
# ===========================

@app.get("/api/v1/tankan", tags=["BOJ"])
async def get_tankan_summary():
    """
    日銀短観サマリー — 大企業/中小企業 × 製造業/非製造業のDI一覧。

    日本経済の「体温計」。プラスは好況、マイナスは不況。
    大企業製造業DIが最も注目される。
    """
    result = boj.get_tankan_summary()
    return _wrap_response("boj", result)


@app.get("/api/v1/tankan/{series_id}", tags=["BOJ"])
async def get_tankan_series(
    series_id: str = Path(description="系列ID（tankan_large_manufacturing等）"),
    limit: int = Query(default=20, ge=1, le=100, description="取得期間数"),
):
    """
    短観の特定系列のデータを取得する。

    利用可能な系列:
    - tankan_large_manufacturing: 大企業製造業DI
    - tankan_large_nonmanufacturing: 大企業非製造業DI
    - tankan_small_manufacturing: 中小企業製造業DI
    - tankan_small_nonmanufacturing: 中小企業非製造業DI
    - tankan_capex_large: 大企業設備投資計画
    """
    result = boj.get_tankan(series_id=series_id, limit=limit)
    return _wrap_response("boj", result)


@app.get("/api/v1/tankan/series/list", tags=["BOJ"])
async def get_tankan_series_list():
    """利用可能な短観系列の一覧を返す。"""
    return _wrap_response("boj", boj.get_available_series())


# ===========================
#  JPX 投資部門別売買動向
# ===========================

@app.get("/api/v1/investor-flows", tags=["InvestorFlows"])
async def get_investor_flows():
    """
    JPX投資部門別売買動向 — 外国人投資家は日本株を買っているか？

    外国人・個人・信託銀行（GPIF代理）・事業法人の
    週次売買データ。市場方向の最強シグナル。
    毎週木曜日15:30更新。
    """
    result = jpx_investor.get_investor_flows()
    return _wrap_response("jpx", result)



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
    - 投資部門別売買動向（外国人・個人・信託銀行・事業法人のネットフロー）
    - セクター概況（市場区分別銘柄数）
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

    # 投資部門別売買動向（外国人投資家フロー）
    try:
        flows_data = jpx_investor.get_investor_flows()
        investor_summary = {}
        flows = flows_data.get("flows", {})
        for key in ["foreigners", "individuals", "trust_banks", "corporations"]:
            f = flows.get(key)
            if f and f.get("net") is not None:
                investor_summary[key] = {
                    "name": f.get("name_jp"),
                    "net": f["net"],
                    "signal": f.get("signal"),
                }
        investor_section = {
            "period": flows_data.get("period"),
            "key_flows": investor_summary,
            "highlights": flows_data.get("highlights", []),
        }
    except Exception:
        investor_section = {"error": "fetch_failed"}

    # セクター概況
    try:
        sector_data = jquants.get_sector_summary()
        sector_section = {
            "total_stocks": sector_data.get("total_stocks"),
            "market_distribution": sector_data.get("market_distribution", [])[:5],
        }
    except Exception:
        sector_section = None

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
        "investor_flows": investor_section,
        "sector_overview": sector_section,
    })


# ===========================
#  Japan Briefing — 全体ブリーフィング
# ===========================

@app.get("/api/v1/briefing", tags=["Intelligence"])
async def get_japan_briefing():
    """
    Japan Briefing — 日本市場の全体像を1コールで把握する最強エンドポイント。

    このエンドポイントは「今日の日本」を1回の呼び出しで完全に理解するために設計。
    AIエージェントが朝一に呼ぶべきツール。

    含まれるデータ:
    - マクロ6指標（日経・ドル円・VIX・原油・金・S&P500）
    - 日米金融政策（FF金利・日銀金利・米10Y/2Y利回り）
    - 日銀短観DI（大企業製造業・非製造業）
    - 景気ウォッチャーDI
    - 直近の適時開示ハイライト
    - 投資部門別売買動向
    """
    result = {}

    # 1. マクロ指標
    try:
        result["market"] = {
            "indicators": macro.get_indicators(),
            "events": macro.detect_events(),
        }
    except Exception:
        result["market"] = {"error": "fetch_failed"}

    # 2. 金融政策
    try:
        result["policy"] = fred.get_policy_summary()
    except Exception:
        result["policy"] = {"error": "fetch_failed"}

    # 3. 短観DI
    try:
        tankan_data = boj.get_tankan_summary()
        tankan_brief = {}
        for item in tankan_data.get("items", []):
            lv = item.get("latest_value")
            if isinstance(lv, tuple):
                lv = lv[0]
            tankan_brief[item["id"]] = {
                "label": item["label"],
                "di": lv,
                "trend": item.get("trend", "unknown"),
            }
        result["tankan"] = tankan_brief
    except Exception:
        result["tankan"] = {"error": "fetch_failed"}

    # 4. 景気ウォッチャー
    try:
        ew = estat.get_stats("economy_watchers", limit=3)
        ew_data = ew.get("data", [])
        if ew_data:
            result["economy_watchers"] = {
                "latest_di": ew_data[0].get("value"),
                "period": ew_data[0].get("time"),
                "previous_di": ew_data[1].get("value") if len(ew_data) > 1 else None,
                "label": "景気ウォッチャー調査DI（現状判断）",
            }
        else:
            result["economy_watchers"] = {"error": "no_data"}
    except Exception:
        result["economy_watchers"] = {"error": "fetch_failed"}

    # 5. 適時開示ハイライト
    try:
        disclosures = tdnet.get_disclosures(days=1)
        notable = []
        for d in disclosures:
            imp = d.get("impact", "NEUTRAL")
            if imp in ("POSITIVE", "NEGATIVE"):
                if not d.get("company_name"):
                    d["company_name"] = resolve_name(d["ticker"])
                notable.append({
                    "ticker": d["ticker"],
                    "company": d["company_name"],
                    "title": d["title"][:60],
                    "impact": imp,
                })
        result["disclosures"] = {
            "today_count": len(disclosures),
            "notable": notable[:5],
        }
    except Exception:
        result["disclosures"] = {"error": "fetch_failed"}

    # 6. 投資部門別
    try:
        result["investor_flows"] = jpx_investor.get_investor_flows()
    except Exception:
        result["investor_flows"] = {"error": "fetch_failed"}

    return _wrap_response("japan_briefing", {
        "timestamp": datetime.now().isoformat(),
        "description": "Complete Japan market briefing — use this as your daily starting point",
        **result,
    })


# ===========================
#  クロスソース企業インテリジェンス
# ===========================

@app.get("/api/v1/intelligence/{ticker}", tags=["Intelligence"])
async def get_company_intelligence(
    ticker: str = Path(description="銘柄コード（例: 7203 または 7203.T）"),
):
    """
    企業インテリジェンス — 全ソースを横断統合した包括的企業分析。

    1回のAPIコールで以下を統合取得:
    - gBizINFO: 企業プロフィール、補助金、認定、特許、調達
    - J-Quants: 最新財務（売上・利益・EPS）+ 会社予想
    - J-Quants: 株価ヒストリカル（最新価格・移動平均・騰落率）
    - TDnet: 直近の適時開示（業績修正・M&A等）
    - EDINET: 大量保有報告（機関投資家の持分変動）
    - FRED: 関連マクロ環境（ドル円・VIX）

    エージェントの最強ツール:
    「この企業について全てを教えて」を1回で完結させる。
    """
    normalized = _normalize_ticker(ticker)
    company_name = resolve_name(normalized)

    # --- 並列データ収集 ---
    result = {
        "ticker": normalized,
        "company_name": company_name,
        "timestamp": datetime.now().isoformat(),
    }

    # 1. gBizINFO企業プロフィール
    try:
        corp_num = _resolve_corporate_number(ticker)
        profile = gbizinfo.get_company(corp_num) or {}
        certs = gbizinfo.get_certifications(corp_num)
        result["profile"] = {
            "name": profile.get("name", company_name),
            "corporate_number": corp_num,
            "capital_stock": profile.get("capital_stock"),
            "employee_number": profile.get("employee_number"),
            "date_of_establishment": profile.get("date_of_establishment"),
            "business_summary": profile.get("business_summary"),
            "location": profile.get("location"),
            "representative_name": profile.get("representative_name"),
            "certification_count": len(certs),
            "patent_count": profile.get("patent_count", 0),
            "source": "gbizinfo",
        }
    except Exception:
        result["profile"] = {"name": company_name, "source": "ticker_resolver"}

    # 2. J-Quants財務
    try:
        financials = jquants.get_financial_statements(ticker)
        if financials:
            latest = financials[0]
            result["financials"] = {
                "period": f"{latest.get('period_start', '')} ~ {latest.get('period_end', '')}",
                "net_sales": latest.get("net_sales"),
                "operating_profit": latest.get("operating_profit"),
                "net_income": latest.get("net_income"),
                "eps": latest.get("eps"),
                "bps": latest.get("bps"),
                "equity_ratio": latest.get("equity_ratio"),
                "dividend_annual": latest.get("dividend_annual"),
                "forecast_net_sales": latest.get("forecast_net_sales"),
                "forecast_eps": latest.get("forecast_eps"),
                "periods_available": len(financials),
                "source": "jquants",
            }
        else:
            result["financials"] = None
    except Exception:
        result["financials"] = None

    # 3. TDnet直近開示
    try:
        disclosures = tdnet.get_disclosures(days=30)
        company_disclosures = [
            {
                "title": d["title"][:80],
                "category": d.get("category", ""),
                "impact": d.get("impact", ""),
                "date": d.get("date", ""),
            }
            for d in disclosures
            if d.get("ticker", "").replace(".T", "") == normalized.replace(".T", "")
        ]
        result["disclosures"] = {
            "count": len(company_disclosures),
            "items": company_disclosures[:10],
            "source": "tdnet",
        }
    except Exception:
        result["disclosures"] = {"count": 0, "items": [], "source": "tdnet"}

    # 4. EDINET大量保有
    try:
        holdings = edinet.get_holdings(days=90)
        ticker_code = normalized.replace(".T", "")
        company_holdings = [
            {
                "filer_name": h.get("filer_name", ""),
                "title": h.get("title", ""),
                "date": h.get("date", ""),
                "is_correction": h.get("is_correction", False),
            }
            for h in holdings
            if h.get("code", "") == ticker_code
        ]
        result["holdings"] = {
            "count": len(company_holdings),
            "items": company_holdings[:10],
            "source": "edinet",
        }
    except Exception:
        result["holdings"] = {"count": 0, "items": [], "source": "edinet"}

    # 5. マクロ環境コンテキスト
    try:
        policy = fred.get_policy_summary()
        result["macro_context"] = {
            "usdjpy": policy.get("series", {}).get("usdjpy", {}).get("latest_value"),
            "vix": policy.get("series", {}).get("vix", {}).get("latest_value"),
            "fed_rate": policy.get("series", {}).get("fed_funds_rate", {}).get("latest_value"),
            "boj_rate": policy.get("series", {}).get("boj_rate", {}).get("latest_value"),
            "source": "fred",
        }
    except Exception:
        result["macro_context"] = None

    # 6. 株価ヒストリカル（J-Quants Free Plan: 12週間遅延）
    try:
        prices = jquants.get_stock_prices(ticker, limit=5)
        if prices and not prices.get("error"):
            result["stock_price"] = {
                "latest": prices.get("latest_price"),
                "moving_averages": prices.get("moving_averages"),
                "price_change": prices.get("price_change"),
                "period": prices.get("period"),
                "note": prices.get("note"),
                "source": "jquants",
            }
        else:
            result["stock_price"] = None
    except Exception:
        result["stock_price"] = None

    return _wrap_response("intelligence", result)


# ===========================
#  エントリポイント
# ===========================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
