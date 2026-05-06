"""
TRANSCODE × LangChain Integration

LangChain の Tool として TRANSCODE API を使うためのラッパー集。
Agent が日本市場データにアクセスするための最短経路。

Usage:
    from transcode_langchain import get_transcode_tools

    tools = get_transcode_tools(api_key="your-api-key")
    # → LangChain Agent に渡すだけ
"""

import os
import json
import requests
from typing import Optional

# LangChain imports (optional — 未インストール時はスキップ)
try:
    from langchain_core.tools import tool
    HAS_LANGCHAIN = True
except ImportError:
    HAS_LANGCHAIN = False


# === 設定 ===
TRANSCODE_BASE_URL = os.getenv(
    "TRANSCODE_BASE_URL",
    "https://japan-intelligence-api.onrender.com"
)
TRANSCODE_API_KEY = os.getenv("TRANSCODE_API_KEY", "")


def _call_api(path: str, api_key: str = None, params: dict = None) -> dict:
    """TRANSCODE API を呼び出す共通ヘルパー"""
    key = api_key or TRANSCODE_API_KEY
    headers = {"X-API-Key": key} if key else {}
    url = f"{TRANSCODE_BASE_URL}{path}"

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        return {"error": str(e)}


def _post_api(path: str, body: dict, api_key: str = None) -> dict:
    """TRANSCODE API に POST する共通ヘルパー"""
    key = api_key or TRANSCODE_API_KEY
    headers = {"X-API-Key": key, "Content-Type": "application/json"} if key else {}
    url = f"{TRANSCODE_BASE_URL}{path}"

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        return {"error": str(e)}


# ============================================================
#  LangChain Tools
# ============================================================

if HAS_LANGCHAIN:

    @tool
    def japan_briefing() -> str:
        """Get a complete Japan market briefing in one call.
        Returns macro indicators, policy rates, Tankan DI, disclosures,
        investor flows, weather, seismic, and calendar data.
        USE THIS FIRST for any general Japan market question."""
        data = _call_api("/api/v1/briefing")
        return json.dumps(data.get("data", data), ensure_ascii=False, indent=2)

    @tool
    def company_intelligence(ticker: str) -> str:
        """Get comprehensive intelligence for a Japanese company by ticker code.
        Combines gBizINFO profile, J-Quants financials, TDnet disclosures,
        EDINET holdings, stock price, and macro context.
        Args:
            ticker: Stock code like '7203' for Toyota, '6501' for Hitachi"""
        data = _call_api(f"/api/v1/intelligence/{ticker}")
        return json.dumps(data.get("data", data), ensure_ascii=False, indent=2)

    @tool
    def market_snapshot() -> str:
        """Get a real-time market snapshot including macro indicators,
        abnormal events, disclosure stats, and investor flow signals."""
        data = _call_api("/api/v1/market/snapshot")
        return json.dumps(data.get("data", data), ensure_ascii=False, indent=2)

    @tool
    def disclosures(days: int = 3, category: str = None) -> str:
        """Get recent corporate disclosures from TDnet (Tokyo Stock Exchange).
        Each disclosure includes category, impact scoring, and company name.
        Args:
            days: Number of days to look back (1-30)
            category: Optional filter (業績修正, M&A・提携, 自社株買い, 配当, etc.)"""
        params = {"days": days, "limit": 50}
        if category:
            params["category"] = category
        data = _call_api("/api/v1/disclosures", params=params)
        return json.dumps(data.get("data", data), ensure_ascii=False, indent=2)

    @tool
    def ai_summarized_disclosures(days: int = 1, min_impact: int = 0) -> str:
        """Get AI-summarized corporate disclosures with English translations.
        Each disclosure includes a 1-line English summary, impact score (1-5),
        and sector relevance. TRANSCODE exclusive data layer.
        Args:
            days: Number of days (1-7)
            min_impact: Minimum impact score filter (0-5)"""
        params = {"days": days, "min_impact": min_impact, "limit": 30}
        data = _call_api("/api/v1/disclosures/summarized", params=params)
        return json.dumps(data.get("data", data), ensure_ascii=False, indent=2)

    @tool
    def holdings(days: int = 7) -> str:
        """Get EDINET large shareholding reports — institutional investor position changes.
        Tracks 5%+ ownership changes in Japanese listed companies.
        Args:
            days: Number of days to look back (1-30)"""
        data = _call_api("/api/v1/holdings", params={"days": days})
        return json.dumps(data.get("data", data), ensure_ascii=False, indent=2)

    @tool
    def investor_flows() -> str:
        """Get JPX investor flow data — are foreigners buying or selling Japan?
        Shows weekly net buy/sell by: foreigners, individuals, trust banks, corporations.
        Updated every Thursday 15:30 JST."""
        data = _call_api("/api/v1/investor-flows")
        return json.dumps(data.get("data", data), ensure_ascii=False, indent=2)

    @tool
    def macro_events() -> str:
        """Detect abnormal macro movements — oil surge, yen shock, VIX spike.
        Each event includes affected tickers (positive and negative)."""
        data = _call_api("/api/v1/macro/events")
        return json.dumps(data.get("data", data), ensure_ascii=False, indent=2)

    @tool
    def tankan_summary() -> str:
        """Get BOJ Tankan survey — Japan's economic thermometer.
        Business confidence DI for large/small × manufacturing/non-manufacturing."""
        data = _call_api("/api/v1/tankan")
        return json.dumps(data.get("data", data), ensure_ascii=False, indent=2)

    @tool
    def economic_calendar(days: int = 30) -> str:
        """Get upcoming Japanese economic events — BOJ meetings, GDP, CPI, holidays.
        Args:
            days: Days ahead to look (1-365)"""
        data = _call_api("/api/v1/calendar", params={"days": days})
        return json.dumps(data.get("data", data), ensure_ascii=False, indent=2)

    @tool
    def batch_intelligence(tickers: str) -> str:
        """Get intelligence for multiple companies at once (Developer/Pro tier).
        Args:
            tickers: Comma-separated ticker codes, e.g. '7203,6501,9984'"""
        ticker_list = [t.strip() for t in tickers.split(",")]
        data = _post_api("/api/v1/batch/intelligence", {"tickers": ticker_list})
        return json.dumps(data.get("data", data), ensure_ascii=False, indent=2)


