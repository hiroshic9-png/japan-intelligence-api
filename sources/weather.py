"""
Japan Intelligence — 天気データソース（Open-Meteo API）

APIキー不要・無料。JMA（気象庁）モデルベースの日本主要都市天気予報。
エージェントが日本のビジネス環境を包括的に理解するための非金融コンテキスト。

更新頻度: 1時間キャッシュ
ソース: Open-Meteo (https://open-meteo.com) — JMA GSM/MSM モデル
"""
import requests
from datetime import datetime

# 日本主要都市の座標
JAPAN_CITIES = {
    "tokyo": {"lat": 35.6762, "lon": 139.6503, "name_jp": "東京", "name_en": "Tokyo"},
    "osaka": {"lat": 34.6937, "lon": 135.5023, "name_jp": "大阪", "name_en": "Osaka"},
    "nagoya": {"lat": 35.1815, "lon": 136.9066, "name_jp": "名古屋", "name_en": "Nagoya"},
    "fukuoka": {"lat": 33.5904, "lon": 130.4017, "name_jp": "福岡", "name_en": "Fukuoka"},
    "sapporo": {"lat": 43.0618, "lon": 141.3545, "name_jp": "札幌", "name_en": "Sapporo"},
    "sendai": {"lat": 38.2682, "lon": 140.8694, "name_jp": "仙台", "name_en": "Sendai"},
    "hiroshima": {"lat": 34.3853, "lon": 132.4553, "name_jp": "広島", "name_en": "Hiroshima"},
    "naha": {"lat": 26.2124, "lon": 127.6809, "name_jp": "那覇", "name_en": "Naha"},
}

OPEN_METEO_BASE = "https://api.open-meteo.com/v1/forecast"

# キャッシュ
_weather_cache: dict = {"data": None, "fetched_at": None}
CACHE_TTL = 3600  # 1時間


