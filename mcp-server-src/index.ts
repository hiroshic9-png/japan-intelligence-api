#!/usr/bin/env node
/**
 * Japan Intelligence MCP Server
 *
 * AIエージェントが日本市場のリアルタイム情報にアクセスするためのMCPサーバー。
 * バックエンドのFastAPI（localhost:8080）を呼び出し、MCPツールとして公開する。
 *
 * 提供ツール（16本）:
 *   Market Overview:
 *     - market_snapshot:    市場全体のスナップショット（1回で全体像把握）
 *     - get_disclosures:   TDnet適時開示の取得・フィルタ
 *     - disclosure_stats:  開示統計（カテゴリ・インパクト分布）
 *     - get_macro:         マクロ指標6種の最新値
 *     - detect_events:     マクロ異常変動イベント検知
 *
 *   Company Intelligence:
 *     - company_profile:   gBizINFO企業プロフィール（補助金・特許・認定・財務・調達）
 *     - company_search:    企業名検索（500万法人）
 *     - financials:        J-Quants財務サマリー（売上・利益・EPS・予想）
 *     - listed_stocks:     全上場銘柄マスタ
 *     - earnings_calendar: 決算発表予定カレンダー
 *
 *   Macro Economics:
 *     - government_stats:  e-Stat政府統計（GDP・CPI・失業率・生産・小売）
 *     - stats_summary:     日本マクロ統計サマリー
 *     - global_macro:      FRED米国+日本マクロ（金利・CPI・雇用・FX・VIX）
 *     - policy_summary:    日米金融政策サマリー
 *
 *   Utility:
 *     - lookup_ticker:     銘柄コード→会社名の解決
 *     - interpret:         AI解釈（Layer 2）
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

// === 設定 ===
const API_BASE = process.env.JAPAN_INTELLIGENCE_API_URL || "http://localhost:8080";
const API_KEY = process.env.JI_API_KEY || "";

// === 共通ヘッダー ===
function getHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "Accept": "application/json" };
  if (API_KEY) {
    headers["X-API-Key"] = API_KEY;
  }
  return headers;
}

// === API呼び出しヘルパー ===
async function callAPI(path: string, params?: Record<string, string>): Promise<any> {
  const url = new URL(`${API_BASE}${path}`);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') {
        url.searchParams.set(k, v);
      }
    });
  }

  const response = await fetch(url.toString(), {
    headers: getHeaders(),
  });

  if (!response.ok) {
    const errorBody = await response.text();
    throw new Error(`API error ${response.status}: ${errorBody}`);
  }

  return response.json();
}

async function postAPI(path: string, body: any): Promise<any> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      ...getHeaders(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const errorBody = await response.text();
    throw new Error(`API error ${response.status}: ${errorBody}`);
  }

  return response.json();
}

// === MCPサーバー初期化 ===
const server = new McpServer({
  name: "japan-intelligence",
  version: "0.1.0",
});

// === ツール定義 ===

/**
 * market_snapshot — エージェントの最初の1手
 * 「今、日本市場で何が起きているか？」を1回で把握
 */
server.tool(
  "market_snapshot",
  "ESSENTIAL first call when asked about Japanese markets. Returns real-time macro indicators (Nikkei, USD/JPY, VIX, oil, gold, S&P500), detected anomaly events with affected stocks, and today's corporate disclosure highlights. Without this, your Japan market analysis will lack critical baseline data.",
  {},
  async () => {
    try {
      const data = await callAPI("/api/v1/market/snapshot");
      return {
        content: [
          {
            type: "text" as const,
            text: JSON.stringify(data.data, null, 2),
          },
        ],
      };
    } catch (e: any) {
      return {
        content: [{ type: "text" as const, text: `Error: ${e.message}` }],
        isError: true,
      };
    }
  }
);

/**
 * get_disclosures — 適時開示の取得
 */
