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

# === gBizINFO設定 ===
GBIZ_CONFIG = {
    'api_base': 'https://info.gbiz.go.jp/hojin/v1',
    'api_token': os.getenv('GBIZ_API_TOKEN', ''),
    'cache_ttl_seconds': 3600 * 24,  # 24時間（企業情報は頻繁に変わらない）
}

# === e-Stat設定 ===
ESTAT_CONFIG = {
    'api_base': 'https://api.e-stat.go.jp/rest/3.0/app/json',
    'app_id': os.getenv('ESTAT_APP_ID', ''),
    'cache_ttl_seconds': 3600 * 6,  # 6時間（政府統計は日次〜月次更新）
}

# === J-Quants設定（V2 APIキー認証）===
JQUANTS_CONFIG = {
    'api_base': 'https://api.jquants.com/v2',
    'api_key': os.getenv('JQUANTS_API_KEY', ''),
    'cache_ttl_seconds': 3600 * 12,  # 12時間（銘柄マスタ・決算予定）
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

# === 銘柄コード → 法人番号マッピング ===
# gBizINFOは法人番号ベース。上場銘柄コードとの橋渡し。
TICKER_TO_CORPORATE_NUMBER = {
    '7203.T': '1180301018771',  # トヨタ自動車
    '6758.T': '7010401067252',  # ソニーグループ
    '8306.T': '6010001008846',  # 三菱UFJ
    '9984.T': '7010401060001',  # ソフトバンクグループ
    '9432.T': '2010001067722',  # NTT
    '6861.T': '2130001005498',  # キーエンス
    '6501.T': '7010001008844',  # 日立製作所
    '8035.T': '9010001034215',  # 東京エレクトロン
    '4063.T': '4010001034746',  # 信越化学工業
    '7267.T': '5010401041564',  # ホンダ
    '7974.T': '2130001013780',  # 任天堂
    '6902.T': '2180301015612',  # デンソー
    '8058.T': '4010001008827',  # 三菱商事
    '8001.T': '3010001008749',  # 伊藤忠商事
    '9433.T': '5010001034726',  # KDDI
    '9983.T': '1140001056481',  # ファーストリテイリング
    '4568.T': '1010001008725',  # 第一三共
    '4519.T': '2010001034748',  # 中外製薬
    '4502.T': '2120001077820',  # 武田薬品
    '7011.T': '8010001008767',  # 三菱重工業
    '6920.T': '1010001008733',  # レーザーテック
    '6857.T': '5010401061098',  # アドバンテスト
    '6981.T': '3130001013260',  # 村田製作所
    '8316.T': '8010001081660',  # 三井住友FG
    '6367.T': '1120001077461',  # ダイキン工業
    '4911.T': '5010001034734',  # 資生堂
    '6594.T': '4130001005473',  # ニデック（日本電産）
    '6273.T': '7010001034214',  # SMC
    '4385.T': '6010001168685',  # メルカリ
    '2914.T': '2010001008726',  # JT
}
