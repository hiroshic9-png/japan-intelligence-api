# Japan Intelligence API

**AIエージェントのための日本市場インテリジェンス基盤**

Japan Intelligence は、日本の公開情報を構造化し、AIエージェントが即座に利用可能な形式で提供するAPIプラットフォームです。**10のデータソース**を横断統合し、企業分析・マクロ経済・金融政策を**35エンドポイント + 22 MCPツール**で完結させます。

> 🎯 **1つのAPIキーで日本の全て** — 適時開示、機関投資家の持分変動、500万法人のデータベース、政府統計10系列、株価ヒストリカル、日銀短観、投資部門別売買動向、日米金融政策、AI解釈を統合提供

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    AI Agent (Claude, Cursor, etc.)                │
│                          ↓ MCP (22 tools)                        │
│              ┌──────────────────────────────┐                    │
│              │   MCP Server (22 tools)       │                   │
│              └──────────────┬───────────────┘                    │
│                             ↓ REST API (35 endpoints)            │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │              Japan Intelligence API (FastAPI)             │    │
│  │                                                          │    │
│  │  Layer 2: AI Interpretation (Gemini 2.5 Flash)           │    │
│  │  Layer 1: Structured Data + Cache-Control (per-source)   │    │
│  │                                                          │    │
│  │  ┌─────┐ ┌──────┐ ┌────────┐ ┌──────┐ ┌────────┐       │    │
│  │  │TDnet│ │EDINET│ │gBizINFO│ │e-Stat│ │J-Quants│       │    │
│  │  └─────┘ └──────┘ └────────┘ └──────┘ └────────┘       │    │
│  │  ┌────┐ ┌───┐ ┌───┐ ┌─────┐ ┌───────────┐              │    │
│  │  │FRED│ │BOJ│ │JPX│ │Macro│ │Interpreter│               │    │
│  │  └────┘ └───┘ └───┘ └─────┘ └───────────┘              │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

## Data Sources (10)

| # | Source | Data | Coverage |
|---|--------|------|----------|
| 1 | **TDnet** | 適時開示 — 業績修正、M&A、自社株買い、配当等15カテゴリ自動分類 | 全上場企業 |
| 2 | **EDINET** | 大量保有報告書 — 機関投資家の持分変動（5%超） | 全上場企業 |
| 3 | **gBizINFO** | 企業情報 — 補助金、認定、特許、財務、調達 | 500万法人 |
| 4 | **e-Stat** | 政府統計10系列 — GDP、CPI、失業率、鉱工業生産、小売、景気ウォッチャー、家計調査、貿易統計 | 日本経済全体 |
| 5 | **J-Quants** | 市場データ — 全銘柄マスタ、決算、財務、株価ヒストリカル（OHLCV + 移動平均）、セクター分析 | 全上場銘柄 |
| 6 | **FRED** | 日米マクロ — 金利、CPI、雇用、為替、VIX（10系列） | 米国+日本 |
| 7 | **BOJ** | 日銀短観 — 業況判断DI（大企業/中小×製造業/非製造業＋設備投資計画） | 四半期更新 |
| 8 | **JPX** | 投資部門別売買動向 — 外国人、個人、信託銀行、事業法人（9部門構造化） | 週次 |
| 9 | **Macro** | リアルタイム指標 — 原油、金、ドル円、VIX、日経、S&P + 異常変動検知 | 6指標 |
| 10 | **AI** | Gemini 2.5 Flash による構造化データ解釈（Layer 2） | 全データ |

## Key Endpoints (35)

### Intelligence — 1コールで全て把握

```bash
# 日本全体ブリーフィング（朝の第一手）★ 
GET /api/v1/briefing

# 企業インテリジェンス — 6軸分析（プロフィール+財務+株価+開示+保有+マクロ）★
GET /api/v1/intelligence/{ticker}

# マーケットスナップショット — 市場全体 + 投資部門別フロー + セクター概況
GET /api/v1/market/snapshot

# 開示統計 — 市場の温度感
GET /api/v1/disclosures/stats
```

### Corporate Data

```bash
GET /api/v1/company/{id}              # 企業プロフィール
GET /api/v1/company/{id}/patents      # 特許ポートフォリオ
GET /api/v1/company/{id}/subsidies    # 補助金実績
GET /api/v1/company/{id}/certifications # 認定情報
GET /api/v1/company/{id}/finance      # 財務データ
GET /api/v1/company/search?name=ソニー # 企業名検索
GET /api/v1/disclosures               # 適時開示一覧
GET /api/v1/disclosures/{ticker}      # 銘柄別開示
GET /api/v1/holdings                   # 大量保有報告
GET /api/v1/holdings/{ticker}          # 銘柄別大量保有
```

### Market & Financials

```bash
GET /api/v1/financials/{ticker}  # 財務サマリー（売上・利益・EPS・予想）
GET /api/v1/stocks               # 全上場銘柄マスタ
GET /api/v1/earnings             # 決算カレンダー
GET /api/v1/prices/{ticker}      # 株価ヒストリカル（OHLCV + MA5/25/75 + 騰落率）★NEW
GET /api/v1/sectors              # セクター分析（17/33業種 + 市場区分別構成）★NEW
```

### Government Statistics & Global Macro

```bash
GET /api/v1/stats/series         # 利用可能統計系列一覧
GET /api/v1/stats/summary        # マクロ統計サマリー（1コール）
GET /api/v1/stats/{series_id}    # 個別統計（gdp, cpi, unemployment等10系列）
GET /api/v1/stats/search/{kw}    # 統計検索
GET /api/v1/global/series        # FRED系列一覧
GET /api/v1/global/policy        # 日米金融政策サマリー（1コール）
GET /api/v1/global/{series_key}  # FRED個別系列
GET /api/v1/tankan               # 日銀短観サマリー
GET /api/v1/tankan/{series_id}   # 短観個別系列
GET /api/v1/tankan/series/list   # 短観系列一覧
GET /api/v1/investor-flows       # 投資部門別売買動向（9部門構造化）
```

