"""
Japan Intelligence — 地震データソース（USGS Earthquake API）

APIキー不要。日本周辺の地震をリアルタイム検出。
ソース: USGS (https://earthquake.usgs.gov)
"""
import requests
from datetime import datetime, timedelta

JAPAN_BBOX = {
    "minlatitude": 24.0, "maxlatitude": 46.0,
    "minlongitude": 122.0, "maxlongitude": 150.0,
}
USGS_BASE = "https://earthquake.usgs.gov/fdsnws/event/1/query"
_quake_cache: dict = {"data": None, "fetched_at": None}
CACHE_TTL = 300


class EarthquakeSource:
    def get_recent_earthquakes(self, days: int = 7, min_magnitude: float = 3.0) -> dict:
        now = datetime.utcnow()
        if (_quake_cache["data"] and _quake_cache["fetched_at"]
                and (now - _quake_cache["fetched_at"]).seconds < CACHE_TTL):
            cached = _quake_cache["data"]
            filtered = [q for q in cached.get("earthquakes", [])
                        if q.get("magnitude", 0) >= min_magnitude]
            return {**cached, "earthquakes": filtered[:50],
                    "filter": {"days": days, "min_magnitude": min_magnitude}, "cached": True}

        try:
            params = {"format": "geojson",
                      "starttime": (now - timedelta(days=days)).strftime("%Y-%m-%d"),
                      "endtime": now.strftime("%Y-%m-%d"),
                      "minmagnitude": min_magnitude, "orderby": "time", "limit": 100,
                      **JAPAN_BBOX}
            resp = requests.get(USGS_BASE, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            features = data.get("features", [])
            earthquakes = []
            mag_dist = {"M3-4": 0, "M4-5": 0, "M5-6": 0, "M6-7": 0, "M7+": 0}

            for f in features:
                props = f.get("properties", {})
                geom = f.get("geometry", {}).get("coordinates", [0, 0, 0])
                mag = props.get("mag", 0) or 0
                if mag >= 7: mag_dist["M7+"] += 1
                elif mag >= 6: mag_dist["M6-7"] += 1
                elif mag >= 5: mag_dist["M5-6"] += 1
                elif mag >= 4: mag_dist["M4-5"] += 1
                else: mag_dist["M3-4"] += 1
                time_ms = props.get("time", 0)
                event_time = datetime.utcfromtimestamp(time_ms / 1000).isoformat() + "Z" if time_ms else None
                tsunami = bool(props.get("tsunami", 0))
                impact = self._assess_impact(mag, tsunami)
                earthquakes.append({
                    "magnitude": mag, "place": props.get("place", "Unknown"),
                    "time": event_time, "depth_km": geom[2] if len(geom) > 2 else None,
                    "latitude": geom[1] if len(geom) > 1 else None,
                    "longitude": geom[0], "tsunami_warning": tsunami,
                    "significance": props.get("sig", 0),
                    "business_impact": impact, "usgs_url": props.get("url", ""),
                })

            max_q = max(earthquakes, key=lambda x: x["magnitude"]) if earthquakes else None
            risk = self._assess_risk(earthquakes)
            result = {
                "period": {"start": params["starttime"], "end": params["endtime"], "days": days},
                "summary": {
                    "total_events": len(earthquakes), "magnitude_distribution": mag_dist,
                    "max_magnitude": max_q["magnitude"] if max_q else 0,
                    "max_event": {"magnitude": max_q["magnitude"], "place": max_q["place"],
                                  "time": max_q["time"]} if max_q else None,
                    "tsunami_warnings": sum(1 for q in earthquakes if q["tsunami_warning"]),
                    "seismic_risk_level": risk,
                },
                "earthquakes": earthquakes[:50],
                "filter": {"days": days, "min_magnitude": min_magnitude},
                "source": "USGS Earthquake Catalog", "cached": False,
                "fetched_at": now.isoformat() + "Z",
            }
            _quake_cache["data"] = result
            _quake_cache["fetched_at"] = now
            return result
        except Exception as e:
            print(f"[Earthquake] Error: {e}")
            if _quake_cache["data"]:
                return {**_quake_cache["data"], "cached": True, "error": str(e)}
            return {"earthquakes": [], "summary": {"total_events": 0, "error": str(e)}}

    def _assess_impact(self, mag: float, tsunami: bool) -> dict:
        if mag >= 7.0 or tsunami:
            return {"severity": "critical",
                    "description_jp": "大地震 — インフラ被害・サプライチェーン寸断リスク",
                    "affected_sectors": ["insurance", "construction", "logistics", "utilities"]}
        elif mag >= 6.0:
            return {"severity": "high",
                    "description_jp": "強い地震 — 局所的被害、交通影響",
                    "affected_sectors": ["insurance", "construction", "logistics"]}
        elif mag >= 5.0:
            return {"severity": "moderate",
                    "description_jp": "中規模地震 — 軽微な影響",
                    "affected_sectors": ["insurance", "construction"]}
        elif mag >= 4.0:
            return {"severity": "low", "description_jp": "軽い地震 — 重大影響なし"}
        return {"severity": "negligible", "description_jp": "微小地震"}

    def _assess_risk(self, earthquakes: list) -> str:
        if not earthquakes:
            return "low"
        max_m = max(q["magnitude"] for q in earthquakes)
        c5 = sum(1 for q in earthquakes if q["magnitude"] >= 5.0)
        if max_m >= 7.0 or c5 >= 3: return "critical"
        elif max_m >= 6.0 or c5 >= 1: return "elevated"
        elif max_m >= 4.0: return "moderate"
        return "low"