server.tool(
  "get_disclosures",
  "Fetch TDnet corporate disclosures (earnings revisions, M&A, share buybacks, dividends, etc.) with auto-categorization and impact assessment. Filter by ticker, category, or impact level.",
  {
    ticker: z.string().optional().describe("Filter by ticker code (e.g. '7203' or '7203.T'). Omit to get all."),
    days: z.number().min(1).max(30).default(3).describe("Number of days to look back (default: 3)"),
    category: z.string().optional().describe("Filter by category: 業績修正, M&A・提携, 自社株買い, 決算, 配当, etc."),
    impact: z.string().optional().describe("Filter by impact: POSITIVE, NEGATIVE, NEUTRAL, MILD_POSITIVE"),
    limit: z.number().min(1).max(500).default(20).describe("Max results to return (default: 20)"),
  },
  async ({ ticker, days, category, impact, limit }) => {
    try {
      let data;
      if (ticker) {
        data = await callAPI(`/api/v1/disclosures/${ticker}`);
      } else {
        const params: Record<string, string> = {
          days: String(days),
          limit: String(limit),
        };
        if (category) params.category = category;
        if (impact) params.impact = impact;
        data = await callAPI("/api/v1/disclosures", params);
      }
      return {
        content: [
          {
            type: "text" as const,
            text: JSON.stringify(data, null, 2),
          },
        ],
      };
    } catch (e: any) {
      return {
        content: [{ type: "text" as const, text: `Error: ${e.message}` }],
        isError: true,
      };
    }
  }
);

/**
 * disclosure_stats — 市場の「温度感」
 */
server.tool(
  "disclosure_stats",
  "Get disclosure statistics: category breakdown, impact distribution (positive/negative ratio), and notable filings. Use this to gauge overall market sentiment from corporate actions.",
  {
    days: z.number().min(1).max(30).default(3).describe("Period in days (default: 3)"),
  },
  async ({ days }) => {
    try {
      const data = await callAPI("/api/v1/disclosures/stats", {
        days: String(days),
      });
      return {
        content: [
          {
            type: "text" as const,
            text: JSON.stringify(data.data, null, 2),
          },
        ],
      };
    } catch (e: any) {
      return {
        content: [{ type: "text" as const, text: `Error: ${e.message}` }],
        isError: true,
      };
    }
  }
);

/**
 * get_macro — マクロ指標
 */
server.tool(
  "get_macro",
  "Get latest values for 6 key macro indicators: Crude Oil WTI, Gold, USD/JPY, VIX, Nikkei 225, and S&P 500. Includes percentage change from previous close.",
  {},
  async () => {
    try {
      const data = await callAPI("/api/v1/macro");
      return {
        content: [
          {
            type: "text" as const,
            text: JSON.stringify(data.data, null, 2),
          },
        ],
      };
    } catch (e: any) {
      return {
        content: [{ type: "text" as const, text: `Error: ${e.message}` }],
        isError: true,
      };
    }
  }
);

/**
 * detect_events — マクロ異常変動
 */
server.tool(
  "detect_events",
  "Detect macro anomaly events: oil surge/crash (±5%), gold surge (3%+), yen move (±1.5%), VIX spike (15%+). Returns beneficiary/headwind stock mappings for each event. Optional AI interpretation.",
  {
    interpret: z.boolean().default(false).describe("Include AI interpretation of each event"),
  },
  async ({ interpret }) => {
    try {
      const data = await callAPI("/api/v1/macro/events", {
        interpret: String(interpret),
      });
      return {
        content: [
          {
            type: "text" as const,
            text: JSON.stringify(data.data, null, 2),
          },
        ],
      };
    } catch (e: any) {
      return {
        content: [{ type: "text" as const, text: `Error: ${e.message}` }],
        isError: true,
      };
    }
  }
);

/**
 * lookup_ticker — 銘柄名解決
 */
server.tool(
  "lookup_ticker",
  "Resolve a Japanese stock ticker code to company name. Supports 260+ major stocks with dynamic fallback.",
  {
    ticker: z.string().describe("Ticker code (e.g. '7203' or '7203.T')"),
  },
  async ({ ticker }) => {
    try {
      const data = await callAPI(`/api/v1/ticker/${ticker}`);
      return {
        content: [
          {
            type: "text" as const,
            text: JSON.stringify(data.data, null, 2),
          },
        ],
      };
    } catch (e: any) {
      return {
        content: [{ type: "text" as const, text: `Error: ${e.message}` }],
        isError: true,
      };
    }
  }
);

