"""
Japan Intelligence — 設定ファイル

全設定を1箇所に集約。環境変数で上書き可能。
"""
import os

# === API設定 ===
API_VERSION = "v1"
API_TITLE = "Japan Intelligence API"
API_DESCRIPTION = "Structured, real-time Japanese public data for AI agents"

# === データソース設定 ===
TDNET_CONFIG = {
    'api_base': 'https://webapi.yanoshin.jp/webapi/tdnet/list',
    'default_days': 3,
    'cache_ttl_seconds': 1800,  # 30分
}

EDINET_CONFIG = {
    'api_base': 'https://api.edinet-fsa.go.jp/api/v2',
    'api_key': os.getenv('EDINET_API_KEY', ''),
    'default_days': 7,
    'cache_ttl_seconds': 3600 * 6,  # 6時間
}

MACRO_CONFIG = {
    'thresholds': {
        'oil_surge_pct': 5.0,
        'oil_crash_pct': -5.0,
        'gold_surge_pct': 3.0,
        'yen_move_pct': 1.5,
        'vix_spike_pct': 15.0,
    },
}

# === LLM設定 ===
LLM_CONFIG = {
    'model': 'gemini-2.5-flash',
    'api_key': os.getenv('GEMINI_API_KEY', ''),
}

# === レート制限 ===
RATE_LIMIT = {
    'free_daily': 100,
    'developer_monthly': 10000,
    'pro_monthly': 100000,
}
