# Japan Intelligence API

**AIエージェントのための日本市場インテリジェンス基盤**

Japan Intelligence は、日本の公開情報を構造化し、AIエージェントが即座に利用可能な形式で提供するAPIプラットフォームです。8つのデータソースを横断統合し、企業分析・マクロ経済・金融政策を1つのAPIで完結させます。

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    AI Agent (Claude, etc.)                │
│                          ↓ MCP                           │
│              ┌─────────────────────────┐                 │
│              │   MCP Server (17 tools)  │                │
│              └────────────┬────────────┘                 │
│                           ↓ REST API                     │
│  ┌────────────────────────────────────────────────────┐  │
│  │            Japan Intelligence API (FastAPI)         │  │
│  │                                                    │  │
│  │  Layer 2: AI Interpretation (Gemini 2.5 Flash)     │  │
│  │  Layer 1: Structured Data                          │  │
│  │                                                    │  │
│  │  ┌─────┐ ┌──────┐ ┌────────┐ ┌──────┐ ┌────────┐ │  │
│  │  │TDnet│ │EDINET│ │gBizINFO│ │e-Stat│ │J-Quants│ │  │
│  │  └─────┘ └──────┘ └────────┘ └──────┘ └────────┘ │  │
│  │  ┌────┐ ┌─────┐ ┌───────────┐                     │  │
│  │  │FRED│ │Macro│ │Interpreter│                      │  │
│  │  └────┘ └─────┘ └───────────┘                     │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

## Data Sources

| Source | Data | Coverage |
|--------|------|----------|
| **TDnet** | 適時開示 — 業績修正、M&A、自社株買い、配当 | 全上場企業 |
| **EDINET** | 大量保有報告書 — 機関投資家の持分変動 | 5%超保有 |
| **gBizINFO** | 企業情報 — 補助金、認定、特許、財務、調達 | 500万法人 |
| **e-Stat** | 政府統計 — GDP、CPI、失業率、鉱工業生産、小売 | 日本経済全体 |
| **J-Quants** | 市場データ — 銘柄マスタ、決算カレンダー、財務 | 全上場銘柄 |
| **FRED** | 日米マクロ — 金利、CPI、雇用、為替、VIX | 米国+日本 |
| **Macro** | リアルタイム指標 — 原油、金、ドル円、VIX、日経、S&P | 6指標 |
| **AI** | Gemini 2.5 Flash による構造化データ解釈 | 全データ |

## Key Endpoints

### Cross-Source Intelligence

```bash
# 企業インテリジェンス — 5ソース横断統合（キラー機能）
GET /api/v1/intelligence/{ticker}

# マーケットスナップショット — 市場全体を1コールで把握
GET /api/v1/market/snapshot
```

### Corporate Data

```bash
GET /api/v1/company/{id}              # 企業プロフィール
GET /api/v1/company/{id}/patents      # 特許ポートフォリオ
GET /api/v1/company/{id}/subsidies    # 補助金実績
GET /api/v1/company/search?name=ソニー # 企業名検索
GET /api/v1/disclosures               # 適時開示一覧
GET /api/v1/holdings                   # 大量保有報告
```

### Market & Financials

```bash
GET /api/v1/financials/{ticker}  # 財務サマリー（売上・利益・EPS・予想）
GET /api/v1/stocks               # 全上場銘柄マスタ
GET /api/v1/earnings             # 決算カレンダー
GET /api/v1/macro                # マクロ6指標
GET /api/v1/macro/events         # 異常変動検知 + 恩恵/逆風銘柄
```

### Government Statistics & Global Macro

```bash
GET /api/v1/stats/gdp            # GDP
GET /api/v1/stats/cpi            # 消費者物価指数
GET /api/v1/stats/summary        # マクロ統計サマリー
GET /api/v1/global/policy        # 日米金融政策サマリー
GET /api/v1/global/fed_funds_rate # FF金利時系列
GET /api/v1/global/usdjpy        # ドル円時系列
```

### AI Interpretation

```bash
POST /api/v1/interpret           # 構造化データのAI解釈
```

## Authentication

All endpoints (except `/docs` and `/health`) require API key authentication:

```bash
# Header authentication
curl -H "X-API-Key: YOUR_API_KEY" https://japan-intelligence-api.onrender.com/api/v1/macro

# Query parameter
curl "https://japan-intelligence-api.onrender.com/api/v1/macro?api_key=YOUR_API_KEY"
```

Rate limit: **100 requests/hour** per API key.

## MCP Server (AI Agent Integration)

17 tools available for AI agents via [Model Context Protocol](https://modelcontextprotocol.io/):

| Tool | Description |
|------|-------------|
| `company_intelligence` | Cross-source company analysis (5 sources in 1 call) |
| `market_snapshot` | Complete market overview |
| `financials` | Financial statements (sales, profit, EPS) |
| `policy_summary` | US-Japan monetary policy summary |
| `government_stats` | Japanese government statistics |
| `global_macro` | FRED macro data (rates, CPI, FX) |
| `get_disclosures` | TDnet corporate disclosures |
| `company_profile` | gBizINFO company profile |
| ... and 9 more | |

### Setup

```bash
cd mcp-server && npm install && npm run build
```

### Claude Desktop Configuration

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
| `GEMINI_API_KEY` | Yes | Google Gemini API key (for AI interpretation) |
| `GBIZ_API_TOKEN` | Yes | gBizINFO API token |
| `ESTAT_APP_ID` | Yes | e-Stat application ID |
| `JQUANTS_API_KEY` | Yes | J-Quants v2 API key |
| `FRED_API_KEY` | Yes | FRED API key |
| `JI_API_KEY` | Optional | API authentication key (enables auth when set) |
| `RATE_LIMIT_PER_HOUR` | Optional | Rate limit (default: 100) |

## API Documentation

Interactive documentation available at:
- **Swagger UI**: https://japan-intelligence-api.onrender.com/docs
- **ReDoc**: https://japan-intelligence-api.onrender.com/redoc

## License

Proprietary. All rights reserved.
