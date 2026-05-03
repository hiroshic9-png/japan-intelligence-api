"""
Japan Intelligence — 日本銀行 統計データソース

日本銀行 時系列統計データ検索サイト API を利用して
短観（全国企業短期経済観測調査）等の日銀統計を構造化取得する。

API仕様:
  Base: https://www.stat-search.boj.or.jp/api/v1
  認証: 不要（公開API）
  db=CO: 短観データベース
"""
from __future__ import annotations
import requests
from datetime import datetime


# 短観 主要系列コード
BOJ_TANKAN_SERIES = {
    "tankan_large_manufacturing": {
        "code": "TK99F1000601GCQ01000",
        "label": "短観 大企業 製造業 業況判断DI",
        "description": "日本経済の「体温計」。プラスは好況、マイナスは不況を示す。",
    },
    "tankan_large_nonmanufacturing": {
        "code": "TK99F2000601GCQ01000",
        "label": "短観 大企業 非製造業 業況判断DI",
        "description": "サービス・金融等。国内消費の強さを反映。",
    },
    "tankan_small_manufacturing": {
        "code": "TK99F1000601GCQ02000",
        "label": "短観 中小企業 製造業 業況判断DI",
        "description": "中小製造業の景況感。大企業との乖離が重要。",
    },
    "tankan_small_nonmanufacturing": {
        "code": "TK99F2000601GCQ02000",
        "label": "短観 中小企業 非製造業 業況判断DI",
        "description": "街角の景況感に近い。地方経済の実態を反映。",
    },
    "tankan_all_industry": {
        "code": "TK99F0000601GCQ00000",
        "label": "短観 全規模 全産業 業況判断DI",
        "description": "全企業を網羅した総合的な景況指標。",
    },
}


class BOJSource:
    """日本銀行 時系列統計データ APIクライアント"""

    API_BASE = "https://www.stat-search.boj.or.jp/api/v1"

    def __init__(self):
        self._cache = {}
        self._cache_ttl = 21600  # 6時間（短観は四半期更新）

    def get_available_series(self) -> list:
        """利用可能な短観系列の一覧を返す。"""
        return [
            {"id": key, "label": val["label"], "description": val["description"]}
            for key, val in BOJ_TANKAN_SERIES.items()
        ]

    def get_tankan(self, series_id: str = None, limit: int = 20) -> dict:
        """
        短観データを取得する。

        Args:
            series_id: 系列ID（指定しない場合は主要4系列を全て取得）
            limit: 取得期間数
        """
        if series_id and series_id in BOJ_TANKAN_SERIES:
            return self._fetch_single(series_id, limit)

        # 全系列を一括取得
        cache_key = f"tankan:all:{limit}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        result = {}
        for sid in ["tankan_large_manufacturing", "tankan_large_nonmanufacturing",
                     "tankan_small_manufacturing", "tankan_small_nonmanufacturing"]:
            data = self._fetch_single(sid, limit)
            result[sid] = data

        summary = {
            "survey": "全国企業短期経済観測調査（短観）",
            "publisher": "日本銀行",
            "frequency": "四半期（3月・6月・9月・12月）",
            "series": result,
            "source": "boj",
        }

        self._set_cache(cache_key, summary)
        return summary

    def get_tankan_summary(self) -> dict:
        """
        短観サマリー — エージェント向け1コールダイジェスト。
        大企業・中小企業の製造業/非製造業DIの最新値と前期比較。
        """
        cache_key = "tankan:summary"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        summary = {"items": [], "source": "boj"}

        for sid, info in BOJ_TANKAN_SERIES.items():
            if "capex" in sid:
                continue  # サマリーからは除外
            data = self._fetch_single(sid, 4)
            values = data.get("data", [])
            latest = values[0] if values else None
            previous = values[1] if len(values) > 1 else None

            item = {
                "id": sid,
                "label": info["label"],
                "description": info["description"],
            }
            if latest:
                item["latest_value"] = latest.get("value"),
                item["latest_period"] = latest.get("period", ""),
            if previous:
                item["previous_value"] = previous.get("value"),
                change = None
                try:
                    lv = float(latest.get("value", 0))
                    pv = float(previous.get("value", 0))
                    change = lv - pv
                except (ValueError, TypeError):
                    pass
                item["change"] = change
                if change is not None:
                    item["trend"] = "improving" if change > 0 else ("declining" if change < 0 else "flat")

            summary["items"].append(item)

        self._set_cache(cache_key, summary)
        return summary

    def _fetch_single(self, series_id: str, limit: int = 20) -> dict:
        """単一系列のデータ取得。"""
        info = BOJ_TANKAN_SERIES.get(series_id, {})
        cache_key = f"tankan:{series_id}:{limit}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        code = info.get("code", "")
        if not code:
            return {"error": f"Unknown series: {series_id}"}

        try:
            resp = requests.get(
                f"{self.API_BASE}/getDataCode",
                params={
                    "format": "json",
                    "lang": "jp",
                    "db": "CO",
                    "code": code,
                },
                timeout=15,
            )

            if resp.status_code != 200:
                print(f"[BOJ] API error {resp.status_code}")
                return {"series": series_id, "label": info.get("label", ""), "data": []}

            raw = resp.json()

            if raw.get("STATUS") != 200:
                print(f"[BOJ] API status: {raw.get('MESSAGE', 'Unknown error')}")
                return {"series": series_id, "label": info.get("label", ""), "data": []}

            # RESULTSET形式をパース
            result_set = raw.get("RESULTSET", [])
            if not result_set:
                return {"series": series_id, "label": info.get("label", ""), "data": []}

            entry = result_set[0]
            values_data = entry.get("VALUES", {})
            dates = values_data.get("SURVEY_DATES", [])
            values = values_data.get("VALUES", [])

            # 最新limit件を逆順で取得
            formatted = []
            pairs = list(zip(dates, values))
            for date, value in reversed(pairs[-limit:]):
                # dateは YYYYQQ形式（例: 202601 = 2026年Q1）
                year = str(date)[:4]
                quarter = str(date)[4:]
                period = f"{year}Q{quarter}" if len(str(date)) == 6 else str(date)
                formatted.append({
                    "period": period,
                    "value": value,
                })

            result = {
                "series": series_id,
                "label": info.get("label", ""),
                "description": info.get("description", ""),
                "unit": entry.get("UNIT_J", ""),
                "frequency": entry.get("FREQUENCY", ""),
                "last_update": entry.get("LAST_UPDATE", ""),
                "data": formatted,
                "count": len(formatted),
                "source": "boj",
            }

            self._set_cache(cache_key, result)
            return result

        except Exception as e:
            print(f"[BOJ] Fetch error for {series_id}: {e}")
            return {"series": series_id, "label": info.get("label", ""), "data": [], "error": str(e)}

    def _get_cache(self, key: str):
        if key in self._cache:
            entry = self._cache[key]
            elapsed = (datetime.now() - entry["time"]).total_seconds()
            if elapsed < self._cache_ttl:
                return entry["data"]
            del self._cache[key]
        return None

    def _set_cache(self, key: str, data):
        self._cache[key] = {"data": data, "time": datetime.now()}
