"""
Japan Intelligence — JPX 投資部門別売買動向データソース

JPX（日本取引所グループ）の投資部門別売買動向を取得する。
外国人投資家・個人・信託銀行等の週次売買データは
市場方向の最強シグナルの一つ。

データ元: https://www.jpx.co.jp/markets/statistics-equities/investor-type/
更新: 毎週第4営業日（木曜日 15:30頃）
形式: Excel (.xls)
"""
from __future__ import annotations
import io
import re
import requests
from datetime import datetime, timedelta


class JPXInvestorFlowSource:
    """JPX 投資部門別売買動向クライアント"""

    BASE_URL = "https://www.jpx.co.jp/markets/statistics-equities/investor-type"

    def __init__(self):
        self._cache = None
        self._cache_time = None
        self._cache_ttl = 43200  # 12時間

    def get_investor_flows(self) -> dict:
        """
        最新の投資部門別売買動向を取得する。

        Returns:
            外国人・個人・信託・事業法人等の売買差額（金額ベース）
        """
        if self._is_cache_valid():
            return self._cache

        try:
            data = self._fetch_latest()
            if data:
                self._cache = data
                self._cache_time = datetime.now()
            return data or self._get_fallback_data()
        except Exception as e:
            print(f"[JPX] Investor flow fetch error: {e}")
            return self._get_fallback_data()

    def _fetch_latest(self) -> dict:
        """JPXサイトから最新の金額ベースデータを取得・構造化。"""
        try:
            # ページからExcelリンクを検索
            page_url = f"{self.BASE_URL}/index.html"
            resp = requests.get(page_url, timeout=15)
            if resp.status_code != 200:
                print(f"[JPX] Page fetch error: {resp.status_code}")
                return None

            html = resp.text
            # 金額ベース(val)のExcelファイルURLを検索
            xls_pattern = r'(/markets/statistics-equities/investor-type/[^"]*stock_val_1[^"]*\.xls[x]?)'
            matches = re.findall(xls_pattern, html)

            if not matches:
                print("[JPX] No value Excel file found")
                return None

            # 最新ファイル（最初のマッチ）をダウンロード
            xls_url = f"https://www.jpx.co.jp{matches[0]}"
            xls_resp = requests.get(xls_url, timeout=30)

            if xls_resp.status_code != 200:
                print(f"[JPX] Excel download error: {xls_resp.status_code}")
                return None

            return self._parse_excel(xls_resp.content, xls_url)

        except Exception as e:
            print(f"[JPX] Fetch error: {e}")
            return None

    def _parse_excel(self, content: bytes, source_url: str) -> dict:
        """JPX Excelファイルを構造化パース。"""
        try:
            import pandas as pd
            df = pd.read_excel(io.BytesIO(content), engine='xlrd', header=None)

            # 期間情報の抽出（行3: "2026年4月第4週 2026/4 week4  ( 4/20 - 4/24 )"）
            period_str = ""
            for i in range(min(5, len(df))):
                cell = str(df.iloc[i, 0]) if not pd.isna(df.iloc[i, 0]) else ""
                if "週" in cell or "week" in cell.lower():
                    period_str = cell
                    break

            # 総売買代金（行8）
            total_value = self._parse_number(df, 8, 0)

            # 委託内訳を抽出（行22以降）
            flows = {}
            current_week_col = None
            prev_week_col = None

            # 列インデックスを特定 — 最新週は右側のデータ列
            # パターン: [ラベル, 売り/買い, Sales/Purchases, 前週金額, 前週比率, 前週差引き, 今週金額, 今週比率, 今週差引き]
            # 実際のデータ列位置を動的に検出
            categories = {
                "海外投資家": "foreigners",
                "個　人": "individuals",
                "投資信託": "investment_trusts",
                "信託銀行": "trust_banks",
                "事業法人": "corporations",
                "生保・損保": "insurance",
                "都銀・地銀等": "banks",
                "その他法人": "other_institutions",
                "証券会社": "securities_cos",
            }

            # JPX Excel列構造:
            # col 0-2: ラベル（カテゴリ名, 売り/買い, Sales/Purchases）
            # col 3: 空
            # col 4: 前週の金額
            # col 5: 前週の比率
            # col 6: 前週の差引き
            # col 7: 空
            # col 8: 最新週の金額
            # col 9: 最新週の比率
            # col 10: 最新週の差引き
            LATEST_VALUE_COL = 8
            LATEST_BALANCE_COL = 10

            for i in range(len(df)):
                cell0 = str(df.iloc[i, 0]) if not pd.isna(df.iloc[i, 0]) else ""

                for jp_name, en_key in categories.items():
                    # 既にマッチ済みのカテゴリはスキップ（複数市場セクション対策）
                    if en_key in flows:
                        continue
                    if jp_name in cell0:
                        # この行は「売り」行、次の行が「買い」行
                        sells = self._parse_value(df, i, LATEST_VALUE_COL)
                        buys = self._parse_value(df, i + 1, LATEST_VALUE_COL)
                        # 差引きは買い行のcol 10
                        net = self._parse_value(df, i + 1, LATEST_BALANCE_COL)
                        
                        # 差引きが取れない場合は計算
                        if net is None and sells is not None and buys is not None:
                            net = buys - sells

                        flows[en_key] = {
                            "name_jp": jp_name.replace("　", ""),
                            "sells": sells,
                            "buys": buys,
                            "net": net,
                            "signal": self._interpret_flow(en_key, net),
                        }
                        break

            result = {
                "period": period_str,
                "total_trading_value": total_value,
                "unit": "千円 (1,000 JPY)",
                "flows": flows,
                "highlights": self._generate_highlights(flows),
                "source": "jpx",
                "source_url": source_url,
            }

            return result

        except Exception as e:
            print(f"[JPX] Excel parse error: {e}")
            return None

    def _parse_number(self, df, row: int, col: int):
        """セルから数値を取得（カンマ区切り対応）。"""
        try:
            import pandas as pd
            val = df.iloc[row, col]
            if pd.isna(val):
                return None
            if isinstance(val, (int, float)):
                return val
            s = str(val).replace(",", "").strip()
            return int(s) if s.isdigit() else float(s)
        except Exception:
            return None

    def _parse_value(self, df, row: int, col: int):
        """指定行・列からカンマ区切り金額を取得。"""
        import pandas as pd
        try:
            if row >= len(df) or col >= df.shape[1]:
                return None
            val = df.iloc[row, col]
            if pd.isna(val):
                return None
            if isinstance(val, (int, float)):
                return int(val)
            s = str(val).replace(",", "").replace(" ", "").strip()
            if s.lstrip("-").isdigit():
                return int(s)
            try:
                return int(float(s))
            except (ValueError, TypeError):
                return None
        except Exception:
            return None

    def _interpret_flow(self, category: str, net) -> str:
        """フローの意味を解釈する。"""
        if net is None:
            return "unknown"
        
        interpretations = {
            "foreigners": ("bullish_signal", "bearish_signal"),
            "individuals": ("contrarian_bearish", "contrarian_bullish"),
            "trust_banks": ("pension_buying", "pension_selling"),
            "corporations": ("buyback_support", "corporate_selling"),
            "investment_trusts": ("retail_bullish", "retail_bearish"),
        }
        
        if category in interpretations:
            bull, bear = interpretations[category]
            return bull if net > 0 else bear
        return "net_buy" if net > 0 else "net_sell"

    def _generate_highlights(self, flows: dict) -> list:
        """主要な洞察を生成。"""
        highlights = []
        
        fg = flows.get("foreigners", {})
        if fg.get("net") is not None:
            net_b = fg["net"] / 1_000_000  # 百万円
            direction = "買い越し" if fg["net"] > 0 else "売り越し"
            highlights.append(f"外国人: {abs(net_b):,.0f}百万円の{direction}")

        ig = flows.get("individuals", {})
        if ig.get("net") is not None:
            net_b = ig["net"] / 1_000_000
            direction = "買い越し" if ig["net"] > 0 else "売り越し"
            highlights.append(f"個人: {abs(net_b):,.0f}百万円の{direction}")

        tb = flows.get("trust_banks", {})
        if tb.get("net") is not None:
            net_b = tb["net"] / 1_000_000
            direction = "買い越し" if tb["net"] > 0 else "売り越し"
            highlights.append(f"信託銀行(年金代理): {abs(net_b):,.0f}百万円の{direction}")

        return highlights

    def _get_fallback_data(self) -> dict:
        """Excel取得失敗時のフォールバック。"""
        return {
            "description": "投資部門別 株式売買状況（東証）",
            "frequency": "weekly (updated Thursday 15:30 JST)",
            "data_available": False,
            "manual_url": f"{self.BASE_URL}/index.html",
            "explanation": (
                "Foreign investor flows are the single most important signal "
                "for Japanese equity markets. Weekly data shows net buying/selling "
                "by: foreigners, individuals, trust banks (GPIF proxy), "
                "corporations, and proprietary traders."
            ),
            "key_categories": [
                {"name": "外国人（海外投資家）", "significance": "Market direction leader — 70% of TSE trading volume"},
                {"name": "個人", "significance": "Contrarian signal — typically sells into rallies"},
                {"name": "信託銀行", "significance": "GPIF and pension fund proxy"},
                {"name": "事業法人", "significance": "Corporate buybacks — structural support"},
                {"name": "投資信託", "significance": "Retail fund flows — sentiment indicator"},
            ],
            "source": "jpx",
        }

    def _is_cache_valid(self) -> bool:
        if not self._cache_time:
            return False
        elapsed = (datetime.now() - self._cache_time).total_seconds()
        return elapsed < self._cache_ttl
