"""
Japan Intelligence — EDINET大量保有報告データソース

EDINET API v2を利用して大量保有報告書・変更報告書を取得し構造化する。
ASTRAのedinet_fetcher.pyから転用・拡張。

重複排除ロジック:
  - 訂正報告書（docTypeCode=360）は parentDocID で原本に紐づけ
  - 原本に訂正がある場合、訂正報告書で置き換え（最新の訂正を優先）
  - 同一parentDocIDへの複数訂正は最新のsubmitDateTimeのみ保持
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
        大量保有報告書を取得する（重複排除済み）。

        Args:
            days: 取得期間（日数）
            ticker: 特定銘柄でフィルタ（例: "7203.T"）
        """
        days = days or EDINET_CONFIG['default_days']

        if self._is_cache_valid():
            results = self._cache
        else:
            raw = self._fetch(days)
            results = self._deduplicate(raw)
            self._cache = results
            self._cache_time = datetime.now()

        if ticker:
            results = [r for r in results if r['ticker'] == ticker]

        return results

    def _fetch(self, days: int) -> list[dict]:
        """EDINET APIから大量保有報告書を取得（生データ、重複排除前）"""
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
                                parent_doc_id = doc.get("parentDocID", "")
                                doc_type_code = doc.get("docTypeCode", "")
                                is_correction = (str(doc_type_code) == "360")

                                results.append({
                                    'ticker': f"{ticker_code}.T",
                                    'code': ticker_code,
                                    'filer_name': doc.get("filerName", ""),
                                    'title': title,
                                    'date': target_date,
                                    'doc_id': doc.get("docID", ""),
                                    'doc_type': doc_type_code,
                                    'parent_doc_id': parent_doc_id,
                                    'is_correction': is_correction,
                                    'submit_datetime': doc.get("submitDateTime", ""),
                                    'source': 'edinet',
                                })
                else:
                    print(f"[EDINET] API Error {resp.status_code} on {target_date}")
            except Exception as e:
                print(f"[EDINET] Fetch error on {target_date}: {e}")

            time.sleep(0.5)  # レート制限回避

        return results

    def _deduplicate(self, raw: list[dict]) -> list[dict]:
        """
        訂正報告書の重複排除。

        ロジック:
        1. 訂正報告書（is_correction=True）は parentDocID で原本にマッピング
        2. 同じ parentDocID に複数の訂正がある場合、最新の submit_datetime を採用
        3. 訂正が存在する原本は訂正報告書で置き換え（タイトルに「→訂正済」を付与）
        4. 訂正のない原本はそのまま保持
        """
        # doc_id → entry のマップ（原本用）
        originals = {}
        # parent_doc_id → 最新訂正 のマップ
        corrections = {}

        for entry in raw:
            if entry['is_correction'] and entry['parent_doc_id']:
                parent_id = entry['parent_doc_id']
                if parent_id not in corrections:
                    corrections[parent_id] = entry
                else:
                    # 最新の訂正を保持（submit_datetime比較）
                    existing_dt = corrections[parent_id].get('submit_datetime', '')
                    new_dt = entry.get('submit_datetime', '')
                    if new_dt > existing_dt:
                        corrections[parent_id] = entry
            else:
                originals[entry['doc_id']] = entry

        # 結果を組み立て
        results = []
        replaced_ids = set()

        for doc_id, original in originals.items():
            if doc_id in corrections:
                # 訂正で原本を置き換え
                corrected = corrections[doc_id].copy()
                corrected['original_doc_id'] = doc_id
                corrected['original_title'] = original['title']
                corrected['title'] = f"{original['title']}（訂正済）"
                results.append(corrected)
                replaced_ids.add(doc_id)
            else:
                results.append(original)

        # parentDocIDが取得期間外の原本を指す訂正報告書（原本がresultsにない場合）
        for parent_id, correction in corrections.items():
            if parent_id not in replaced_ids and parent_id not in originals:
                correction_entry = correction.copy()
                correction_entry['original_doc_id'] = parent_id
                results.append(correction_entry)

        # 日付降順でソート
        results.sort(key=lambda x: (x['date'], x.get('submit_datetime', '')), reverse=True)

        deduped_count = len(raw) - len(results)
        if deduped_count > 0:
            print(f"[EDINET] Deduplicated: {len(raw)} → {len(results)} ({deduped_count} corrections merged)")

        return results

    def _is_cache_valid(self) -> bool:
        if not self._cache_time:
            return False
        elapsed = (datetime.now() - self._cache_time).total_seconds()
        return elapsed < self._cache_ttl