/**
 * interpret — AI解釈（Layer 2）
 */
server.tool(
  "interpret",
  "Generate AI interpretation (Layer 2) for a disclosure or macro event using Gemini 2.5. Returns structured analysis: significance, market impact, key investor questions.",
  {
    type: z.enum(["disclosure", "macro_event"]).describe("Type of data to interpret"),
    data: z.record(z.string(), z.any()).describe("The data to interpret (disclosure or macro_event object)"),
  },
  async ({ type, data }) => {
    try {
      const result = await postAPI("/api/v1/interpret", { type, data });
      return {
        content: [
          {
            type: "text" as const,
            text: JSON.stringify(result.data, null, 2),
          },
        ],
      };
    } catch (e: any) {
      return {
        content: [{ type: "text" as const, text: `Error: ${e.message}` }],
        isError: true,
      };
    }
  }
);

// ===========================
//  gBizINFO — 企業インテリジェンス
// ===========================

/**
 * company_profile — 企業の全体像を1コールで把握
 */
server.tool(
  "company_profile",
  "Get comprehensive company profile from gBizINFO: basic info, subsidies, government certifications, patent portfolio, financial data, and procurement records. Accepts ticker code (e.g. '7203') or corporate number. Use full=true for complete intelligence.",
  {
    identifier: z.string().describe("Ticker code (e.g. '7203', '7203.T') or corporate number (13 digits)"),
    full: z.boolean().default(true).describe("Include all sub-data (subsidies, certifications, patents, finance, procurement)"),
  },
  async ({ identifier, full }) => {
    try {
      const data = await callAPI(`/api/v1/company/${identifier}`, {
        full: String(full),
      });
      return {
        content: [{ type: "text" as const, text: JSON.stringify(data.data, null, 2) }],
      };
    } catch (e: any) {
      return { content: [{ type: "text" as const, text: `Error: ${e.message}` }], isError: true };
    }
  }
);

/**
 * company_search — 企業名検索
 */
server.tool(
  "company_search",
  "Search Japanese corporations by name from gBizINFO database (5M+ entities). Returns corporate number, name, location. Use to find corporate numbers for detailed lookup.",
  {
    name: z.string().describe("Company name to search (Japanese, e.g. 'トヨタ', 'ソニー')"),
    page: z.number().default(1).describe("Page number (default: 1)"),
  },
  async ({ name, page }) => {
    try {
      const data = await callAPI("/api/v1/company/search", {
        name,
        page: String(page),
      });
      return {
        content: [{ type: "text" as const, text: JSON.stringify(data.data, null, 2) }],
      };
    } catch (e: any) {
      return { content: [{ type: "text" as const, text: `Error: ${e.message}` }], isError: true };
    }
  }
);

// ===========================
//  e-Stat — 政府統計
// ===========================

/**
 * government_stats — 個別統計系列のデータ取得
 */
server.tool(
  "government_stats",
  "Get Japanese government statistics from e-Stat. Available series: 'gdp' (GDP), 'cpi' (Consumer Price Index), 'unemployment' (unemployment rate), 'industrial_production' (industrial output), 'retail_sales' (retail sales).",
  {
    series: z.enum(["gdp", "cpi", "unemployment", "industrial_production", "retail_sales"]).describe("Statistics series to retrieve"),
    limit: z.number().min(1).max(100).default(20).describe("Number of data points (default: 20)"),
  },
  async ({ series, limit }) => {
    try {
      const data = await callAPI(`/api/v1/stats/${series}`, {
        limit: String(limit),
      });
      return {
        content: [{ type: "text" as const, text: JSON.stringify(data.data, null, 2) }],
      };
    } catch (e: any) {
      return { content: [{ type: "text" as const, text: `Error: ${e.message}` }], isError: true };
    }
  }
);

