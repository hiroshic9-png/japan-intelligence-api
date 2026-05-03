"""
Japan Intelligence — gBizINFO データソース

経済産業省 gBizINFO API v1 を利用して法人プロフィール、
補助金、認定、特許、財務、調達情報を取得・構造化する。

500万法人超の政府保有データに基づく企業インテリジェンス。
開示書類に現れない「裏側」— 補助金受給歴、政府認定、特許数は
隠れた成長シグナルとしてエージェントの分析精度を引き上げる。
"""
from __future__ import annotations
import os
import time
import requests
from typing import Optional
from datetime import datetime
from core.config import GBIZ_CONFIG


class GBizInfoSource:
    """gBizINFO APIクライアント — 企業の政府保有データを構造化取得"""

    def __init__(self):
        self.api_base = GBIZ_CONFIG['api_base']
        self.api_token = GBIZ_CONFIG['api_token']
        self._cache = {}
        self._cache_ttl = GBIZ_CONFIG['cache_ttl_seconds']

    def get_company(self, corporate_number: str) -> dict | None:
        """
        法人番号から企業プロフィールを取得。

        Args:
            corporate_number: 13桁の法人番号
        Returns:
            構造化された企業プロフィール or None
        """
        cache_key = f"company:{corporate_number}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        data = self._api_get(f"/hojin/{corporate_number}")
        if not data:
            return None

        infos = data.get("hojin-infos", [])
        if not infos:
            return None

        raw = infos[0]
        result = {
            "corporate_number": raw.get("corporate_number", ""),
            "name": raw.get("name", ""),
            "kana": raw.get("kana", ""),
            "location": raw.get("location", ""),
            "postal_code": raw.get("postal_code", ""),
            "representative_name": (raw.get("representative_name") or "").strip().replace("\xa0", " "),
            "capital_stock": raw.get("capital_stock"),
            "employee_number": raw.get("employee_number"),
            "business_summary": raw.get("business_summary", ""),
            "company_url": raw.get("company_url", ""),
            "date_of_establishment": raw.get("date_of_establishment", ""),
            "qualification_grade": raw.get("qualification_grade", ""),
            "status": raw.get("status", ""),
            "update_date": raw.get("update_date", ""),
            "source": "gbizinfo",
        }

        self._set_cache(cache_key, result)
        return result

    def get_subsidies(self, corporate_number: str) -> list[dict]:
        """法人番号から補助金受給履歴を取得。"""
        cache_key = f"subsidy:{corporate_number}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        data = self._api_get(f"/hojin/{corporate_number}/subsidy")
        if not data:
            return []

        infos = data.get("hojin-infos", [])
        if not infos:
            return []

        raw_subsidies = infos[0].get("subsidy", [])
        results = []
        for s in raw_subsidies:
            results.append({
                "title": s.get("title", ""),
                "amount": s.get("amount"),
                "date_of_approval": s.get("date_of_approval", ""),
                "target": s.get("target", ""),
                "government_departments": s.get("government_departments", ""),
                "note": s.get("note", ""),
                "source": "gbizinfo",
            })

        # 日付降順
        results.sort(key=lambda x: x.get("date_of_approval") or "", reverse=True)
        self._set_cache(cache_key, results)
        return results

    def get_certifications(self, corporate_number: str) -> list[dict]:
        """法人番号から認定・届出情報を取得。"""
        cache_key = f"cert:{corporate_number}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        data = self._api_get(f"/hojin/{corporate_number}/certification")
        if not data:
            return []

        infos = data.get("hojin-infos", [])
        if not infos:
            return []

        raw_certs = infos[0].get("certification", [])
        results = []
        for c in raw_certs:
            results.append({
                "title": c.get("title", ""),
                "date_of_approval": c.get("date_of_approval", ""),
                "expiration_date": c.get("expiration_date", ""),
                "target": c.get("target", ""),
                "category": c.get("category", ""),
                "government_departments": c.get("government_departments", ""),
                "enterprise_scale": c.get("enterprise_scale", ""),
                "source": "gbizinfo",
            })

        results.sort(key=lambda x: x.get("date_of_approval") or "", reverse=True)
        self._set_cache(cache_key, results)
        return results

    def get_patents(self, corporate_number: str) -> list[dict]:
        """法人番号から特許情報を取得。"""
        cache_key = f"patent:{corporate_number}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        data = self._api_get(f"/hojin/{corporate_number}/patent")
        if not data:
            return []

        infos = data.get("hojin-infos", [])
        if not infos:
            return []

        raw_patents = infos[0].get("patent", [])
        results = []
        for p in raw_patents:
            classifications = p.get("classifications", [])
            class_labels = [
                c.get("日本語", c.get("コード値", ""))
                for c in classifications
            ] if classifications else []

            results.append({
                "patent_type": p.get("patent_type", ""),
                "application_number": p.get("application_number", ""),
                "application_date": p.get("application_date", ""),
                "classifications": class_labels,
                "source": "gbizinfo",
            })

        results.sort(key=lambda x: x.get("application_date") or "", reverse=True)
        self._set_cache(cache_key, results)
        return results

    def get_finance(self, corporate_number: str) -> list[dict]:
        """法人番号から財務情報を取得。"""
        cache_key = f"finance:{corporate_number}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        data = self._api_get(f"/hojin/{corporate_number}/finance")
        if not data:
            return []

        infos = data.get("hojin-infos", [])
        if not infos:
            return []

        raw_finance = infos[0].get("finance", {})
        if not raw_finance or not isinstance(raw_finance, dict):
            return []

        results = []

        # management_index 内の期別データを抽出
        mgmt_indices = raw_finance.get("management_index", [])
        if isinstance(mgmt_indices, list):
            for mi in mgmt_indices:
                if isinstance(mi, dict):
                    results.append({
                        "period": mi.get("period", ""),
                        "net_sales": mi.get("net_sales_summary_of_business_results"),
                        "operating_revenue": mi.get("operating_revenue_summary_of_business_results"),
                        "ordinary_income": mi.get("ordinary_income_summary_of_business_results"),
                        "net_income": mi.get("net_income_summary_of_business_results"),
                        "total_assets": mi.get("total_assets_summary_of_business_results"),
                        "net_assets": mi.get("net_assets_summary_of_business_results"),
                        "number_of_employees": mi.get("number_of_employees"),
                        "source": "gbizinfo",
                    })

        # 補足情報を付与
        fiscal_year = raw_finance.get("fiscal_year_cover_page", "")
        accounting_standards = raw_finance.get("accounting_standards", "")
        major_shareholders = raw_finance.get("major_shareholders", [])

        # 結果にメタ情報を追加
        for r in results:
            r["fiscal_year_cover_page"] = fiscal_year
            r["accounting_standards"] = accounting_standards

        # 大株主情報があれば先頭エントリに付与
        if results and major_shareholders:
            results[0]["major_shareholders"] = [
                {
                    "name": s.get("name_major_shareholders", ""),
                    "ratio": s.get("shareholding_ratio"),
                }
                for s in major_shareholders[:10]
                if isinstance(s, dict)
            ]

        self._set_cache(cache_key, results)
        return results

    def get_procurement(self, corporate_number: str) -> list[dict]:
        """法人番号から調達（入札）情報を取得。"""
        cache_key = f"procurement:{corporate_number}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        data = self._api_get(f"/hojin/{corporate_number}/procurement")
        if not data:
            return []

        infos = data.get("hojin-infos", [])
        if not infos:
            return []

        raw_proc = infos[0].get("procurement", [])
        results = []
        for p in raw_proc:
            results.append({
                "title": p.get("title", ""),
                "amount": p.get("amount"),
                "date_of_order": p.get("date_of_order", ""),
                "government_departments": p.get("government_departments", ""),
                "source": "gbizinfo",
            })

        results.sort(key=lambda x: x.get("date_of_order") or "", reverse=True)
        self._set_cache(cache_key, results)
        return results

    def get_full_profile(self, corporate_number: str) -> dict | None:
        """
        企業の全情報を統合して返す（プロフィール+補助金+認定+特許+財務+調達）。
        エージェントが1コールで企業の全貌を把握するためのエンドポイント。
        """
        company = self.get_company(corporate_number)
        if not company:
            return None

        subsidies = self.get_subsidies(corporate_number)
        certifications = self.get_certifications(corporate_number)
        patents = self.get_patents(corporate_number)
        finance = self.get_finance(corporate_number)
        procurement = self.get_procurement(corporate_number)

        return {
            **company,
            "subsidies": {
                "count": len(subsidies),
                "items": subsidies[:20],  # 上位20件
            },
            "certifications": {
                "count": len(certifications),
                "items": certifications[:20],
            },
            "patents": {
                "count": len(patents),
                "items": patents[:20],
            },
            "finance": {
                "count": len(finance),
                "items": finance[:5],  # 直近5期
            },
            "procurement": {
                "count": len(procurement),
                "items": procurement[:20],
            },
        }

    def search_companies(self, name: str, page: int = 1) -> dict:
        """
        企業名で法人を検索する。

        Args:
            name: 検索キーワード（企業名の一部）
            page: ページ番号
        Returns:
            検索結果（法人番号リスト付き）
        """
        data = self._api_get(f"/hojin?name={name}&page={page}")
        if not data:
            return {"total": 0, "companies": []}

        infos = data.get("hojin-infos", [])
        total = data.get("totalCount", len(infos))

        companies = []
        for raw in infos:
            companies.append({
                "corporate_number": raw.get("corporate_number", ""),
                "name": raw.get("name", ""),
                "location": raw.get("location", ""),
                "status": raw.get("status", ""),
                "update_date": raw.get("update_date", ""),
            })

        return {
            "total": total,
            "page": page,
            "companies": companies,
        }

    # === Private Methods ===

    def _api_get(self, path: str) -> dict | None:
        """gBizINFO APIにGETリクエストを送信。"""
        if not self.api_token:
            print("[gBizINFO] WARNING: GBIZ_API_TOKEN not set")
            return None

        url = f"{self.api_base}{path}"
        headers = {"X-hojinInfo-api-token": self.api_token}

        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                return resp.json()
            else:
                print(f"[gBizINFO] API Error {resp.status_code}: {url}")
                return None
        except Exception as e:
            print(f"[gBizINFO] Request error: {e}")
            return None

    def _get_cache(self, key: str):
        """キャッシュから取得（TTL付き）。"""
        if key in self._cache:
            entry = self._cache[key]
            elapsed = (datetime.now() - entry["time"]).total_seconds()
            if elapsed < self._cache_ttl:
                return entry["data"]
            del self._cache[key]
        return None

    def _set_cache(self, key: str, data):
        """キャッシュに格納。"""
        self._cache[key] = {"data": data, "time": datetime.now()}
