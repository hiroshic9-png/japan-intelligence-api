"""
Japan Intelligence — J-Quants データソース

JPX J-Quants API (Free Plan) を利用して
銘柄マスタ、決算カレンダー、財務サマリーを取得する。

Free Planの制約:
  - 直近12週間の株価データは取得不可（ヒストリカルのみ）
  - 信用取引データ、指数データは対象外
  - 銘柄一覧、決算予定、財務サマリーは取得可能

事業が軌道に乗った段階でPaid Planにアップグレードし、
リアルタイム株価・信用取引データを追加する想定。
"""
from __future__ import annotations
import os
import requests
from typing import Optional
from datetime import datetime, timedelta
from core.config import JQUANTS_CONFIG


class JQuantsSource:
    """J-Quants API (Free) クライアント — 銘柄マスタ・決算カレンダー"""

    def __init__(self):
        self.api_base = JQUANTS_CONFIG['api_base']
        self.refresh_token = JQUANTS_CONFIG['refresh_token']
        self._id_token = None
        self._id_token_expiry = None
        self._cache = {}
        self._cache_ttl = JQUANTS_CONFIG['cache_ttl_seconds']

    def get_listed_stocks(self, market: str = None) -> list[dict]:
        """
        上場銘柄一覧を取得。

        Args:
            market: 市場フィルタ（"プライム", "スタンダード", "グロース"）
        """
        cache_key = f"listed:{market or 'all'}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        token = self._get_id_token()
        if not token:
            return []

        headers = {"Authorization": f"Bearer {token}"}

        try:
            resp = requests.get(
                f"{self.api_base}/listed/info",
                headers=headers,
                timeout=15,
            )
            if resp.status_code != 200:
                print(f"[J-Quants] Listed stocks error {resp.status_code}")
                return []

            data = resp.json()
            stocks = data.get("info", [])

            results = []
            for s in stocks:
                entry = {
                    "ticker": s.get("Code", ""),
                    "name": s.get("CompanyName", ""),
                    "market": s.get("MarketCodeName", ""),
                    "sector_17": s.get("Sector17CodeName", ""),
                    "sector_33": s.get("Sector33CodeName", ""),
                    "scale_category": s.get("ScaleCategory", ""),
                    "update_date": s.get("UpdateDate", ""),
                    "source": "jquants",
                }

                if market and entry["market"] != market:
                    continue
                results.append(entry)

            self._set_cache(cache_key, results)
            return results

        except Exception as e:
            print(f"[J-Quants] Listed stocks error: {e}")
            return []

    def get_earnings_calendar(self, date_from: str = None, date_to: str = None) -> list[dict]:
        """
        決算発表予定日を取得。

        Args:
            date_from: 開始日（YYYY-MM-DD）
            date_to: 終了日（YYYY-MM-DD）
        """
        if not date_from:
            date_from = datetime.now().strftime("%Y-%m-%d")
        if not date_to:
            date_to = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

        cache_key = f"earnings:{date_from}:{date_to}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        token = self._get_id_token()
        if not token:
            return []

        headers = {"Authorization": f"Bearer {token}"}
        params = {"from": date_from, "to": date_to}

        try:
            resp = requests.get(
                f"{self.api_base}/fins/announcement",
                headers=headers,
                params=params,
                timeout=15,
            )
            if resp.status_code != 200:
                print(f"[J-Quants] Earnings calendar error {resp.status_code}")
                return []

            data = resp.json()
            announcements = data.get("announcement", [])

            results = []
            for a in announcements:
                results.append({
                    "ticker": a.get("Code", ""),
                    "company_name": a.get("CompanyName", ""),
                    "date": a.get("Date", ""),
                    "fiscal_year_end": a.get("FiscalYearEnd", ""),
                    "section": a.get("Section", ""),
                    "source": "jquants",
                })

            results.sort(key=lambda x: x.get("date") or "", reverse=False)
            self._set_cache(cache_key, results)
            return results

        except Exception as e:
            print(f"[J-Quants] Earnings calendar error: {e}")
            return []

    def get_financial_statements(self, ticker: str) -> list[dict]:
        """
        銘柄の財務サマリーを取得。

        Args:
            ticker: 銘柄コード（例: "72030"）— J-Quantsは5桁コード
        """
        # 4桁→5桁変換
        code = ticker.replace(".T", "")
        if len(code) == 4:
            code = code + "0"

        cache_key = f"fins:{code}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        token = self._get_id_token()
        if not token:
            return []

        headers = {"Authorization": f"Bearer {token}"}
        params = {"code": code}

        try:
            resp = requests.get(
                f"{self.api_base}/fins/statements",
                headers=headers,
                params=params,
                timeout=15,
            )
            if resp.status_code != 200:
                print(f"[J-Quants] Financial statements error {resp.status_code}")
                return []

            data = resp.json()
            statements = data.get("statements", [])

            results = []
            for s in statements:
                results.append({
                    "ticker": ticker,
                    "disclosed_date": s.get("DisclosedDate", ""),
                    "type_of_document": s.get("TypeOfDocument", ""),
                    "net_sales": s.get("NetSales"),
                    "operating_profit": s.get("OperatingProfit"),
                    "ordinary_profit": s.get("OrdinaryProfit"),
                    "profit": s.get("Profit"),
                    "eps": s.get("EarningsPerShare"),
                    "total_assets": s.get("TotalAssets"),
                    "equity": s.get("Equity"),
                    "equity_to_asset_ratio": s.get("EquityToAssetRatio"),
                    "bps": s.get("BookValuePerShare"),
                    "forecast_net_sales": s.get("ForecastNetSales"),
                    "forecast_operating_profit": s.get("ForecastOperatingProfit"),
                    "forecast_ordinary_profit": s.get("ForecastOrdinaryProfit"),
                    "forecast_profit": s.get("ForecastProfit"),
                    "forecast_eps": s.get("ForecastEarningsPerShare"),
                    "source": "jquants",
                })

            results.sort(key=lambda x: x.get("disclosed_date") or "", reverse=True)
            self._set_cache(cache_key, results)
            return results

        except Exception as e:
            print(f"[J-Quants] Financial statements error: {e}")
            return []

    # === Authentication ===

    def _get_id_token(self) -> Optional[str]:
        """IDトークンを取得（refresh_tokenから）。有効期限内ならキャッシュ。"""
        if self._id_token and self._id_token_expiry:
            if datetime.now() < self._id_token_expiry:
                return self._id_token

        if not self.refresh_token:
            print("[J-Quants] WARNING: JQUANTS_REFRESH_TOKEN not set")
            return None

        try:
            resp = requests.post(
                f"{self.api_base}/token/auth_refresh",
                params={"refreshtoken": self.refresh_token},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                self._id_token = data.get("idToken")
                # IDトークンは24時間有効だが、余裕を持って23時間で更新
                self._id_token_expiry = datetime.now() + timedelta(hours=23)
                return self._id_token
            else:
                print(f"[J-Quants] Token refresh error {resp.status_code}: {resp.text}")
                return None
        except Exception as e:
            print(f"[J-Quants] Token error: {e}")
            return None

    # === Cache ===

    def _get_cache(self, key: str):
        if key in self._cache:
            entry = self._cache[key]
            elapsed = (datetime.now() - entry["time"]).total_seconds()
            if elapsed < self._cache_ttl:
                return entry["data"]
            del self._cache[key]
        return None

    def _set_cache(self, key: str, data):
        self._cache[key] = {"data": data, "time": datetime.now()}
