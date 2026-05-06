"""
TRANSCODE × CrewAI Integration

CrewAI の Tool として TRANSCODE API を使うためのラッパー。
Japan market research crew を構築する最短経路。

Usage:
    from transcode_crewai import TranscodeTools

    tools = TranscodeTools(api_key="your-api-key")

    # CrewAI Agent に渡す
    from crewai import Agent, Task, Crew

    analyst = Agent(
        role="Japan Market Analyst",
        goal="Analyze Japanese market conditions and identify opportunities",
        tools=tools.all(),
    )
"""

import os
import json
import requests

# CrewAI imports (optional)
try:
    from crewai.tools import BaseTool
    from pydantic import BaseModel, Field
    HAS_CREWAI = True
except ImportError:
    HAS_CREWAI = False


TRANSCODE_BASE_URL = os.getenv(
    "TRANSCODE_BASE_URL",
    "https://japan-intelligence-api.onrender.com"
)


def _api_call(path: str, api_key: str, params: dict = None) -> str:
    """TRANSCODE API call → formatted string"""
    headers = {"X-API-Key": api_key} if api_key else {}
    url = f"{TRANSCODE_BASE_URL}{path}"
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return json.dumps(data.get("data", data), ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


def _api_post(path: str, body: dict, api_key: str) -> str:
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
    url = f"{TRANSCODE_BASE_URL}{path}"
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return json.dumps(data.get("data", data), ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


if HAS_CREWAI:

    # --- Input Schemas ---
    class EmptyInput(BaseModel):
        pass

    class TickerInput(BaseModel):
        ticker: str = Field(description="Japanese stock ticker code, e.g. '7203' for Toyota")

    class DaysInput(BaseModel):
        days: int = Field(default=3, description="Number of days to look back")

    class DisclosureInput(BaseModel):
        days: int = Field(default=1, description="Number of days (1-7)")
        min_impact: int = Field(default=0, description="Minimum impact score (0-5)")

    class BatchInput(BaseModel):
        tickers: str = Field(description="Comma-separated ticker codes, e.g. '7203,6501,9984'")

    class CalendarInput(BaseModel):
        days: int = Field(default=30, description="Days ahead to look (1-365)")

    # --- Tools ---

    class JapanBriefingTool(BaseTool):
        name: str = "japan_briefing"
        description: str = (
            "Get a COMPLETE Japan market briefing in ONE call. "
            "Returns macro indicators (Nikkei, USD/JPY, VIX), policy rates, "
            "Tankan DI, top disclosures, investor flows, weather, seismic risk, "
            "and economic calendar. USE THIS FIRST for any Japan market question."
        )
        args_schema: type = EmptyInput
        api_key: str = ""

        def _run(self) -> str:
            return _api_call("/api/v1/briefing", self.api_key)

    class CompanyIntelligenceTool(BaseTool):
        name: str = "company_intelligence"
        description: str = (
            "Get comprehensive intelligence for a specific Japanese company. "
            "Combines corporate profile, financials, disclosures, holdings, "
            "stock price, and macro context from 6 authoritative sources."
        )
        args_schema: type = TickerInput
        api_key: str = ""

        def _run(self, ticker: str) -> str:
            return _api_call(f"/api/v1/intelligence/{ticker}", self.api_key)

    class MarketSnapshotTool(BaseTool):
        name: str = "market_snapshot"
        description: str = (
            "Get real-time market snapshot: macro indicators, abnormal events, "
            "disclosure stats, and investor flow signals."
        )
        args_schema: type = EmptyInput
        api_key: str = ""

        def _run(self) -> str:
            return _api_call("/api/v1/market/snapshot", self.api_key)

    class DisclosuresTool(BaseTool):
        name: str = "disclosures"
        description: str = (
            "Get recent TDnet corporate disclosures with category classification "
            "and AI impact scoring. Covers earnings revisions, M&A, buybacks, dividends."
        )
        args_schema: type = DaysInput
        api_key: str = ""

        def _run(self, days: int = 3) -> str:
            return _api_call("/api/v1/disclosures", self.api_key, {"days": days, "limit": 50})

    class AISummarizedDisclosuresTool(BaseTool):
        name: str = "ai_summarized_disclosures"
        description: str = (
            "Get AI-summarized disclosures with English translations, impact scores (1-5), "
            "and sector relevance. TRANSCODE exclusive intelligence layer."
        )
        args_schema: type = DisclosureInput
        api_key: str = ""

        def _run(self, days: int = 1, min_impact: int = 0) -> str:
            return _api_call("/api/v1/disclosures/summarized", self.api_key,
                             {"days": days, "min_impact": min_impact, "limit": 30})

    class InvestorFlowsTool(BaseTool):
        name: str = "investor_flows"
        description: str = (
            "Get JPX investor flow data. Shows if foreign investors, individuals, "
            "and trust banks are net buying or selling Japanese stocks. "
            "The strongest directional signal for Japan equities."
        )
        args_schema: type = EmptyInput
        api_key: str = ""

        def _run(self) -> str:
            return _api_call("/api/v1/investor-flows", self.api_key)

    class TankanTool(BaseTool):
        name: str = "tankan_survey"
        description: str = (
            "Get BOJ Tankan business confidence survey. Japan's economic thermometer. "
            "Positive DI = expansion, Negative = contraction."
        )
        args_schema: type = EmptyInput
        api_key: str = ""

        def _run(self) -> str:
            return _api_call("/api/v1/tankan", self.api_key)

    class EconomicCalendarTool(BaseTool):
        name: str = "economic_calendar"
        description: str = (
            "Get upcoming Japanese economic events: BOJ meetings, GDP releases, "
            "CPI, employment data, earnings seasons, market holidays."
        )
        args_schema: type = CalendarInput
        api_key: str = ""

        def _run(self, days: int = 30) -> str:
            return _api_call("/api/v1/calendar", self.api_key, {"days": days})

    class BatchIntelligenceTool(BaseTool):
        name: str = "batch_company_intelligence"
        description: str = (
            "Get intelligence for MULTIPLE companies at once (Developer/Pro tier). "
            "Input: comma-separated ticker codes. Max 10-20 tickers per call."
        )
        args_schema: type = BatchInput
        api_key: str = ""

        def _run(self, tickers: str) -> str:
            ticker_list = [t.strip() for t in tickers.split(",")]
            return _api_post("/api/v1/batch/intelligence", {"tickers": ticker_list}, self.api_key)


class TranscodeTools:
    """
    TRANSCODE ツールセットを一括生成するヘルパー。

    Usage:
        tools = TranscodeTools(api_key="your-key")

        # 全ツール
        analyst = Agent(role="Analyst", tools=tools.all())

        # コアツールのみ
        analyst = Agent(role="Analyst", tools=tools.core())
    """

    def __init__(self, api_key: str = None):
        if not HAS_CREWAI:
            raise ImportError("crewai is required. Install: pip install crewai")
        self.api_key = api_key or os.getenv("TRANSCODE_API_KEY", "")

    def _make(self, cls):
        return cls(api_key=self.api_key)

    def all(self) -> list:
        """全11ツールを返す"""
        return [
            self._make(JapanBriefingTool),
            self._make(CompanyIntelligenceTool),
            self._make(MarketSnapshotTool),
            self._make(DisclosuresTool),
            self._make(AISummarizedDisclosuresTool),
            self._make(InvestorFlowsTool),
            self._make(TankanTool),
            self._make(EconomicCalendarTool),
            self._make(BatchIntelligenceTool),
        ]

    def core(self) -> list:
        """コアツール4つ（briefing, intelligence, snapshot, disclosures）"""
        return [
            self._make(JapanBriefingTool),
            self._make(CompanyIntelligenceTool),
            self._make(MarketSnapshotTool),
            self._make(DisclosuresTool),
        ]
