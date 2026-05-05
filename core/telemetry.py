from __future__ import annotations

"""
テレメトリ/監査ログモジュール

全APIリクエストをJSONL形式で日別ファイルに記録する。
- 誰が（client_id / tier）
- いつ（timestamp）
- 何を（endpoint / method）
- どうなったか（status_code / latency_ms）
をログに残す。

インメモリバッファに蓄積し、一定件数 or 一定秒数ごとにフラッシュして
ディスクI/O負荷を最小化する。
"""

import json
import os
import time
import threading
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional


class TelemetryLogger:
    """APIリクエストの監査ログを記録・集計するエンジン"""

    def __init__(self, log_dir: str = None, buffer_size: int = 50, flush_interval: int = 30):
        """
        Args:
            log_dir: ログファイル保存先ディレクトリ
            buffer_size: フラッシュまでのバッファサイズ
            flush_interval: 自動フラッシュ間隔（秒）
        """
        if log_dir is None:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            log_dir = os.path.join(base, "data", "telemetry")
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)

        self.buffer_size = buffer_size
        self.flush_interval = flush_interval
        self._buffer: list[dict] = []
        self._lock = threading.Lock()
        self._last_flush = time.time()

        # インメモリ集計（日次リセット）
        self._today = datetime.now().strftime("%Y-%m-%d")
        self._stats = self._empty_stats()

        # 自動フラッシュスレッド
        self._flush_thread = threading.Thread(target=self._auto_flush, daemon=True)
        self._flush_thread.start()

    def _empty_stats(self) -> dict:
        return {
            "total_requests": 0,
            "by_tier": defaultdict(int),
            "by_endpoint": defaultdict(int),
            "by_status": defaultdict(int),
            "by_hour": defaultdict(int),
            "latency_sum": 0.0,
            "latency_count": 0,
            "unique_clients": set(),
            "errors": 0,
        }

    def record(
        self,
        method: str,
        path: str,
        status_code: int,
        latency_ms: float,
        tier: str = "free",
        client_id: str = "anonymous",
        user_agent: Optional[str] = None,
    ):
        """APIリクエストを記録する"""
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")

        # 日次リセット
        if today != self._today:
            self.flush()
            self._today = today
            self._stats = self._empty_stats()

        entry = {
            "ts": now.isoformat(),
            "method": method,
            "path": path,
            "status": status_code,
            "latency_ms": round(latency_ms, 1),
            "tier": tier,
            "client": client_id,
            "ua": (user_agent or "")[:120],
        }

        with self._lock:
            self._buffer.append(entry)

            # インメモリ集計更新
            self._stats["total_requests"] += 1
            self._stats["by_tier"][tier] += 1
            self._stats["by_endpoint"][path] += 1
            self._stats["by_status"][str(status_code)] += 1
            self._stats["by_hour"][now.hour] += 1
            self._stats["latency_sum"] += latency_ms
            self._stats["latency_count"] += 1
            self._stats["unique_clients"].add(client_id)
            if status_code >= 400:
                self._stats["errors"] += 1

            if len(self._buffer) >= self.buffer_size:
                self._flush_locked()

    def flush(self):
        """バッファをディスクにフラッシュ"""
        with self._lock:
            self._flush_locked()

    def _flush_locked(self):
        """ロック取得済み前提でフラッシュ"""
        if not self._buffer:
            return

        today = datetime.now().strftime("%Y-%m-%d")
        filepath = os.path.join(self.log_dir, f"api_log_{today}.jsonl")

        try:
            with open(filepath, "a", encoding="utf-8") as f:
                for entry in self._buffer:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self._buffer.clear()
            self._last_flush = time.time()
        except Exception as e:
            print(f"[Telemetry] Flush error: {e}")

    def _auto_flush(self):
        """定期的にバッファをフラッシュするバックグラウンドスレッド"""
        while True:
            time.sleep(self.flush_interval)
            self.flush()

    def get_stats(self) -> dict:
        """今日の集計統計を返す"""
        with self._lock:
            stats = self._stats
            avg_latency = (
                round(stats["latency_sum"] / stats["latency_count"], 1)
                if stats["latency_count"] > 0
                else 0
            )

            # top endpoints
            top_endpoints = sorted(
                stats["by_endpoint"].items(),
                key=lambda x: x[1],
                reverse=True,
            )[:15]

            # hourly distribution
            hourly = {str(h): stats["by_hour"].get(h, 0) for h in range(24)}

            return {
                "date": self._today,
                "total_requests": stats["total_requests"],
                "unique_clients": len(stats["unique_clients"]),
                "by_tier": dict(stats["by_tier"]),
                "by_status": dict(stats["by_status"]),
                "top_endpoints": [{"path": p, "count": c} for p, c in top_endpoints],
                "hourly_distribution": hourly,
                "avg_latency_ms": avg_latency,
                "error_count": stats["errors"],
                "error_rate": round(
                    stats["errors"] / max(stats["total_requests"], 1) * 100, 2
                ),
            }

    def get_historical(self, days: int = 7) -> list[dict]:
        """過去N日分のログファイルサマリーを返す"""
        result = []
        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            filepath = os.path.join(self.log_dir, f"api_log_{date}.jsonl")

            if not os.path.exists(filepath):
                result.append({"date": date, "requests": 0, "file_exists": False})
                continue

            try:
                count = 0
                tiers = defaultdict(int)
                errors = 0
                with open(filepath, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            count += 1
                            try:
                                entry = json.loads(line)
                                tiers[entry.get("tier", "unknown")] += 1
                                if entry.get("status", 200) >= 400:
                                    errors += 1
                            except json.JSONDecodeError:
                                pass

                result.append({
                    "date": date,
                    "requests": count,
                    "by_tier": dict(tiers),
                    "errors": errors,
                    "file_exists": True,
                })
            except Exception as e:
                result.append({"date": date, "requests": 0, "error": str(e)})

        return result
