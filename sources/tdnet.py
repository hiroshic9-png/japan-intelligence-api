"""
Japan Intelligence — TDnet適時開示データソース

TDnet（適時開示情報閲覧サービス）から直近の開示情報を取得し、
カテゴリ分類・インパクト判定を付与して構造化する。

データソース: やのしんTDnet Web API（無料・JSON）
https://webapi.yanoshin.jp/webapi/tdnet/list/

ASTRA v2のtdnet_fetcher.pyから転用・公開API向けに汎用化。
"""
from __future__ import annotations
import os
import requests
from datetime import datetime, timedelta
from typing import Optional

from core.config import TDNET_CONFIG, LLM_CONFIG

try:
    from google import genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False


class TDnetSource:
    """TDnet適時開示を取得・構造化するデータソース"""

    def __init__(self):
        self.api_base = TDNET_CONFIG['api_base']
        self._cache = {}
        self._cache_time = None
        self._cache_ttl = TDNET_CONFIG['cache_ttl_seconds']

        if HAS_GENAI and LLM_CONFIG['api_key']:
            self.genai_client = genai.Client(api_key=LLM_CONFIG['api_key'])
        else:
            self.genai_client = None

    def get_disclosures(self, days: int = None, ticker: str = None) -> list[dict]:
        """
        適時開示を取得する。

        Args:
            days: 取得期間（日数）。デフォルトはconfig値。
            ticker: 特定銘柄でフィルタ（例: "7203.T"）

        Returns:
            構造化された開示情報のリスト
        """
        days = days or TDNET_CONFIG['default_days']

        # キャッシュ判定（daysが変わったら再取得）
        cached_days = self._cache.get('days', 0)
        if self._is_cache_valid() and cached_days >= days:
            disclosures = self._cache.get('disclosures', [])
        else:
            disclosures = self._fetch(days)

        # 銘柄フィルタ
        if ticker:
            code = ticker.replace('.T', '')
            disclosures = [d for d in disclosures if d['code'] == code]

        return disclosures

    def get_disclosure_summary(self, ticker: str) -> Optional[dict]:
        """特定銘柄の開示情報からAI要約を生成する（Layer 2）"""
        disclosures = self.get_disclosures(ticker=ticker)
        if not disclosures:
            return None

        prioritized = self._prioritize(disclosures)
        top = prioritized[0]

        result = {
            'ticker': ticker,
            'title': top['title'],
            'category': top['category'],
            'published_at': top['published_at'],
            'url': top.get('url', ''),
            'impact': top.get('impact', 'UNKNOWN'),
        }

        # AI解釈（Layer 2）
        if self.genai_client and prioritized:
            try:
                titles = "\n".join([f"- {d['title']}" for d in prioritized[:5]])
                prompt = f"""以下は{ticker}の直近の適時開示タイトルです。
株価への影響を30文字以内で要約してください。
ポジティブ/ネガティブ/中立も判定してください。

{titles}

回答形式: [ポジティブ/ネガティブ/中立] 要約文"""

                resp = self.genai_client.models.generate_content(
                    model=LLM_CONFIG['model'],
                    contents=prompt,
                )
                summary = resp.text.strip() if resp.text else ""
                result['ai_interpretation'] = summary

                if 'ポジティブ' in summary:
                    result['impact'] = 'POSITIVE'
                elif 'ネガティブ' in summary:
                    result['impact'] = 'NEGATIVE'
                else:
                    result['impact'] = 'NEUTRAL'
            except Exception as e:
                print(f"[TDnet] AI interpretation error: {e}")

        return result

    def _fetch(self, days: int) -> list[dict]:
        """APIから生データを取得し構造化する"""
        disclosures = []
        try:
            today = datetime.now()
            start_date = (today - timedelta(days=max(1, days - 1))).strftime("%Y%m%d")
            end_date = today.strftime("%Y%m%d")
            url = f"{self.api_base}/{start_date}-{end_date}.json"

            print(f"[TDnet] Fetching disclosures: {start_date}-{end_date}")
            response = requests.get(url, timeout=30)

            if response.status_code == 200:
                data = response.json()
                items = data.get('items', [])
                print(f"[TDnet] Fetched {len(items)} raw disclosures")

                for item in items:
                    parsed = self._parse_item(item)
                    if parsed:
                        disclosures.append(parsed)
            else:
                print(f"[TDnet] API error: {response.status_code}")
        except Exception as e:
            print(f"[TDnet] Fetch error: {e}")

        # キャッシュ更新
        self._cache = {'disclosures': disclosures, 'days': days}
        self._cache_time = datetime.now()

        return disclosures

    def _is_cache_valid(self) -> bool:
        if not self._cache_time:
            return False
        elapsed = (datetime.now() - self._cache_time).total_seconds()
        return elapsed < self._cache_ttl

    def _parse_item(self, item: dict) -> Optional[dict]:
        """APIレスポンスの1アイテムをパースする"""
        try:
            td = item.get('Tdnet', item)
            title = td.get('title', '')
            company = td.get('company_name', '')
            code_raw = td.get('company_code', '')
            published = td.get('pubdate', '')
            url = td.get('document_url', '')

            if not code_raw or not title:
                return None

            code = str(code_raw)[:4]
            category = self._categorize(title)
            impact = self._estimate_impact(title, category)

            return {
                'code': code,
                'ticker': f"{code}.T",
                'company_name': company,
                'title': title,
                'published_at': published,
                'category': category,
                'impact': impact,
                'url': url,
                'source': 'tdnet',
            }
        except Exception:
            return None

    def _categorize(self, title: str) -> str:
        """開示タイトルからカテゴリを推定"""
        categories = [
            ('M&A・提携', ['業務提携', '資本提携', '合併', '買収', 'TOB', '公開買付',
                          'MBO', '経営統合', '事業譲渡', '完全子会社化']),
            ('株式の取得', ['株式の取得', '株式取得', '保有割合', '大量保有']),
            ('自社株買い', ['自己株式の取得', '自社株買い']),
            ('業績修正', ['業績予想の修正', '上方修正', '下方修正', '増額', '減額']),
            ('決算', ['決算短信', '四半期報告', '決算発表']),
            ('配当', ['配当予想の修正', '増配', '減配', '復配', '特別配当', '初配']),
            ('株式分割', ['株式分割', '株式併合']),
            ('株主優待', ['株主優待']),
            ('資金調達', ['第三者割当', '新株予約権', '公募増資', '転換社債']),
            ('経営計画', ['中期経営計画', '経営計画', '成長戦略', '資本コスト', 'PBR', 'ROE']),
            ('月次業績', ['月次業績', '月次営業', '月次売上']),
            ('受注', ['受注', '大型案件', '大口受注', '新規契約']),
            ('新規事業', ['新製品', '新サービス', '特許', '海外展開', '設備投資']),
            ('ガバナンス', ['訴訟', '損害賠償', '行政処分', '不正', '買収防衛']),
            ('IR', ['説明会', '説明資料', 'IR', '決算説明']),
        ]
        for cat, keywords in categories:
            for kw in keywords:
                if kw in title:
                    return cat
        return 'その他'

    def _estimate_impact(self, title: str, category: str) -> str:
        """株価インパクトを推定"""
        strong_positive = ['上方修正', '増額', '増配', '復配', '自己株式の取得',
                           '株式分割', '業務提携', '資本提携', '完全子会社化', 'MBO']
        mild_positive = ['中期経営計画', '成長戦略', '新製品', '受注', '大型案件',
                         '海外展開', '設備投資', '株主優待']
        negative = ['下方修正', '減額', '減配', '無配', '債務超過',
                    '特別損失', '減損', '訴訟', '行政処分', '不正']

        for kw in strong_positive:
            if kw in title:
                return 'POSITIVE'
        for kw in negative:
            if kw in title:
                return 'NEGATIVE'
        for kw in mild_positive:
            if kw in title:
                return 'MILD_POSITIVE'
        if category in ('月次業績', '受注', '新規事業'):
            return 'MILD_POSITIVE'
        if category == 'ガバナンス':
            return 'NEGATIVE'
        return 'NEUTRAL'

    def _prioritize(self, disclosures: list[dict]) -> list[dict]:
        """重要度順にソート"""
        priority = {
            '株式の取得': 0, 'M&A・提携': 1, '業績修正': 2, '自社株買い': 3,
            '受注': 4, '経営計画': 5, '決算': 6, '配当': 7, '株式分割': 8,
            '株主優待': 9, '月次業績': 10, '新規事業': 11, '資金調達': 12,
            'IR': 13, 'ガバナンス': 14, 'その他': 15,
        }
        return sorted(disclosures, key=lambda d: priority.get(d['category'], 99))
