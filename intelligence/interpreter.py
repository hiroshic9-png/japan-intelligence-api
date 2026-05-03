"""
Japan Intelligence — AI解釈エンジン（Layer 2）

構造化データに対してLLMベースの解釈を付与する。
ASTRAのthe_why_engine.pyから転用・汎用化。

v2: JSON構造化出力に変更（プレーンテキスト→パース可能なJSON）
"""
import json
import re
from typing import Optional
from core.config import LLM_CONFIG

try:
    from google import genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False


class Interpreter:
    """AI解釈エンジン — 構造化データに「なぜ重要か」の解釈を付与する"""

    def __init__(self):
        if HAS_GENAI and LLM_CONFIG['api_key']:
            self.client = genai.Client(api_key=LLM_CONFIG['api_key'])
        else:
            self.client = None

    def interpret_disclosure(self, disclosure: dict) -> dict:
        """
        適時開示に対してAI解釈を生成する。

        Args:
            disclosure: TDnetSource から返された開示データ

        Returns:
            構造化された解釈データ
        """
        if not self.client:
            return {
                'significance': 'unknown',
                'significance_reason': 'LLM not available',
                'market_impact': 'neutral',
                'market_impact_reason': 'LLM not available',
                'key_question': '',
                'model': 'none',
            }

        prompt = f"""あなたは日本株市場の専門アナリストです。
以下の適時開示情報を分析し、JSON形式で解釈を提供してください。

銘柄: {disclosure.get('ticker', '')} ({disclosure.get('company_name', '')})
開示タイトル: {disclosure.get('title', '')}
カテゴリ: {disclosure.get('category', '')}
インパクト判定: {disclosure.get('impact', '')}

必ず以下のJSON形式のみで回答してください。説明文やコードブロックは不要です:
{{"significance": "high/medium/low", "significance_reason": "理由（1文）", "market_impact": "+/-/neutral", "market_impact_reason": "根拠（1文）", "key_question": "投資家が確認すべきポイント（1文）"}}"""

        return self._call_llm(prompt, 'disclosure',
                              ['significance', 'significance_reason',
                               'market_impact', 'market_impact_reason',
                               'key_question'])

    def interpret_macro_event(self, event: dict) -> dict:
        """マクロイベントに対してAI解釈を生成する"""
        if not self.client:
            return {
                'immediate_impact': 'LLM not available',
                'sector_rotation': '',
                'risk_scenario': '',
                'model': 'none',
            }

        prompt = f"""あなたはグローバルマクロのストラテジストです。
以下のマクロイベントが日本株市場に与える影響をJSON形式で分析してください。

イベント: {event.get('label', '')}
変動率: {event.get('change_pct', 0):+.1f}%
現在価格: {event.get('price', 0)}

必ず以下のJSON形式のみで回答してください。説明文やコードブロックは不要です:
{{"immediate_impact": "短期的影響（1文）", "sector_rotation": "資金フローの方向（1文）", "risk_scenario": "注意すべきリスク（1文）"}}"""

        return self._call_llm(prompt, 'macro_event',
                              ['immediate_impact', 'sector_rotation',
                               'risk_scenario'])

    def _call_llm(self, prompt: str, context: str, expected_keys: list) -> dict:
        """LLMを呼び出し、構造化JSONを返す"""
        try:
            resp = self.client.models.generate_content(
                model=LLM_CONFIG['model'],
                contents=prompt,
            )
            text = resp.text.strip() if resp.text else ""

            # JSON抽出: コードブロック内またはプレーンJSON
            parsed = self._extract_json(text)

            if parsed:
                # 期待するキーが存在するか確認
                result = {k: parsed.get(k, '') for k in expected_keys}
                result['model'] = LLM_CONFIG['model']
                return result

            # JSONパース失敗時: テキストをそのままフォールバック
            result = {k: '' for k in expected_keys}
            result['raw_text'] = text
            result['model'] = LLM_CONFIG['model']
            return result

        except Exception as e:
            result = {k: '' for k in expected_keys}
            result['error'] = str(e)
            result['model'] = LLM_CONFIG['model']
            return result

    def _extract_json(self, text: str) -> Optional[dict]:
        """テキストからJSONオブジェクトを抽出する"""
        # コードブロック内のJSONを探す
        code_block = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
        if code_block:
            try:
                return json.loads(code_block.group(1).strip())
            except json.JSONDecodeError:
                pass

        # プレーンJSONを探す
        brace_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        return None
