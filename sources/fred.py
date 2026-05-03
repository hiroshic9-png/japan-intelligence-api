"""
Japan Intelligence — FRED データソース

米連邦準備制度 FRED API を利用して
米国マクロ経済指標 + 日本関連指標を取得する。

日米金融政策の連動は日本市場に直接影響するため、
FRBの金利・インフレ・雇用データは日本株分析に必須。
日銀政策金利もFREDに収録されており、一元取得が可能。
"""
from __future__ import annotations
import os
import requests
from typing import Optional
from datetime import datetime
from core.config import FRED_CONFIG


# エージェントにとって高価値な系列
FRED_SERIES = {
    # === 米国マクロ ===
    "fed_funds_rate": {
        "series_id": "FEDFUNDS",
        "label": "米FF金利（政策金利）",
        "category": "us_monetary",
    },
    "us_cpi": {
        "series_id": "CPIAUCSL",
        "label": "米CPI（都市部消費者物価）",
        "category": "us_prices",
    },
    "us_unemployment": {
        "series_id": "UNRATE",
        "label": "米失業率",
        "category": "us_employment",
    },
    "us_10y_yield": {
        "series_id": "GS10",
        "label": "米10年国債利回り",
        "category": "us_rates",
    },
    "us_2y_yield": {
        "series_id": "GS2",
        "label": "米2年国債利回り",
        "category": "us_rates",
    },
    # === 日本関連（FRED収録） ===
    "boj_rate": {
        "series_id": "IRSTCI01JPM156N",
        "label": "日銀政策金利（短期）",
        "category": "jp_monetary",
    },
    "jp_cpi": {
        "series_id": "JPNCPIALLMINMEI",
        "label": "日本CPI",
        "category": "jp_prices",
    },
    "usdjpy": {
        "series_id": "DEXJPUS",
        "label": "ドル円レート",
        "category": "fx",
    },
    # === グローバルリスク ===
    "vix": {
        "series_id": "VIXCLS",
        "label": "VIX（恐怖指数）",
        "category": "risk",
    },
    "oil_wti": {
        "series_id": "DCOILWTICO",
        "label": "WTI原油価格",
        "category": "commodities",
    },
}


class FredSource:
    """FRED APIクライアント — 米国+日本マクロ経済指標"""

    def __init__(self):
        self.api_base = FRED_CONFIG['api_base']
        self.api_key = FRED_CONFIG['api_key']
        self._cache = {}
        self._cache_ttl = FRED_CONFIG['cache_ttl_seconds']

    def get_available_series(self) -> list[dict]:
        """利用可能な系列一覧を返す。"""
        return [
            {
                "id": key,
                "series_id": val["series_id"],
                "label": val["label"],
                "category": val["category"],
            }
            for key, val in FRED_SERIES.items()
        ]

    def get_series(self, series_key: str, limit: int = 30) -> dict:
        """
        指定した系列の最新データを取得。

        Args:
            series_key: 系列キー（fed_funds_rate, us_cpi, boj_rate, usdjpy等）
            limit: 取得件数
        """
        if series_key not in FRED_SERIES:
            return {
                "error": f"Unknown series: {series_key}",
                "available": list(FRED_SERIES.keys()),
            }

        series = FRED_SERIES[series_key]
        cache_key = f"fred:{series_key}:{limit}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        data = self._fetch_observations(series["series_id"], limit=limit)
        if data is None:
            return {"series": series_key, "label": series["label"], "data": [], "error": "fetch_failed"}

        result = {
            "series": series_key,
            "fred_series_id": series["series_id"],
            "label": series["label"],
            "category": series["category"],
            "data": data,
            "count": len(data),
            "source": "fred",
        }

        self._set_cache(cache_key, result)
        return result

    def get_policy_summary(self) -> dict:
        """
        日米金融政策サマリーを一括取得。
        エージェントが金融環境を1コールで把握するためのエンドポイント。
        """
        cache_key = "fred:policy_summary"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        key_series = ["fed_funds_rate", "boj_rate", "us_10y_yield", "us_2y_yield", "usdjpy", "vix"]
        summary = {}

        for key in key_series:
            data = self.get_series(key, limit=3)
            latest = data.get("data", [{}])
            summary[key] = {
                "label": data.get("label", ""),
                "latest_value": latest[0].get("value") if latest else None,
                "latest_date": latest[0].get("date") if latest else None,
                "previous_value": latest[1].get("value") if len(latest) > 1 else None,
            }

        result = {
            "series_count": len(summary),
            "series": summary,
            "source": "fred",
        }

        self._set_cache(cache_key, result)
        return result

    # === Private Methods ===

    def _fetch_observations(self, series_id: str, limit: int = 30) -> Optional[list[dict]]:
        """FRED APIから観測データを取得。"""
        if not self.api_key:
            print("[FRED] WARNING: FRED_API_KEY not set")
            return None

        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": limit,
        }

        try:
            resp = requests.get(
                f"{self.api_base}/series/observations",
                params=params,
                timeout=15,
            )
            if resp.status_code != 200:
                print(f"[FRED] API error {resp.status_code}: {series_id}")
                return None

            data = resp.json()
            observations = data.get("observations", [])

            results = []
            for obs in observations:
                val = obs.get("value", ".")
                results.append({
                    "date": obs.get("date", ""),
                    "value": float(val) if val != "." else None,
                })

            return results

        except Exception as e:
            print(f"[FRED] Fetch error: {e}")
            return None

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