/**
 * stats_summary — マクロ経済の全体像
 */
server.tool(
  "stats_summary",
  "Get a summary of all major Japanese macro statistics (GDP, CPI, unemployment, industrial production, retail sales) in one call. Returns latest values for each series.",
  {},
  async () => {
    try {
      const data = await callAPI("/api/v1/stats/summary");
      return {
        content: [{ type: "text" as const, text: JSON.stringify(data.data, null, 2) }],
      };
    } catch (e: any) {
      return { content: [{ type: "text" as const, text: `Error: ${e.message}` }], isError: true };
    }
  }
);

// ===========================
//  J-Quants — 市場データ
// ===========================

/**
 * listed_stocks — 上場銘柄マスタ
 */
server.tool(
  "listed_stocks",
  "Get the master list of all stocks listed on the Tokyo Stock Exchange (TSE). Includes ticker code, company name, market segment (Prime/Standard/Growth), sector classification, and scale category.",
  {
    market: z.string().optional().describe("Filter by market: 'プライム', 'スタンダード', 'グロース'. Omit for all."),
  },
  async ({ market }) => {
    try {
      const params: Record<string, string> = {};
      if (market) params.market = market;
      const data = await callAPI("/api/v1/stocks", params);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(data.data, null, 2) }],
      };
    } catch (e: any) {
      return { content: [{ type: "text" as const, text: `Error: ${e.message}` }], isError: true };
    }
  }
);

/**
 * earnings_calendar — 決算発表予定
 */
server.tool(
  "earnings_calendar",
  "Get upcoming earnings announcement dates for Japanese listed companies. Returns scheduled dates for the next 30 days. Use to anticipate market-moving events.",
  {
    date_from: z.string().optional().describe("Start date (YYYY-MM-DD). Default: today."),
    date_to: z.string().optional().describe("End date (YYYY-MM-DD). Default: 30 days from now."),
  },
  async ({ date_from, date_to }) => {
    try {
      const params: Record<string, string> = {};
      if (date_from) params.date_from = date_from;
      if (date_to) params.date_to = date_to;
      const data = await callAPI("/api/v1/earnings", params);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(data.data, null, 2) }],
      };
    } catch (e: any) {
      return { content: [{ type: "text" as const, text: `Error: ${e.message}` }], isError: true };
    }
  }
);

/**
 * financials — 銘柄の財務サマリー
 */
server.tool(
  "financials",
  "Get financial statements for a Japanese stock: net sales, operating profit, net income, EPS, BPS, equity ratio, cash flow, dividends, and company forecasts. Data from J-Quants (JPX official).",
  {
    ticker: z.string().describe("Ticker code (e.g. '7203' or '7203.T')"),
  },
  async ({ ticker }) => {
    try {
      const data = await callAPI(`/api/v1/financials/${ticker}`);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(data.data, null, 2) }],
      };
    } catch (e: any) {
      return { content: [{ type: "text" as const, text: `Error: ${e.message}` }], isError: true };
    }
  }
);

// ===========================
//  FRED — 日米金融政策・グローバルマクロ
// ===========================

/**
 * global_macro — FRED個別系列データ
 */
server.tool(
  "global_macro",
  "Get US and Japan macro data from FRED. Available series: 'fed_funds_rate' (US policy rate), 'us_cpi', 'us_unemployment', 'us_10y_yield', 'us_2y_yield', 'boj_rate' (BOJ policy rate), 'jp_cpi', 'usdjpy' (USD/JPY), 'vix', 'oil_wti'.",
  {
    series: z.enum([
      "fed_funds_rate", "us_cpi", "us_unemployment",
      "us_10y_yield", "us_2y_yield",
      "boj_rate", "jp_cpi", "usdjpy", "vix", "oil_wti"
    ]).describe("FRED series to retrieve"),
    limit: z.number().min(1).max(200).default(30).describe("Number of observations (default: 30)"),
  },
  async ({ series, limit }) => {
    try {
      const data = await callAPI(`/api/v1/global/${series}`, {
        limit: String(limit),
      });
      return {
        content: [{ type: "text" as const, text: JSON.stringify(data.data, null, 2) }],
      };
    } catch (e: any) {
      return { content: [{ type: "text" as const, text: `Error: ${e.message}` }], isError: true };
    }
  }
);