class WeatherSource:
    """Open-Meteo APIを使用した日本主要都市の天気予報データソース"""

    def get_japan_weather(self, cities: list[str] = None) -> dict:
        """
        日本主要都市の天気予報を取得する。

        Args:
            cities: 都市キーのリスト（指定なしで全都市）

        Returns:
            都市別天気データの辞書
        """
        now = datetime.now()

        # キャッシュチェック
        if (_weather_cache["data"] is not None
                and _weather_cache["fetched_at"]
                and (now - _weather_cache["fetched_at"]).seconds < CACHE_TTL):
            data = _weather_cache["data"]
            if cities:
                data = {k: v for k, v in data.items() if k in cities}
            return {
                "cities": data,
                "cached": True,
                "fetched_at": _weather_cache["fetched_at"].isoformat(),
                "source": "open-meteo.com (JMA model)",
            }

        # 全都市を一括取得
        all_weather = {}
        target_cities = cities if cities else list(JAPAN_CITIES.keys())

        for city_key in target_cities:
            if city_key not in JAPAN_CITIES:
                continue
            city = JAPAN_CITIES[city_key]
            try:
                weather = self._fetch_city_weather(city)
                all_weather[city_key] = weather
            except Exception as e:
                print(f"[Weather] Error fetching {city_key}: {e}")
                all_weather[city_key] = {"error": str(e)}

        # キャッシュ更新
        _weather_cache["data"] = all_weather
        _weather_cache["fetched_at"] = now

        result_data = all_weather
        if cities:
            result_data = {k: v for k, v in all_weather.items() if k in cities}

        return {
            "cities": result_data,
            "cached": False,
            "fetched_at": now.isoformat(),
            "source": "open-meteo.com (JMA model)",
            "note": "Weather data based on JMA (Japan Meteorological Agency) models. "
                    "Temperature in °C, precipitation in mm, wind in km/h.",
        }

    def _fetch_city_weather(self, city: dict) -> dict:
        """個別都市の天気を取得"""
        params = {
            "latitude": city["lat"],
            "longitude": city["lon"],
            "hourly": "temperature_2m,precipitation,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code",
            "timezone": "Asia/Tokyo",
            "forecast_days": 3,
        }

        resp = requests.get(OPEN_METEO_BASE, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        # 現在の天気（直近の時間帯データ）
        hourly = data.get("hourly", {})
        current_hour = datetime.now().hour
        current_idx = min(current_hour, len(hourly.get("temperature_2m", [])) - 1)

        current = {}
        if hourly.get("temperature_2m"):
            current = {
                "temperature_c": hourly["temperature_2m"][current_idx],
                "precipitation_mm": hourly.get("precipitation", [0])[current_idx],
                "weather_code": hourly.get("weather_code", [0])[current_idx],
                "weather_description": self._weather_code_to_text(
                    hourly.get("weather_code", [0])[current_idx]
                ),
                "wind_speed_kmh": hourly.get("wind_speed_10m", [0])[current_idx],
            }

        # 日別予報
        daily = data.get("daily", {})
        forecast = []
        dates = daily.get("time", [])
        for i, date in enumerate(dates):
            forecast.append({
                "date": date,
                "temp_max_c": daily.get("temperature_2m_max", [None])[i],
                "temp_min_c": daily.get("temperature_2m_min", [None])[i],
                "precipitation_mm": daily.get("precipitation_sum", [0])[i],
                "weather_code": daily.get("weather_code", [0])[i],
                "weather_description": self._weather_code_to_text(
                    daily.get("weather_code", [0])[i]
                ),
            })

        # ビジネスインパクト判定
        impact = self._assess_business_impact(current, forecast)

        return {
            "city": city["name_en"],
            "city_jp": city["name_jp"],
            "current": current,
            "forecast_3day": forecast,
            "business_impact": impact,
        }

    def _assess_business_impact(self, current: dict, forecast: list) -> dict:
        """天候のビジネスインパクトを判定"""
        alerts = []
        risk_level = "normal"

        # 現在の天候チェック
        if current.get("temperature_c") is not None:
            temp = current["temperature_c"]
            if temp >= 35:
                alerts.append({
                    "type": "extreme_heat",
                    "message_en": f"Extreme heat: {temp}°C — affects outdoor workers, energy demand surge",
                    "message_jp": f"猛暑警戒: {temp}°C — 屋外作業影響、電力需要急増",
                    "affected_sectors": ["utilities", "construction", "retail"],
                })
                risk_level = "high"
            elif temp <= -5:
                alerts.append({
                    "type": "extreme_cold",
                    "message_en": f"Extreme cold: {temp}°C — affects logistics, energy demand",
                    "message_jp": f"厳寒警戒: {temp}°C — 物流影響、暖房需要急増",
                    "affected_sectors": ["logistics", "utilities", "agriculture"],
                })
                risk_level = "high"

        # 大雨チェック
        for day in forecast:
            precip = day.get("precipitation_mm", 0)
            if precip and precip >= 50:
                alerts.append({
                    "type": "heavy_rain",
                    "date": day["date"],
                    "message_en": f"Heavy rain forecast: {precip}mm — flood/landslide risk",
                    "message_jp": f"大雨予報: {precip}mm — 洪水・土砂災害リスク",
                    "affected_sectors": ["logistics", "construction", "insurance", "agriculture"],
                })
                risk_level = "elevated" if risk_level == "normal" else risk_level

        return {
            "risk_level": risk_level,
            "alert_count": len(alerts),
            "alerts": alerts,
        }

    @staticmethod
    def _weather_code_to_text(code: int) -> str:
        """WMO天気コードを日英テキストに変換"""
        codes = {
            0: "Clear sky / 快晴",
            1: "Mainly clear / 晴れ",
            2: "Partly cloudy / 曇り時々晴れ",
            3: "Overcast / 曇り",
            45: "Fog / 霧",
            48: "Rime fog / 霧氷",
            51: "Light drizzle / 小雨",
            53: "Moderate drizzle / 雨",
            55: "Dense drizzle / 強い雨",
            61: "Slight rain / 小雨",
            63: "Moderate rain / 雨",
            65: "Heavy rain / 大雨",
            71: "Slight snow / 小雪",
            73: "Moderate snow / 雪",
            75: "Heavy snow / 大雪",
            80: "Slight rain showers / にわか雨",
            81: "Moderate rain showers / 雨",
            82: "Violent rain showers / 激しい雨",
            95: "Thunderstorm / 雷雨",
            96: "Thunderstorm with hail / 雹を伴う雷雨",
            99: "Thunderstorm with heavy hail / 大粒の雹を伴う雷雨",
        }
        return codes.get(code, f"Unknown ({code})")

    def get_available_cities(self) -> list:
        """利用可能な都市一覧を返す"""
        return [
            {
                "key": key,
                "name_en": city["name_en"],
                "name_jp": city["name_jp"],
                "latitude": city["lat"],
                "longitude": city["lon"],
            }
            for key, city in JAPAN_CITIES.items()
        ]
