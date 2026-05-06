"""
適時開示AI要約エンジン — TRANSCODE排他的データ層

TDnet開示タイトル（日本語）に対して、Geminiで1行英語要約を生成し
エージェントが即座に内容を把握できるようにする。

設計:
  - バッチ処理: 複数タイトルを1プロンプトに集約してAPI呼び出しを最小化
  - キャッシュ: 要約済み結果を保持し、同一タイトルの再生成を回避
  - フォールバック: LLM不可時はルールベースのテンプレート要約を生成
"""
from __future__ import annotations

import json
import re
import threading
import time
from typing import Optional
from collections import OrderedDict

from core.config import LLM_CONFIG

try:
    from google import genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False


class DisclosureSummarizer:
    """適時開示のAI要約を生成・キャッシュするエンジン"""

    def __init__(self, max_cache_size: int = 2000):
        if HAS_GENAI and LLM_CONFIG['api_key']:
            self.client = genai.Client(api_key=LLM_CONFIG['api_key'])
        else:
            self.client = None

        # LRUキャッシュ: {title_hash: summary_dict}
        self._cache: OrderedDict[str, dict] = OrderedDict()
        self._max_cache = max_cache_size
        self._lock = threading.Lock()
        self._stats = {"hits": 0, "misses": 0, "llm_calls": 0, "fallbacks": 0}

    def summarize_batch(self, disclosures: list[dict], max_items: int = 30) -> list[dict]:
        """
        複数の開示に対してAI要約を一括生成する。

        Args:
            disclosures: TDnetSourceから返された開示リスト
            max_items: 要約対象の最大数

        Returns:
            ai_summary フィールドが追加された開示リスト
        """
        target = disclosures[:max_items]

        # キャッシュから取得可能なものを分離
        uncached = []
        for d in target:
            key = self._cache_key(d)
            with self._lock:
                if key in self._cache:
                    self._cache.move_to_end(key)
                    d['ai_summary'] = self._cache[key]
                    self._stats["hits"] += 1
                else:
                    uncached.append(d)
                    self._stats["misses"] += 1

        # 未キャッシュ分をバッチ要約
        if uncached and self.client:
            summaries = self._batch_summarize(uncached)
            for d, summary in zip(uncached, summaries):
                d['ai_summary'] = summary
                key = self._cache_key(d)
                self._put_cache(key, summary)
        elif uncached:
            # LLM不可時: ルールベースフォールバック
            for d in uncached:
                d['ai_summary'] = self._rule_based_summary(d)
                self._stats["fallbacks"] += 1

        # 残りの開示（max_items超過分）はフォールバック
        for d in disclosures[max_items:]:
            if 'ai_summary' not in d:
                d['ai_summary'] = self._rule_based_summary(d)

        return disclosures

    def get_stats(self) -> dict:
        """キャッシュ統計を返す"""
        return {
            **self._stats,
            "cache_size": len(self._cache),
            "max_cache_size": self._max_cache,
            "llm_available": self.client is not None,
        }

    def _batch_summarize(self, disclosures: list[dict]) -> list[dict]:
        """
        複数開示を1プロンプトでバッチ要約する。

        10件ずつチャンクに分割してLLMを呼び出す。
        """
        chunk_size = 10
        all_summaries = []

        for i in range(0, len(disclosures), chunk_size):
            chunk = disclosures[i:i + chunk_size]
            summaries = self._call_llm_batch(chunk)
            all_summaries.extend(summaries)
            self._stats["llm_calls"] += 1

        return all_summaries

    def _call_llm_batch(self, disclosures: list[dict]) -> list[dict]:
        """LLMを1回呼び出して複数開示を一括要約する"""
        # プロンプト構築
        items = []
        for idx, d in enumerate(disclosures, 1):
            items.append(
                f"{idx}. [{d.get('ticker', '????')}] "
                f"{d.get('company_name', '')} | "
                f"{d.get('title', '')} | "
                f"カテゴリ: {d.get('category', '')} | "
                f"インパクト: {d.get('impact', '')}"
            )

        prompt = f"""You are a Japanese equity market analyst. Summarize each disclosure below in ONE concise English sentence (max 15 words). Focus on the financial significance for investors.

Also provide: impact_score (1-5, where 5=most significant) and sector_relevance (which sectors are affected).

Disclosures:
{chr(10).join(items)}

Respond ONLY with a JSON array. No explanation. No code block markers.
[{{"id": 1, "summary": "...", "impact_score": 3, "sector_relevance": "..."}}]"""

        try:
            resp = self.client.models.generate_content(
                model=LLM_CONFIG['model'],
                contents=prompt,
            )
            text = resp.text.strip() if resp.text else ""
            parsed = self._extract_json_array(text)

            if parsed and len(parsed) == len(disclosures):
                return [
                    {
                        "summary_en": item.get("summary", ""),
                        "impact_score": min(max(item.get("impact_score", 3), 1), 5),
                        "sector_relevance": item.get("sector_relevance", ""),
                        "model": LLM_CONFIG['model'],
                        "source": "gemini",
                    }
                    for item in parsed
                ]

            # パース成功だがアイテム数不一致 — 可能な限りマッチ
            if parsed:
                result = []
                for idx in range(len(disclosures)):
                    if idx < len(parsed):
                        item = parsed[idx]
                        result.append({
                            "summary_en": item.get("summary", ""),
                            "impact_score": min(max(item.get("impact_score", 3), 1), 5),
                            "sector_relevance": item.get("sector_relevance", ""),
                            "model": LLM_CONFIG['model'],
                            "source": "gemini",
                        })
                    else:
                        result.append(self._rule_based_summary(disclosures[idx]))
                return result

        except Exception as e:
            print(f"[Summarizer] LLM batch error: {e}")

        # フォールバック
        return [self._rule_based_summary(d) for d in disclosures]

    def _rule_based_summary(self, disclosure: dict) -> dict:
        """LLM不可時のルールベースフォールバック要約"""
        category = disclosure.get('category', '')
        impact = disclosure.get('impact', 'NEUTRAL')
        title = disclosure.get('title', '')
        company = disclosure.get('company_name', '')

        templates = {
            '業績修正': f"Earnings forecast revision by {company}",
            'M&A・提携': f"M&A or strategic alliance involving {company}",
            '自社株買い': f"Share buyback announced by {company}",
            '決算': f"Financial results released by {company}",
            '配当': f"Dividend policy change by {company}",
            '株式分割': f"Stock split announced by {company}",
            '資金調達': f"Capital raise planned by {company}",
            '経営計画': f"Management plan update by {company}",
            '月次業績': f"Monthly performance update by {company}",
            '受注': f"Major order received by {company}",
            '新規事業': f"New business initiative by {company}",
            'ガバナンス': f"Corporate governance event at {company}",
            'IR': f"IR materials published by {company}",
            '株主優待': f"Shareholder benefits update by {company}",
            '株式の取得': f"Share acquisition related to {company}",
        }

        summary = templates.get(category, f"Corporate disclosure by {company}")

        impact_score_map = {
            'POSITIVE': 4, 'NEGATIVE': 4, 'MILD_POSITIVE': 3, 'NEUTRAL': 2,
        }

        return {
            "summary_en": summary,
            "impact_score": impact_score_map.get(impact, 2),
            "sector_relevance": "",
            "model": "rule_based",
            "source": "fallback",
        }

    def _cache_key(self, disclosure: dict) -> str:
        """キャッシュキーを生成"""
        return f"{disclosure.get('ticker', '')}:{disclosure.get('title', '')[:60]}"

    def _put_cache(self, key: str, value: dict):
        """キャッシュに追加（LRU管理）"""
        with self._lock:
            self._cache[key] = value
            if len(self._cache) > self._max_cache:
                self._cache.popitem(last=False)

    def _extract_json_array(self, text: str) -> Optional[list]:
        """テキストからJSON配列を抽出する"""
        # コードブロック内を探す
        code_block = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
        if code_block:
            try:
                return json.loads(code_block.group(1).strip())
            except json.JSONDecodeError:
                pass

        # プレーンJSON配列を探す
        bracket_match = re.search(r'\[.*\]', text, re.DOTALL)
        if bracket_match:
            try:
                return json.loads(bracket_match.group(0))
            except json.JSONDecodeError:
                pass

        return None