# ============================================================
#  Tool Registration Helper
# ============================================================

def get_transcode_tools(api_key: str = None) -> list:
    """
    TRANSCODE の LangChain ツール一覧を返す。

    Args:
        api_key: TRANSCODE API キー（未指定時は環境変数 TRANSCODE_API_KEY）

    Returns:
        LangChain Tool のリスト

    Usage:
        from transcode_langchain import get_transcode_tools

        tools = get_transcode_tools("your-api-key")

        # With LangChain Agent
        from langchain_openai import ChatOpenAI
        from langgraph.prebuilt import create_react_agent

        llm = ChatOpenAI(model="gpt-4o")
        agent = create_react_agent(llm, tools)
        result = agent.invoke({"messages": [("user", "What's happening in Japan today?")]})
    """
    if not HAS_LANGCHAIN:
        raise ImportError(
            "langchain-core is required. Install: pip install langchain-core"
        )

    if api_key:
        global TRANSCODE_API_KEY
        TRANSCODE_API_KEY = api_key

    return [
        japan_briefing,
        company_intelligence,
        market_snapshot,
        disclosures,
        ai_summarized_disclosures,
        holdings,
        investor_flows,
        macro_events,
        tankan_summary,
        economic_calendar,
        batch_intelligence,
    ]


# ============================================================
#  Standalone Usage (LangChain不要)
# ============================================================

class TranscodeClient:
    """LangChain不要で TRANSCODE API を使うシンプルクライアント"""

    def __init__(self, api_key: str = None, base_url: str = None):
        self.api_key = api_key or TRANSCODE_API_KEY
        self.base_url = base_url or TRANSCODE_BASE_URL

    def briefing(self) -> dict:
        return _call_api("/api/v1/briefing", self.api_key)

    def intelligence(self, ticker: str) -> dict:
        return _call_api(f"/api/v1/intelligence/{ticker}", self.api_key)

    def snapshot(self) -> dict:
        return _call_api("/api/v1/market/snapshot", self.api_key)

    def disclosures(self, days: int = 3) -> dict:
        return _call_api("/api/v1/disclosures", self.api_key, {"days": days})

    def summarized_disclosures(self, days: int = 1) -> dict:
        return _call_api("/api/v1/disclosures/summarized", self.api_key, {"days": days})

    def holdings(self, days: int = 7) -> dict:
        return _call_api("/api/v1/holdings", self.api_key, {"days": days})

    def investor_flows(self) -> dict:
        return _call_api("/api/v1/investor-flows", self.api_key)

    def tankan(self) -> dict:
        return _call_api("/api/v1/tankan", self.api_key)

    def calendar(self, days: int = 30) -> dict:
        return _call_api("/api/v1/calendar", self.api_key, {"days": days})

    def batch_intelligence(self, tickers: list) -> dict:
        return _post_api("/api/v1/batch/intelligence", {"tickers": tickers}, self.api_key)


if __name__ == "__main__":
    # Quick test
    client = TranscodeClient()
    result = client.briefing()
    print(json.dumps(result, indent=2, ensure_ascii=False)[:500])
