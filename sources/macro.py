"""
Japan Intelligence — マクロ指標データソース

コモディティ・為替・VIX等のマクロ指標を取得し、
異常変動イベントと恩恵/逆風銘柄をマッピングする。

ASTRAのmacro_catalyst.pyから転用・汎用化。
"""
import datetime
import pytz
import yfinance as yf
from core.config import MACRO_CONFIG

# マクロ指標 → 恩恵/逆風銘柄マッピング
MACRO_BENEFICIARIES = {
    'oil_surge': {
        'label': '原油急騰', 'label_en': 'Crude Oil Surge',
        'description': '原油価格の急上昇。石油開発・資源株に恩恵',
        'positive': ['1605.T', '1662.T', '5020.T', '5019.T', '5021.T', '5017.T',
                     '8031.T', '8058.T', '8002.T', '8053.T'],
        'negative': ['9020.T', '9202.T', '9201.T', '9501.T'],
    },
    'oil_crash': {
        'label': '原油急落', 'label_en': 'Crude Oil Crash',
        'description': '原油価格の急落。運輸・化学にコスト減恩恵',
        'positive': ['9202.T', '9201.T', '9020.T', '9022.T', '4063.T'],
        'negative': ['1605.T', '1662.T', '5020.T', '5019.T'],
    },
    'gold_surge': {
        'label': '金急騰', 'label_en': 'Gold Surge',
        'description': '金価格の急上昇。金鉱株・貴金属関連に恩恵',
        'positive': ['5711.T', '5706.T', '5713.T', '5714.T', '7456.T'],
        'negative': [],
    },
    'yen_weaken': {
        'label': '円安加速', 'label_en': 'Yen Weakening',
        'description': 'ドル円急上昇（円安）。輸出・インバウンドに恩恵',
        'positive': ['7203.T', '7267.T', '6758.T', '6954.T', '4661.T'],
        'negative': ['2914.T', '2802.T'],
    },
    'yen_strengthen': {
        'label': '円高加速', 'label_en': 'Yen Strengthening',
        'description': 'ドル円急落（円高）。輸入関連に恩恵',
        'positive': ['9983.T', '3382.T', '2914.T'],
        'negative': ['7203.T', '7267.T', '6758.T'],
    },
    'vix_spike': {
        'label': 'VIX急騰', 'label_en': 'VIX Spike',
        'description': 'VIX恐怖指数の急上昇。ディフェンシブに資金流入',
        'positive': ['7011.T', '7012.T', '7013.T', '4502.T', '9432.T'],
        'negative': [],
    },
}

# 取得対象指標
MACRO_TICKERS = {
    'CL=F': 'crude_oil', 'GC=F': 'gold',
    'JPY=X': 'usdjpy', '^VIX': 'vix',
    '^N225': 'nikkei225', '^GSPC': 'sp500',
}
MACRO_LABELS = {
    'crude_oil': '原油WTI', 'gold': '金先物',
    'usdjpy': 'ドル円', 'vix': 'VIX恐怖指数',
    'nikkei225': '日経225', 'sp500': 'S&P500',
}


class MacroSource:
    """マクロ指標の取得と異常変動検知"""

    def __init__(self):
        self.tz = pytz.timezone('Asia/Tokyo')
        self._cache = None
        self._cache_date = None
        self.thresholds = MACRO_CONFIG['thresholds']

    def get_indicators(self) -> list[dict]:
        """全マクロ指標の最新値を返す"""
        data = self._fetch_market_data()
        indicators = []
        for key, label in MACRO_LABELS.items():
            if key in data:
                indicators.append({
                    'indicator': key,
                    'label': label,
                    'price': data[key]['price'],
                    'change_pct': data[key]['change'],
                    'source': 'yfinance',
                })
        return indicators

    def detect_events(self) -> list[dict]:
        """マクロ異常変動イベントを検出する"""
        today = datetime.datetime.now(self.tz).strftime('%Y-%m-%d')
        if self._cache and self._cache_date == today:
            return self._cache

        data = self._fetch_market_data()
        events = []

        oil = data.get('crude_oil', {})
        oil_chg = oil.get('change', 0)
        if oil_chg >= self.thresholds['oil_surge_pct']:
            events.append(self._build_event('oil_surge', oil_chg, oil.get('price', 0)))
        elif oil_chg <= self.thresholds['oil_crash_pct']:
            events.append(self._build_event('oil_crash', oil_chg, oil.get('price', 0)))

        gold = data.get('gold', {})
        gold_chg = gold.get('change', 0)
        if gold_chg >= self.thresholds['gold_surge_pct']:
            events.append(self._build_event('gold_surge', gold_chg, gold.get('price', 0)))

        yen = data.get('usdjpy', {})
        yen_chg = yen.get('change', 0)
        if yen_chg >= self.thresholds['yen_move_pct']:
            events.append(self._build_event('yen_weaken', yen_chg, yen.get('price', 0)))
        elif yen_chg <= -self.thresholds['yen_move_pct']:
            events.append(self._build_event('yen_strengthen', yen_chg, yen.get('price', 0)))

        vix = data.get('vix', {})
        vix_chg = vix.get('change', 0)
        if vix_chg >= self.thresholds['vix_spike_pct']:
            events.append(self._build_event('vix_spike', vix_chg, vix.get('price', 0)))

        self._cache = events
        self._cache_date = today
        return events

    def _build_event(self, event_key: str, change_pct: float, price: float) -> dict:
        config = MACRO_BENEFICIARIES.get(event_key, {})
        return {
            'event': event_key,
            'label': config.get('label', event_key),
            'label_en': config.get('label_en', event_key),
            'change_pct': round(change_pct, 2),
            'price': round(price, 2),
            'description': config.get('description', ''),
            'positive_tickers': config.get('positive', []),
            'negative_tickers': config.get('negative', []),
            'source': 'macro_detection',
        }

    def _fetch_market_data(self) -> dict:
        data = {}
        for yf_ticker, key in MACRO_TICKERS.items():
            try:
                df = yf.download(yf_ticker, period="5d", progress=False)
                if not df.empty:
                    close = df['Close'].iloc[-1]
                    prev = df['Close'].iloc[-2] if len(df) >= 2 else close
                    change = (close / prev - 1) * 100
                    if hasattr(close, 'iloc'):
                        close = float(close.iloc[0])
                        change = float(change.iloc[0])
                    data[key] = {
                        'price': round(float(close), 2),
                        'change': round(float(change), 2),
                    }
            except Exception:
                continue
        return data
