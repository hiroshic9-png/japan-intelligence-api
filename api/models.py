"""
Japan Intelligence API — レスポンスモデル

全エンドポイントの型安全なレスポンス定義。
OpenAPI/Swaggerスキーマの自動生成にも使用される。
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field


# === 共通レスポンスモデル ===

class PaginationMeta(BaseModel):
    """ページネーション情報"""
    offset: int = Field(0, description="開始位置")
    limit: int = Field(100, description="取得件数上限")
    total: int = Field(0, description="総件数")
    has_more: bool = Field(False, description="追加データの有無")


class APIResponse(BaseModel):
    """API共通レスポンスラッパー"""
    status: str = Field("ok", description="レスポンスステータス")
    source: str = Field(..., description="データソース名")
    updated_at: str = Field(..., description="レスポンス生成時刻 (ISO 8601)")
    count: int = Field(..., description="返却データ件数")
    data: Any = Field(..., description="レスポンスデータ本体")
    pagination: Optional[PaginationMeta] = Field(None, description="ページネーション情報")
    meta: dict = Field(default_factory=dict, description="メタ情報")


class ErrorResponse(BaseModel):
    """エラーレスポンス"""
    status: str = Field("error", description="エラーステータス")
    error: str = Field(..., description="エラーメッセージ")
    detail: Optional[str] = Field(None, description="詳細情報")
    timestamp: str = Field(..., description="エラー発生時刻")


# === TDnet モデル ===

class DisclosureItem(BaseModel):
    """適時開示アイテム"""
    code: str = Field(..., description="銘柄コード (4桁)", example="7203")
    ticker: str = Field(..., description="ティッカー", example="7203.T")
    company_name: str = Field("", description="会社名")
    title: str = Field(..., description="開示タイトル")
    published_at: str = Field("", description="公開日時")
    category: str = Field("その他", description="カテゴリ分類")
    impact: str = Field("NEUTRAL", description="インパクト判定")
    url: str = Field("", description="開示PDF URL")
    source: str = Field("tdnet", description="データソース")


class AIInterpretation(BaseModel):
    """AI解釈結果（Layer 2）"""
    significance: str = Field("", description="重要度 (high/medium/low)")
    significance_reason: str = Field("", description="重要度の根拠")
    market_impact: str = Field("", description="株価影響 (+/-/neutral)")
    market_impact_reason: str = Field("", description="影響の根拠")
    key_question: str = Field("", description="投資家が確認すべきポイント")
    model: str = Field("", description="使用LLMモデル")


class MacroInterpretation(BaseModel):
    """マクロイベントAI解釈"""
    immediate_impact: str = Field("", description="短期的影響")
    sector_rotation: str = Field("", description="セクターローテーション")
    risk_scenario: str = Field("", description="リスクシナリオ")
    model: str = Field("", description="使用LLMモデル")


class TickerDisclosureResult(BaseModel):
    """銘柄別開示レスポンス"""
    ticker: str
    company_name: str
    disclosures: list[DisclosureItem] = []
    ai_interpretation: Optional[AIInterpretation] = None


# === マクロモデル ===

class MacroIndicator(BaseModel):
    """マクロ指標"""
    indicator: str = Field(..., description="指標キー", example="crude_oil")
    label: str = Field(..., description="指標名（日本語）", example="原油WTI")
    price: float = Field(..., description="最新価格")
    change_pct: float = Field(..., description="前日比 (%)")
    source: str = Field("yfinance", description="データソース")


class BeneficiaryDetail(BaseModel):
    """恩恵/逆風銘柄詳細"""
    ticker: str
    company_name: str


class MacroEvent(BaseModel):
    """マクロ異常変動イベント"""
    event: str = Field(..., description="イベントキー")
    label: str = Field(..., description="イベント名（日本語）")
    label_en: str = Field("", description="イベント名（英語）")
    change_pct: float = Field(..., description="変動率 (%)")
    price: float = Field(..., description="現在価格")
    description: str = Field("", description="イベント説明")
    positive_tickers: list[str] = Field(default_factory=list)
    negative_tickers: list[str] = Field(default_factory=list)
    positive_details: list[BeneficiaryDetail] = Field(default_factory=list)
    negative_details: list[BeneficiaryDetail] = Field(default_factory=list)
    ai_interpretation: Optional[MacroInterpretation] = None
    source: str = Field("macro_detection")


# === EDINET モデル ===

class HoldingItem(BaseModel):
    """大量保有報告アイテム"""
    ticker: str
    code: str
    company_name: str = ""
    filer_name: str = Field("", description="報告者名")
    title: str
    date: str
    doc_id: str = ""
    doc_type: str = ""
    source: str = "edinet"


# === ヘルスチェック ===

class HealthResponse(BaseModel):
    """ヘルスチェックレスポンス"""
    status: str = "ok"
    service: str = "japan-intelligence"
    version: str
    timestamp: str
    sources: dict = Field(default_factory=dict)


# === 銘柄情報 ===

class TickerInfo(BaseModel):
    """銘柄基本情報"""
    ticker: str
    company_name: str
