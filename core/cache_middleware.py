"""
Japan Intelligence — レスポンスキャッシュミドルウェア

ソース特性別TTLでHTTPレスポンスをキャッシュし、
Cache-Controlヘッダーを自動付与する。

設計思想:
  - TDnet（適時開示）: 5分（リアルタイム性重視）
  - EDINET（大量保有）: 6時間（日次更新）
  - gBizINFO（企業情報）: 24時間（低頻度更新）
  - e-Stat（政府統計）: 6時間（月次更新メイン）
  - J-Quants（市場データ）: 12時間（日次更新）
  - FRED（米国マクロ）: 1時間（経済指標は頻繁に参照される）
  - BOJ（短観）: 6時間（四半期更新）
  - JPX（投資部門別）: 12時間（週次更新）
  - Macro（マクロ指標）: 5分（リアルタイム性重視）
  - Intelligence（ブリーフィング等）: 10分（複合ソース）
  - Interpreter（AI解釈）: キャッシュなし（毎回新規生成）
"""
import hashlib
import time
from datetime import datetime
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse


# === ソース特性別TTL定義（秒） ===
CACHE_TTL_MAP = {
    # パスプレフィックス → (max-age秒, stale-while-revalidate秒)
    "/api/v1/disclosures": (300, 60),       # TDnet: 5分 + 1分stale
    "/api/v1/holdings": (21600, 600),        # EDINET: 6時間
    "/api/v1/company": (86400, 3600),        # gBizINFO: 24時間
    "/api/v1/stats": (21600, 600),           # e-Stat: 6時間
    "/api/v1/stocks": (43200, 1800),         # J-Quants銘柄マスタ: 12時間
    "/api/v1/earnings": (43200, 1800),       # J-Quants決算: 12時間
    "/api/v1/financials": (43200, 1800),     # J-Quants財務: 12時間
    "/api/v1/prices": (43200, 1800),          # J-Quants株価: 12時間（Free Plan遅延データ）
    "/api/v1/sectors": (43200, 1800),          # J-Quantsセクター: 12時間
    "/api/v1/global": (3600, 300),           # FRED: 1時間
    "/api/v1/tankan": (21600, 600),          # BOJ短観: 6時間
    "/api/v1/investor-flows": (43200, 1800), # JPX: 12時間
    "/api/v1/macro": (300, 60),              # マクロ: 5分
    "/api/v1/briefing": (600, 120),          # ブリーフィング: 10分
    "/api/v1/market/snapshot": (600, 120),   # スナップショット: 10分
    "/api/v1/intelligence": (600, 120),      # 企業インテリジェンス: 10分
    "/api/v1/ticker": (86400, 3600),         # ティッカー解決: 24時間
    "/api/v1/health": (60, 10),              # ヘルス: 1分
}

# キャッシュしないパス
NO_CACHE_PATHS = {"/api/v1/interpret"}


def _get_cache_ttl(path: str) -> Optional[tuple]:
    """パスに基づいてキャッシュTTLを取得する"""
    if path in NO_CACHE_PATHS:
        return None

    # 最長一致で検索
    best_match = None
    best_len = 0
    for prefix, ttl in CACHE_TTL_MAP.items():
        if path.startswith(prefix) and len(prefix) > best_len:
            best_match = ttl
            best_len = len(prefix)

    return best_match


def _generate_etag(body: bytes) -> str:
    """レスポンスボディからETagを生成"""
    return f'"{hashlib.md5(body).hexdigest()}"'


class CacheControlMiddleware(BaseHTTPMiddleware):
    """
    HTTPレスポンスにCache-Control / ETag / Last-Modified ヘッダーを付与する。
    
    - エンドポイント特性に応じたmax-ageを自動設定
    - ETagによる304 Not Modified対応
    - stale-while-revalidateでバックグラウンド再検証
    """

    async def dispatch(self, request: Request, call_next):
        # GETリクエストのみキャッシュ対象
        if request.method != "GET":
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            return response

        path = request.url.path
        cache_config = _get_cache_ttl(path)

        # キャッシュ対象外
        if cache_config is None:
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            return response

        max_age, stale_revalidate = cache_config

        # ETagチェック（If-None-Match）
        client_etag = request.headers.get("If-None-Match")

        response = await call_next(request)

        # レスポンスボディを読み取ってETag生成
        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        etag = _generate_etag(body)

        # 304 Not Modified
        if client_etag and client_etag == etag:
            return Response(
                status_code=304,
                headers={
                    "ETag": etag,
                    "Cache-Control": f"public, max-age={max_age}, stale-while-revalidate={stale_revalidate}",
                },
            )

        # 通常レスポンス + キャッシュヘッダー
        return Response(
            content=body,
            status_code=response.status_code,
            headers={
                **dict(response.headers),
                "Cache-Control": f"public, max-age={max_age}, stale-while-revalidate={stale_revalidate}",
                "ETag": etag,
                "X-Cache-TTL": f"{max_age}s",
                "Vary": "X-API-Key",
            },
            media_type=response.media_type,
        )
