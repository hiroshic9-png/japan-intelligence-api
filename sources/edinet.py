"""
Japan Intelligence — EDINET大量保有報告データソース

EDINET API v2を利用して大量保有報告書・変更報告書を取得し構造化する。
ASTRAのedinet_fetcher.pyから転用・拡張。
"""
import os
import time
import requests
from datetime import datetime, timedelta
from core.config import EDINET_CONFIG


class EDINETSource:
    """EDINET大量保有報告書を取得・構造化するデータソース"""

    def __init__(self):
        self.api_base = EDINET_CONFIG['api_base']
        self.api_key = EDINET_CONFIG['api_key']
        self._cache = []
        self._cache_time = None
        self._cache_ttl = EDINET_CONFIG['cache_ttl_seconds']

    def get_holdings(self, days: int = None, ticker: str = None) -> list[dict]:
        """
        大量保有報告書を取得する。

        Args:
            days: 取得期間（日数）
            ticker: 特定銘柄でフィルタ（例: "7203.T"）
        """
        days = days or EDINET_CONFIG['default_days']

        if self._is_cache_valid():
            results = self._cache
        else:
            results = self._fetch(days)

        if ticker:
            results = [r for r in results if r['ticker'] == ticker]

        return results

    def _fetch(self, days: int) -> list[dict]:
        """EDINET APIから大量保有報告書を取得"""
        if not self.api_key:
            print("[EDINET] WARNING: EDINET_API_KEY not set")
            return []

        results = []
        today = datetime.now()

        for i in range(days):
            target_date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            url = f"{self.api_base}/documents.json"
            params = {
                "date": target_date,
                "type": 2,
                "Subscription-Key": self.api_key,
            }

            try:
                resp = requests.get(url, params=params, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    docs = data.get("results", [])

                    for doc in docs:
                        title = doc.get("docDescription", "")
                        if title and ("大量保有報告書" in title or "変更報告書" in title):
                            code = doc.get("secCode")
                            if code and len(str(code)) >= 4:
                                ticker_code = str(code)[:4]
                                results.append({
                                    'ticker': f"{ticker_code}.T",
                                    'code': ticker_code,
                                    'filer_name': doc.get("filerName", ""),
                                    'title': title,
                                    'date': target_date,
                                    'doc_id': doc.get("docID", ""),
                                    'doc_type': doc.get("docTypeCode", ""),
                                    'source': 'edinet',
                                })
                else:
                    print(f"[EDINET] API Error {resp.status_code} on {target_date}")
            except Exception as e:
                print(f"[EDINET] Fetch error on {target_date}: {e}")

            time.sleep(0.5)  # レート制限回避

        self._cache = results
        self._cache_time = datetime.now()
        return results

    def _is_cache_valid(self) -> bool:
        if not self._cache_time:
            return False
        elapsed = (datetime.now() - self._cache_time).total_seconds()
        return elapsed < self._cache_ttl
