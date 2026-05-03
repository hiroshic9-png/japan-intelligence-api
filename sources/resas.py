"""
Japan Intelligence — RESAS データソース

内閣府 RESAS（地域経済分析システム）API を利用して
地域別の産業構造、人口動態、観光、雇用データを取得する。

「トヨタが強い愛知県の製造業は？」
「東京の情報通信業の付加価値額は？」
エージェントが地域×産業の掛け合わせ分析を行うための基盤データ。
"""
from __future__ import annotations
import os
import requests
from typing import Optional
from datetime import datetime
from core.config import RESAS_CONFIG


class ResasSource:
    """RESAS APIクライアント — 地域経済データの構造化取得"""

    def __init__(self):
        self.api_base = RESAS_CONFIG['api_base']
        self.api_key = RESAS_CONFIG['api_key']
        self._cache = {}
        self._cache_ttl = RESAS_CONFIG['cache_ttl_seconds']

    def get_prefectures(self) -> list[dict]:
        """都道府県一覧を取得。"""
        cache_key = "resas:prefs"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        data = self._api_get("/api/v1/prefectures")
        if not data:
            return []

        results = data.get("result", [])
        self._set_cache(cache_key, results)
        return results

    def get_industry_composition(self, pref_code: int, year: int = 2020) -> dict:
        """
        都道府県の産業構造（付加価値額ベース）を取得。

        Args:
            pref_code: 都道府県コード（1=北海道, 13=東京, 23=愛知, 47=沖縄）
            year: 対象年
        """
        cache_key = f"resas:industry:{pref_code}:{year}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        data = self._api_get(
            "/api/v1/industry/power/forArea",
            params={"prefCode": pref_code, "cityCode": "-", "sicCode": "-", "simcCode": "-", "year": year}
        )
        if not data:
            return {"pref_code": pref_code, "year": year, "industries": []}

        result = {
            "pref_code": pref_code,
            "year": year,
            "data": data.get("result", {}),
            "source": "resas",
        }

        self._set_cache(cache_key, result)
        return result

    def get_population(self, pref_code: int, city_code: str = "-") -> dict:
        """
        人口構成（年齢3区分）の推移を取得。

        Args:
            pref_code: 都道府県コード
            city_code: 市区町村コード（"-"で都道府県全体）
        """
        cache_key = f"resas:pop:{pref_code}:{city_code}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        data = self._api_get(
            "/api/v1/population/composition/perYear",
            params={"prefCode": pref_code, "cityCode": city_code}
        )
        if not data:
            return {"pref_code": pref_code, "data": []}

        result = {
            "pref_code": pref_code,
            "boundary_year": data.get("result", {}).get("boundaryYear"),
            "data": data.get("result", {}).get("data", []),
            "source": "resas",
        }

        self._set_cache(cache_key, result)
        return result

    def get_tourism(self, pref_code: int, year: int = 2022) -> dict:
        """
        観光データ（外国人・日本人の流入）を取得。

        Args:
            pref_code: 都道府県コード
            year: 対象年
        """
        cache_key = f"resas:tourism:{pref_code}:{year}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        data = self._api_get(
            "/api/v1/tourism/foreigners/forFrom",
            params={"prefCode": pref_code, "year": year}
        )
        if not data:
            return {"pref_code": pref_code, "year": year, "data": []}

        result = {
            "pref_code": pref_code,
            "year": year,
            "data": data.get("result", []),
            "source": "resas",
        }

        self._set_cache(cache_key, result)
        return result

    def get_wages(self, pref_code: int, sic_code: str = "-") -> dict:
        """
        一人当たり賃金の推移を取得。

        Args:
            pref_code: 都道府県コード
            sic_code: 産業分類コード（"-"で全産業）
        """
        cache_key = f"resas:wages:{pref_code}:{sic_code}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        data = self._api_get(
            "/api/v1/municipality/wages/perYear",
            params={"prefCode": pref_code, "sicCode": sic_code, "simcCode": "-"}
        )
        if not data:
            return {"pref_code": pref_code, "data": []}

        result = {
            "pref_code": pref_code,
            "sic_code": sic_code,
            "data": data.get("result", {}).get("data", []),
            "source": "resas",
        }

        self._set_cache(cache_key, result)
        return result

    # === Private Methods ===

    def _api_get(self, path: str, params: dict = None) -> Optional[dict]:
        """RESAS APIにGETリクエスト。"""
        if not self.api_key:
            print("[RESAS] WARNING: RESAS_API_KEY not set")
            return None

        url = f"{self.api_base}{path}"
        headers = {"X-API-KEY": self.api_key}

        try:
            resp = requests.get(url, headers=headers, params=params, timeout=15)
            if resp.status_code == 200:
                return resp.json()
            else:
                print(f"[RESAS] API error {resp.status_code}: {path}")
                return None
        except Exception as e:
            print(f"[RESAS] Request error: {e}")
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
