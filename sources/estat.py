"""
Japan Intelligence — e-Stat データソース

政府統計の総合窓口 e-Stat API を利用して
GDP・雇用・物価・産業統計等の政府統計を構造化取得する。

750+の統計テーブルからエージェントが必要とする
マクロ経済指標を自動取得し、市場環境の定量的裏付けを提供。
"""
from __future__ import annotations
import os
import requests
from typing import Optional
from datetime import datetime
from core.config import ESTAT_CONFIG


# 主要統計の系列定義（エージェントにとって高価値なもの）
ESTAT_SERIES = {
    "gdp": {
        "statsDataId": "0003109741",  # 国民経済計算 四半期GDP
        "label": "GDP（国内総生産）",
        "category": "economy",
    },
    "cpi": {
        "statsDataId": "0003427113",  # 消費者物価指数
        "label": "消費者物価指数（CPI）",
        "category": "prices",
    },
    "unemployment": {
        "statsDataId": "0003023501",  # 完全失業率
        "label": "完全失業率",
        "category": "employment",
    },
    "industrial_production": {
        "statsDataId": "0003126843",  # 鉱工業生産指数
        "label": "鉱工業生産指数",
        "category": "industry",
    },
    "retail_sales": {
        "statsDataId": "0003127148",  # 商業動態統計（小売業）
        "label": "小売業販売額",
        "category": "consumption",
    },
    # --- Wave 1 拡張 ---
    "economy_watchers": {
        "statsDataId": "0003348423",  # 景気ウォッチャー調査 季節調整値DI
        "label": "景気ウォッチャー調査（DI）",
        "category": "sentiment",
    },
    "economy_watchers_regional": {
        "statsDataId": "0003348424",  # 景気ウォッチャー調査 地域別DI
        "label": "景気ウォッチャー調査（地域別DI）",
        "category": "sentiment",
    },
    "household_spending": {
        "statsDataId": "0003343671",  # 家計調査 二人以上世帯 消費支出
        "label": "家計調査（消費支出）",
        "category": "consumption",
    },
    "trade_exports": {
        "statsDataId": "0003228190",  # 貿易統計 概況品別輸出
        "label": "貿易統計（輸出）",
        "category": "trade",
    },
    "trade_imports": {
        "statsDataId": "0003228199",  # 貿易統計 概況品別輸入
        "label": "貿易統計（輸入）",
        "category": "trade",
    },
}


class EStatSource:
    """e-Stat APIクライアント — 政府統計データの構造化取得"""

    def __init__(self):
        self.api_base = ESTAT_CONFIG['api_base']
        self.app_id = ESTAT_CONFIG['app_id']
        self._cache = {}
        self._cache_ttl = ESTAT_CONFIG['cache_ttl_seconds']

    def get_available_series(self) -> list[dict]:
        """利用可能な統計系列の一覧を返す。"""
        return [
            {
                "id": key,
                "label": val["label"],
                "category": val["category"],
                "stats_data_id": val["statsDataId"],
            }
            for key, val in ESTAT_SERIES.items()
        ]

    def get_stats(self, series_id: str, limit: int = 20) -> dict:
        """
        指定した統計系列の最新データを取得。

        Args:
            series_id: 系列ID（gdp, cpi, unemployment, industrial_production, retail_sales）
            limit: 取得件数
        Returns:
            構造化された統計データ
        """
        if series_id not in ESTAT_SERIES:
            return {
                "error": f"Unknown series: {series_id}",
                "available": list(ESTAT_SERIES.keys()),
            }

        series = ESTAT_SERIES[series_id]
        cache_key = f"estat:{series_id}:{limit}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        data = self._fetch_stats_data(series["statsDataId"], limit=limit)
        if not data:
            return {"series": series_id, "label": series["label"], "data": [], "error": "fetch_failed"}

        result = {
            "series": series_id,
            "label": series["label"],
            "category": series["category"],
            "data": data,
            "count": len(data),
            "source": "e-stat",
        }

        self._set_cache(cache_key, result)
        return result

    def get_macro_summary(self) -> dict:
        """
        主要マクロ統計のサマリーを一括取得。
        エージェントが1コールで日本経済の全体像を掴むためのエンドポイント。
        """
        cache_key = "estat:macro_summary"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        summary = {}
        for series_id in ESTAT_SERIES:
            stats = self.get_stats(series_id, limit=5)
            summary[series_id] = {
                "label": stats.get("label", ""),
                "category": stats.get("category", ""),
                "latest": stats.get("data", [{}])[0] if stats.get("data") else None,
                "count": stats.get("count", 0),
            }

        result = {
            "series_count": len(summary),
            "series": summary,
            "source": "e-stat",
        }

        self._set_cache(cache_key, result)
        return result

    def search_stats(self, keyword: str, limit: int = 20) -> list[dict]:
        """
        キーワードで統計表を検索する。

        Args:
            keyword: 検索キーワード（例: "GDP", "雇用", "物価"）
            limit: 取得件数上限
        """
        if not self.app_id:
            return []

        params = {
            "appId": self.app_id,
            "searchWord": keyword,
            "limit": limit,
            "lang": "J",
        }

        try:
            resp = requests.get(
                f"{self.api_base}/getStatsList",
                params=params,
                timeout=15,
            )
            if resp.status_code != 200:
                print(f"[e-Stat] Search error {resp.status_code}")
                return []

            data = resp.json()
            result = data.get("GET_STATS_LIST", {}).get("DATALIST_INF", {})
            tables = result.get("TABLE_INF", [])

            if isinstance(tables, dict):
                tables = [tables]

            return [
                {
                    "stats_data_id": t.get("@id", ""),
                    "title": self._extract_text(t.get("TITLE", "")),
                    "survey_name": self._extract_text(t.get("STAT_NAME", "")),
                    "government_dept": self._extract_text(t.get("GOV_ORG", "")),
                    "updated_date": t.get("UPDATED_DATE", ""),
                }
                for t in tables[:limit]
            ]

        except Exception as e:
            print(f"[e-Stat] Search error: {e}")
            return []

    # === Private Methods ===

    def _fetch_stats_data(self, stats_data_id: str, limit: int = 20) -> list[dict]:
        """e-Stat APIからデータ取得。"""
        if not self.app_id:
            print("[e-Stat] WARNING: ESTAT_APP_ID not set")
            return []

        params = {
            "appId": self.app_id,
            "statsDataId": stats_data_id,
            "metaGetFlg": "N",
            "limit": limit,
            "lang": "J",
        }

        try:
            resp = requests.get(
                f"{self.api_base}/getStatsData",
                params=params,
                timeout=15,
            )
            if resp.status_code != 200:
                print(f"[e-Stat] API error {resp.status_code}")
                return []

            data = resp.json()
            body = data.get("GET_STATS_DATA", {}).get("STATISTICAL_DATA", {})
            data_inf = body.get("DATA_INF", {})
            values = data_inf.get("VALUE", [])

            if isinstance(values, dict):
                values = [values]

            results = []
            for v in values:
                entry = {
                    "value": v.get("$", ""),
                    "time": v.get("@time", ""),
                    "unit": v.get("@unit", ""),
                }
                # カテゴリ属性を追加
                for key, val in v.items():
                    if key.startswith("@cat"):
                        entry[key] = val
                results.append(entry)

            return results

        except Exception as e:
            print(f"[e-Stat] Fetch error: {e}")
            return []

    def _extract_text(self, obj) -> str:
        """e-Stat APIのテキストフィールドを文字列に変換。"""
        if isinstance(obj, dict):
            return obj.get("$", str(obj))
        return str(obj) if obj else ""

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
