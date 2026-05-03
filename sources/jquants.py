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

    def get_stock_prices(self, ticker: str, date_from: str = None,
                         date_to: str = None, limit: int = 60) -> dict:
        """
        株価ヒストリカルデータを取得（OHLCV + 調整済み価格）。

        Free Plan: 12週間遅延データ。直近の株価は取得不可。
        トレンド分析用に5日/25日/75日移動平均を自動算出。

        Args:
            ticker: 銘柄コード（例: "7203", "7203.T"）
            date_from: 開始日（YYYY-MM-DD）。省略時は120営業日前
            date_to: 終了日（YYYY-MM-DD）。省略時はFree Plan上限
            limit: 返却件数（デフォルト60）
        """
        code = ticker.replace(".T", "")
        if len(code) == 4:
            code = code + "0"

        cache_key = f"prices:{code}:{date_from}:{date_to}:{limit}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        if not self.api_key:
            return {"ticker": ticker, "bars": [], "error": "no_api_key"}

        # Free Planは12週間前までのデータのみ
        if not date_to:
            date_to = (datetime.now() - timedelta(weeks=12)).strftime("%Y-%m-%d")
        if not date_from:
            date_from = (datetime.now() - timedelta(weeks=12 + 26)).strftime("%Y-%m-%d")

        try:
            resp = requests.get(
                f"{self.api_base}/equities/bars/daily",
                headers=self._headers(),
                params={"code": code, "from": date_from, "to": date_to},
                timeout=30,
            )
            if resp.status_code != 200:
                print(f"[J-Quants] Stock prices error {resp.status_code}: {resp.text[:200]}")
                return {"ticker": ticker, "bars": [], "error": f"api_error_{resp.status_code}"}

            data = resp.json()
            bars_raw = data.get("data", data.get("daily_quotes", []))

            bars = []
            for b in bars_raw:
                bars.append({
                    "date": b.get("Date", ""),
                    "open": b.get("AdjO") or b.get("O"),
                    "high": b.get("AdjH") or b.get("H"),
                    "low": b.get("AdjL") or b.get("L"),
                    "close": b.get("AdjC") or b.get("C"),
                    "volume": b.get("AdjVo") or b.get("Vo"),
                    "turnover": b.get("Va"),
                })

            # 移動平均算出
            closes = [b["close"] for b in bars if b["close"] is not None]
            ma_data = {}
            for period in [5, 25, 75]:
                if len(closes) >= period:
                    ma = sum(closes[-period:]) / period
                    ma_data[f"ma{period}"] = round(ma, 2)

            # 騰落率
            price_change = {}
            if len(bars) >= 2:
                latest = bars[-1]["close"]
                prev = bars[-2]["close"]
                if latest and prev and prev > 0:
                    price_change["daily_change_pct"] = round((latest - prev) / prev * 100, 2)
            if len(bars) >= 6:
                week_ago = bars[-6]["close"]
                latest = bars[-1]["close"]
                if latest and week_ago and week_ago > 0:
                    price_change["weekly_change_pct"] = round((latest - week_ago) / week_ago * 100, 2)
            if len(bars) >= 21:
                month_ago = bars[-21]["close"]
                latest = bars[-1]["close"]
                if latest and month_ago and month_ago > 0:
                    price_change["monthly_change_pct"] = round((latest - month_ago) / month_ago * 100, 2)

            # 直近limitバーのみ返却
            trimmed = bars[-limit:] if len(bars) > limit else bars

            result = {
                "ticker": ticker,
                "period": {"from": date_from, "to": date_to},
                "total_bars": len(bars),
                "returned_bars": len(trimmed),
                "latest_price": bars[-1] if bars else None,
                "moving_averages": ma_data,
                "price_change": price_change,
                "bars": trimmed,
                "note": "Free Plan: 12-week delayed data. For real-time prices, upgrade to Paid Plan.",
                "source": "jquants",
            }

            self._set_cache(cache_key, result)
            return result

        except Exception as e:
            print(f"[J-Quants] Stock prices error: {e}")
            return {"ticker": ticker, "bars": [], "error": str(e)}

    def get_sector_summary(self) -> dict:
        """
        セクター別の銘柄数・市場構成を集計する。

        銘柄マスタデータを活用し、17業種・33業種の分布を返す。
        エージェントが市場構造を把握するためのデータ。
        """
        cache_key = "sector_summary"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        stocks = self.get_listed_stocks()
        if not stocks:
            return {"error": "no_data"}

        # 17業種別集計
        sector17 = {}
        sector33 = {}
        market_dist = {}

        for s in stocks:
            s17 = s.get("sector_17", "不明")
            s33 = s.get("sector_33", "不明")
            mkt = s.get("market", "不明")

            sector17[s17] = sector17.get(s17, 0) + 1
            sector33[s33] = sector33.get(s33, 0) + 1
            market_dist[mkt] = market_dist.get(mkt, 0) + 1

        # ソート
        s17_sorted = sorted(sector17.items(), key=lambda x: x[1], reverse=True)
        s33_sorted = sorted(sector33.items(), key=lambda x: x[1], reverse=True)
        mkt_sorted = sorted(market_dist.items(), key=lambda x: x[1], reverse=True)

        result = {
            "total_stocks": len(stocks),
            "sector_17": [{"sector": k, "count": v, "pct": round(v / len(stocks) * 100, 1)} for k, v in s17_sorted],
            "sector_33": [{"sector": k, "count": v, "pct": round(v / len(stocks) * 100, 1)} for k, v in s33_sorted],
            "market_distribution": [{"market": k, "count": v, "pct": round(v / len(stocks) * 100, 1)} for k, v in mkt_sorted],
            "source": "jquants",
        }

        self._set_cache(cache_key, result)
        return result

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