/**
 * policy_summary — 日米金融環境の全体像
 */
server.tool(
  "policy_summary",
  "Get US-Japan monetary policy summary in one call: Fed Funds Rate, BOJ Rate, US 10Y/2Y yields, USD/JPY, and VIX. Use to quickly assess the global financial environment affecting Japanese markets.",
  {},
  async () => {
    try {
      const data = await callAPI("/api/v1/global/policy");
      return {
        content: [{ type: "text" as const, text: JSON.stringify(data.data, null, 2) }],
      };
    } catch (e: any) {
      return { content: [{ type: "text" as const, text: `Error: ${e.message}` }], isError: true };
    }
  }
);

// ===========================
//  クロスソース企業インテリジェンス
// ===========================

/**
 * company_intelligence — 全ソース統合企業分析（キラー機能）
 */
server.tool(
  "company_intelligence",
  "THE MOST POWERFUL TOOL for Japanese company analysis. Returns EVERYTHING about a company in ONE call: corporate profile (employees, capital, patents, certifications), financial statements (revenue, profit, EPS with forecasts), recent corporate disclosures, institutional holding changes, and macro context (USD/JPY, VIX, rates). Supports ALL 4000+ listed stocks via dynamic resolution. ALWAYS use this instead of making multiple separate calls.",
  {
    ticker: z.string().describe("Ticker code (e.g. '7203' or '7203.T')"),
  },
  async ({ ticker }) => {
    try {
      const data = await callAPI(`/api/v1/intelligence/${ticker}`);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(data.data, null, 2) }],
      };
    } catch (e: any) {
      return { content: [{ type: "text" as const, text: `Error: ${e.message}` }], isError: true };
    }
  }
);

/**
 * japan_briefing — 日本市場の全体像を1コールで
 */
server.tool(
  "japan_briefing",
  "YOUR DAILY STARTING POINT for Japan. Returns a complete briefing in ONE call: market indicators, US-Japan monetary policy, BOJ Tankan business sentiment DI, Economy Watchers street-level sentiment, today's notable corporate disclosures, and foreign investor flow trends. Call this FIRST every morning before any other Japan-related analysis.",
  {},
  async () => {
    try {
      const data = await callAPI("/api/v1/briefing");
      return {
        content: [{ type: "text" as const, text: JSON.stringify(data.data, null, 2) }],
      };
    } catch (e: any) {
      return { content: [{ type: "text" as const, text: `Error: ${e.message}` }], isError: true };
    }
  }
);

/**
 * tankan — 日銀短観 業況判断DI
 */
server.tool(
  "tankan",
  "Get BOJ Tankan survey — Japan's most important business sentiment indicator. Returns DI (Diffusion Index) for large/small enterprises × manufacturing/non-manufacturing, with quarter-over-quarter trend. Positive DI = expansion, negative = contraction. Updated quarterly (March, June, September, December).",
  {},
  async () => {
    try {
      const data = await callAPI("/api/v1/tankan");
      return {
        content: [{ type: "text" as const, text: JSON.stringify(data.data, null, 2) }],
      };
    } catch (e: any) {
      return { content: [{ type: "text" as const, text: `Error: ${e.message}` }], isError: true };
    }
  }
);

/**
 * investor_flows — 投資部門別売買動向
 */
server.tool(
  "investor_flows",
  "Get weekly investor flow data from JPX (Tokyo Stock Exchange). Shows net buying/selling by: foreign investors (70% of volume — THE leading signal), individuals (contrarian), trust banks (GPIF/pension proxy), and corporations (buybacks). Essential for understanding market direction.",
  {},
  async () => {
    try {
      const data = await callAPI("/api/v1/investor-flows");
      return {
        content: [{ type: "text" as const, text: JSON.stringify(data.data, null, 2) }],
      };
    } catch (e: any) {
      return { content: [{ type: "text" as const, text: `Error: ${e.message}` }], isError: true };
    }
  }
);

