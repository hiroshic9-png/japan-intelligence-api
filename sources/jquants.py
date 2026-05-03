"""
Japan Intelligence — J-Quants データソース

JPX J-Quants API v2 (Free Plan) を利用して
銘柄マスタ、決算カレンダー、財務サマリーを取得する。

V2認証: x-api-key ヘッダーによるAPIキー方式。
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
    """J-Quants API v2 クライアント — 銘柄マスタ・決算カレンダー"""

    def __init__(self):
        self.api_base = JQUANTS_CONFIG['api_base']
        self.api_key = JQUANTS_CONFIG.get('api_key', '')
        self._cache = {}
        self._cache_ttl = JQUANTS_CONFIG['cache_ttl_seconds']

    def _headers(self) -> dict:
        """認証ヘッダーを返す。"""
        return {"x-api-key": self.api_key}

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

        if not self.api_key:
            print("[J-Quants] WARNING: JQUANTS_API_KEY not set")
            return []

        try:
            resp = requests.get(
                f"{self.api_base}/equities/master",
                headers=self._headers(),
                timeout=30,
            )
            if resp.status_code != 200:
                print(f"[J-Quants] Listed stocks error {resp.status_code}: {resp.text[:200]}")
                return []

            data = resp.json()
            stocks = data.get("data", [])

            results = []
            for s in stocks:
                entry = {
                    "ticker": s.get("Code", ""),
                    "name": s.get("CoName", ""),
                    "name_en": s.get("CoNameEn", ""),
                    "market": s.get("MktNm", ""),
                    "sector_17": s.get("S17Nm", ""),
                    "sector_33": s.get("S33Nm", ""),
                    "scale_category": s.get("ScaleCat", ""),
                    "margin": s.get("MrgnNm", ""),
                    "date": s.get("Date", ""),
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

        if not self.api_key:
            return []

        params = {"from": date_from, "to": date_to}

        try:
            resp = requests.get(
                f"{self.api_base}/fins/announcement",
                headers=self._headers(),
                params=params,
                timeout=15,
            )
            if resp.status_code != 200:
                print(f"[J-Quants] Earnings calendar error {resp.status_code}: {resp.text[:200]}")
                return []

            data = resp.json()
            announcements = data.get("data", data.get("announcement", []))

            results = []
            for a in announcements:
                results.append({
                    "ticker": a.get("Code", ""),
                    "company_name": a.get("CoName", a.get("CompanyName", "")),
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
            ticker: 銘柄コード（例: "7203", "7203.T"）— 5桁に自動変換
        """
        # 4桁→5桁変換
        code = ticker.replace(".T", "")
        if len(code) == 4:
            code = code + "0"

        cache_key = f"fins:{code}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        if not self.api_key:
            return []

        params = {"code": code}

        try:
            resp = requests.get(
                f"{self.api_base}/fins/summary",
                headers=self._headers(),
                params=params,
                timeout=15,
            )
            if resp.status_code != 200:
                print(f"[J-Quants] Financial statements error {resp.status_code}: {resp.text[:200]}")
                return []

            data = resp.json()
            statements = data.get("data", [])

            results = []
            for s in statements:
                # V2フィールド名にマッピング
                def _num(val):
                    """文字列数値をfloatに変換。空文字はNone。"""
                    if val is None or val == "":
                        return None
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        return None

                results.append({
                    "ticker": ticker,
                    "disclosed_date": s.get("DiscDate", ""),
                    "doc_type": s.get("DocType", ""),
                    "period_type": s.get("CurPerType", ""),
                    "period_start": s.get("CurPerSt", ""),
                    "period_end": s.get("CurPerEn", ""),
                    "net_sales": _num(s.get("Sales")),
                    "operating_profit": _num(s.get("OP")),
                    "ordinary_profit": _num(s.get("OdP")),
                    "net_income": _num(s.get("NP")),
                    "eps": _num(s.get("EPS")),
                    "total_assets": _num(s.get("TA")),
                    "equity": _num(s.get("Eq")),
                    "equity_ratio": _num(s.get("EqAR")),
                    "bps": _num(s.get("BPS")),
                    "cfo": _num(s.get("CFO")),
                    "dividend_annual": _num(s.get("DivAnn")),
                    "payout_ratio": _num(s.get("PayoutRatioAnn")),
                    # 会社予想（次期）
                    "forecast_net_sales": _num(s.get("NxFSales")),
                    "forecast_operating_profit": _num(s.get("NxFOP")),
                    "forecast_net_income": _num(s.get("NxFNp")),
                    "forecast_eps": _num(s.get("NxFEPS")),
                    "source": "jquants",
                })

            results.sort(key=lambda x: x.get("disclosed_date") or "", reverse=True)
            self._set_cache(cache_key, results)
            return results

        except Exception as e:
            print(f"[J-Quants] Financial statements error: {e}")
            return []

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