### Macro & Events

```bash
GET  /api/v1/macro               # マクロ6指標
GET  /api/v1/macro/events        # 異常変動検知 + 恩恵/逆風銘柄
POST /api/v1/interpret           # AI解釈（Layer 2）
GET  /api/v1/ticker/{ticker}     # 銘柄名解決
GET  /api/v1/health              # ヘルスチェック
```

## Response Caching

ソース特性別に最適化されたHTTPキャッシュ：

| Source | Cache-Control max-age | 理由 |
|--------|----------------------|------|
| TDnet | 5分 | リアルタイム性重視 |
| Macro | 5分 | リアルタイム性重視 |
| Intelligence | 10分 | 複合ソース |
| FRED | 1時間 | 高頻度参照 |
| e-Stat | 6時間 | 月次更新 |
| BOJ | 6時間 | 四半期更新 |
| EDINET | 6時間 | 日次更新 |
| J-Quants | 12時間 | 日次更新 |
| JPX | 12時間 | 週次更新 |
| gBizINFO | 24時間 | 低頻度更新 |

ETag対応（304 Not Modified）、stale-while-revalidate対応。

## Authentication

All endpoints (except `/docs`, `/redoc`, `/health`) require API key authentication:

```bash
# Header authentication (recommended)
curl -H "X-API-Key: YOUR_API_KEY" https://japan-intelligence-api.onrender.com/api/v1/briefing

# Bearer token
curl -H "Authorization: Bearer YOUR_API_KEY" https://japan-intelligence-api.onrender.com/api/v1/briefing

# Query parameter
curl "https://japan-intelligence-api.onrender.com/api/v1/briefing?api_key=YOUR_API_KEY"
```

Rate limit: **100 requests/hour** per API key (X-RateLimit-Limit/Remaining headers).

## MCP Server (22 tools for AI Agents)

| Category | Tool | Description |
|----------|------|-------------|
| **Intelligence** | `japan_briefing` | 🌟 Daily briefing — market, policy, tankan, sentiment, investor flows |
| | `market_snapshot` | Market overview — macro + events + disclosures + investor flows + sectors |
| | `company_intelligence` | 🌟 Cross-source 6-axis company analysis (profile + financials + stock price + disclosures + holdings + macro) |
| | `disclosure_stats` | Disclosure statistics — sentiment gauge |
| **Market** | `get_disclosures` | TDnet corporate disclosures with impact assessment |
| | `get_macro` | 6 key macro indicators (Nikkei, USD/JPY, VIX, etc.) |
| | `detect_events` | Macro anomaly detection with stock mapping |
| **Company** | `company_profile` | gBizINFO full company data (patents, subsidies, etc.) |
| | `company_search` | Search 5M+ corporations |
| | `financials` | J-Quants financial statements with forecasts |
| | `listed_stocks` | All listed stocks master |
| | `earnings_calendar` | Upcoming earnings dates |
| | `stock_prices` | 🆕 Stock price history with MA5/25/75 + daily/weekly/monthly changes |
| | `sector_summary` | 🆕 Market structure — 17/33 sector classifications + market segment distribution |
| **Economics** | `government_stats` | e-Stat 10 series (GDP, CPI, economy watchers, trade, etc.) |
| | `stats_summary` | Macro statistics summary (1 call) |
| | `global_macro` | FRED US + Japan macro (rates, CPI, FX, VIX) |
| | `policy_summary` | US-Japan monetary policy summary (1 call) |
| | `tankan` | BOJ Tankan business sentiment DI |
| | `investor_flows` | JPX weekly investor flow data (9 categories with directional signals) |
| **Utility** | `lookup_ticker` | Ticker → company name resolution |
| | `interpret` | AI interpretation (Layer 2, Gemini 2.5) |

### Claude Desktop / Cursor Configuration

```json
{
  "mcpServers": {
    "japan-intelligence": {
      "command": "node",
      "args": ["/path/to/mcp-server/dist/index.js"],
      "env": {
        "JAPAN_INTELLIGENCE_API_URL": "https://japan-intelligence-api.onrender.com",
        "JI_API_KEY": "YOUR_API_KEY"
      }
    }
  }
}
```

## Quick Start

```bash
# 1. Clone
git clone https://github.com/hiroshic9-png/japan-intelligence-api.git
cd japan-intelligence-api

# 2. Setup
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Edit .env with your API keys

# 4. Run
python -m api.main
# → http://localhost:8080/docs
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `EDINET_API_KEY` | Yes | EDINET disclosure API key |
| `GEMINI_API_KEY` | Yes | Google Gemini API key (Layer 2 interpretation) |
| `GBIZ_API_TOKEN` | Yes | gBizINFO API token |
| `ESTAT_APP_ID` | Yes | e-Stat application ID |
| `JQUANTS_API_KEY` | Yes | J-Quants v2 API key |
| `FRED_API_KEY` | Yes | FRED API key |
| `JI_API_KEY` | Optional | API authentication key (enables auth when set) |
| `RATE_LIMIT_PER_HOUR` | Optional | Rate limit (default: 100) |

## API Documentation

Interactive documentation:
- **Swagger UI**: https://japan-intelligence-api.onrender.com/docs
- **ReDoc**: https://japan-intelligence-api.onrender.com/redoc

## License

Proprietary. All rights reserved.