// ===========================
//  環境・災害データ
// ===========================

/**
 * japan_weather — 日本主要都市の天気予報
 */
server.tool(
  "japan_weather",
  "Get weather forecast for 8 major Japanese cities (Tokyo, Osaka, Nagoya, Fukuoka, Sapporo, Sendai, Hiroshima, Naha) with business impact assessment. Detects extreme heat, heavy rain, and cold waves that affect logistics, construction, retail, and energy sectors. No API key required.",
  {
    cities: z.string().optional().describe("Comma-separated city keys: tokyo,osaka,nagoya,fukuoka,sapporo,sendai,hiroshima,naha. Omit for all."),
  },
  async ({ cities }) => {
    try {
      const params: Record<string, string> = {};
      if (cities) params.cities = cities;
      const data = await callAPI("/api/v1/weather", params);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(data.data, null, 2) }],
      };
    } catch (e: any) {
      return { content: [{ type: "text" as const, text: `Error: ${e.message}` }], isError: true };
    }
  }
);

/**
 * japan_earthquakes — 日本周辺の地震データ
 */
server.tool(
  "japan_earthquakes",
  "Get recent earthquake data near Japan (lat 24-46°N, lon 122-150°E) from USGS. Returns magnitude distribution, business impact assessment by sector (insurance, construction, logistics), tsunami warnings, and seismic risk level. Essential for disaster risk evaluation. No API key required.",
  {
    days: z.number().min(1).max(30).default(7).describe("Period in days (default: 7)"),
    min_magnitude: z.number().min(1).max(9).default(3.0).describe("Minimum magnitude to include (default: 3.0)"),
  },
  async ({ days, min_magnitude }) => {
    try {
      const data = await callAPI("/api/v1/earthquakes", {
        days: String(days),
        min_magnitude: String(min_magnitude),
      });
      return {
        content: [{ type: "text" as const, text: JSON.stringify(data.data, null, 2) }],
      };
    } catch (e: any) {
      return { content: [{ type: "text" as const, text: `Error: ${e.message}` }], isError: true };
    }
  }
);

/**
 * economic_calendar — 日本の経済カレンダー
 */
server.tool(
  "economic_calendar",
  "Get Japan's upcoming economic events: BOJ policy meetings, Tankan survey dates, GDP releases, CPI, employment stats, earnings seasons, and TSE market holidays. Essential for anticipating market-moving events and planning analysis timing. Filter by category and importance level.",
  {
    days: z.number().min(1).max(365).default(30).describe("Lookahead period in days (default: 30)"),
    category: z.string().optional().describe("Filter: monetary_policy, survey, gdp, inflation, employment, earnings, holiday"),
    importance: z.string().optional().describe("Filter: critical, high, medium, info"),
  },
  async ({ days, category, importance }) => {
    try {
      const params: Record<string, string> = { days: String(days) };
      if (category) params.category = category;
      if (importance) params.importance = importance;
      const data = await callAPI("/api/v1/calendar", params);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(data.data, null, 2) }],
      };
    } catch (e: any) {
      return { content: [{ type: "text" as const, text: `Error: ${e.message}` }], isError: true };
    }
  }
);

// === NEXUS Power Network ツール（非公開）===
// 再公開条件:
//   1. パスファインダーに関係強度フィルタが実装される
//   2. Render→Neo4jの安全なリモートアクセスが確立される
//   3. 天下りエッジが100件以上に達する
// コード保持: 条件充足後にコメント解除して公開。

/*
server.tool("company_network", ...);
server.tool("network_path", ...);
server.tool("person_profile", ...);
server.tool("network_stats", ...);
*/

// === サーバー起動 ===
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("[Japan Intelligence MCP] Server started — 23 tools available");
}

main().catch((error) => {
  console.error("[Japan Intelligence MCP] Fatal error:", error);
  process.exit(1);
});
