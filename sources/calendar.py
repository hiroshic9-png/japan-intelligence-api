"""
Japan Intelligence — 経済カレンダーデータソース

APIキー不要。主要な日本経済イベントの定期カレンダー。
BOJ政策決定会合、日銀短観、雇用統計、GDP速報等のスケジュール。
"""
from datetime import datetime, date

# 2026年の主要経済イベントスケジュール（既知の定期発表）
# 実際の日程は年初に確定するが、パターンは安定
JAPAN_ECONOMIC_CALENDAR_2026 = [
    # BOJ金融政策決定会合（年8回）
    {"date": "2026-01-22", "event": "BOJ Policy Meeting", "event_jp": "日銀金融政策決定会合",
     "category": "monetary_policy", "importance": "critical",
     "description": "Interest rate decision and monetary policy outlook"},
    {"date": "2026-03-13", "event": "BOJ Policy Meeting", "event_jp": "日銀金融政策決定会合",
     "category": "monetary_policy", "importance": "critical"},
    {"date": "2026-04-30", "event": "BOJ Policy Meeting + Outlook Report",
     "event_jp": "日銀金融政策決定会合＋展望レポート",
     "category": "monetary_policy", "importance": "critical"},
    {"date": "2026-06-18", "event": "BOJ Policy Meeting", "event_jp": "日銀金融政策決定会合",
     "category": "monetary_policy", "importance": "critical"},
    {"date": "2026-07-30", "event": "BOJ Policy Meeting + Outlook Report",
     "event_jp": "日銀金融政策決定会合＋展望レポート",
     "category": "monetary_policy", "importance": "critical"},
    {"date": "2026-09-17", "event": "BOJ Policy Meeting", "event_jp": "日銀金融政策決定会合",
     "category": "monetary_policy", "importance": "critical"},
    {"date": "2026-10-29", "event": "BOJ Policy Meeting + Outlook Report",
     "event_jp": "日銀金融政策決定会合＋展望レポート",
     "category": "monetary_policy", "importance": "critical"},
    {"date": "2026-12-17", "event": "BOJ Policy Meeting", "event_jp": "日銀金融政策決定会合",
     "category": "monetary_policy", "importance": "critical"},

    # 日銀短観（年4回: 4月/7月/10月/12月）
    {"date": "2026-04-01", "event": "BOJ Tankan Survey (Q1)",
     "event_jp": "日銀短観 1-3月期",
     "category": "survey", "importance": "high"},
    {"date": "2026-07-01", "event": "BOJ Tankan Survey (Q2)",
     "event_jp": "日銀短観 4-6月期",
     "category": "survey", "importance": "high"},
    {"date": "2026-10-01", "event": "BOJ Tankan Survey (Q3)",
     "event_jp": "日銀短観 7-9月期",
     "category": "survey", "importance": "high"},
    {"date": "2026-12-14", "event": "BOJ Tankan Survey (Q4)",
     "event_jp": "日銀短観 10-12月期",
     "category": "survey", "importance": "high"},

    # GDP速報（四半期ごと）
    {"date": "2026-02-16", "event": "GDP Preliminary (Q4 2025)",
     "event_jp": "GDP速報 2025年10-12月期",
     "category": "gdp", "importance": "high"},
    {"date": "2026-05-18", "event": "GDP Preliminary (Q1 2026)",
     "event_jp": "GDP速報 2026年1-3月期",
     "category": "gdp", "importance": "high"},
    {"date": "2026-08-17", "event": "GDP Preliminary (Q2 2026)",
     "event_jp": "GDP速報 2026年4-6月期",
     "category": "gdp", "importance": "high"},
    {"date": "2026-11-16", "event": "GDP Preliminary (Q3 2026)",
     "event_jp": "GDP速報 2026年7-9月期",
     "category": "gdp", "importance": "high"},

    # CPI（毎月下旬）
    {"date": "2026-01-23", "event": "CPI (Dec 2025)", "event_jp": "消費者物価指数 12月",
     "category": "inflation", "importance": "medium"},
    {"date": "2026-02-20", "event": "CPI (Jan 2026)", "event_jp": "消費者物価指数 1月",
     "category": "inflation", "importance": "medium"},
    {"date": "2026-03-20", "event": "CPI (Feb 2026)", "event_jp": "消費者物価指数 2月",
     "category": "inflation", "importance": "medium"},
    {"date": "2026-04-24", "event": "CPI (Mar 2026)", "event_jp": "消費者物価指数 3月",
     "category": "inflation", "importance": "medium"},
    {"date": "2026-05-22", "event": "CPI (Apr 2026)", "event_jp": "消費者物価指数 4月",
     "category": "inflation", "importance": "medium"},
    {"date": "2026-06-19", "event": "CPI (May 2026)", "event_jp": "消費者物価指数 5月",
     "category": "inflation", "importance": "medium"},
    {"date": "2026-07-24", "event": "CPI (Jun 2026)", "event_jp": "消費者物価指数 6月",
     "category": "inflation", "importance": "medium"},
    {"date": "2026-08-21", "event": "CPI (Jul 2026)", "event_jp": "消費者物価指数 7月",
     "category": "inflation", "importance": "medium"},
    {"date": "2026-09-18", "event": "CPI (Aug 2026)", "event_jp": "消費者物価指数 8月",
     "category": "inflation", "importance": "medium"},
    {"date": "2026-10-23", "event": "CPI (Sep 2026)", "event_jp": "消費者物価指数 9月",
     "category": "inflation", "importance": "medium"},
    {"date": "2026-11-20", "event": "CPI (Oct 2026)", "event_jp": "消費者物価指数 10月",
     "category": "inflation", "importance": "medium"},
    {"date": "2026-12-18", "event": "CPI (Nov 2026)", "event_jp": "消費者物価指数 11月",
     "category": "inflation", "importance": "medium"},

    # 雇用統計（毎月末）
    {"date": "2026-01-30", "event": "Employment Statistics (Dec)", "event_jp": "雇用統計 12月",
     "category": "employment", "importance": "medium"},
    {"date": "2026-02-27", "event": "Employment Statistics (Jan)", "event_jp": "雇用統計 1月",
     "category": "employment", "importance": "medium"},
    {"date": "2026-03-31", "event": "Employment Statistics (Feb)", "event_jp": "雇用統計 2月",
     "category": "employment", "importance": "medium"},
    {"date": "2026-04-28", "event": "Employment Statistics (Mar)", "event_jp": "雇用統計 3月",
     "category": "employment", "importance": "medium"},

    # 決算シーズン（集中期）
    {"date": "2026-01-26", "event": "Q3 Earnings Season Start",
     "event_jp": "第3四半期決算シーズン開始",
     "category": "earnings", "importance": "high"},
    {"date": "2026-04-27", "event": "Full Year Earnings Season Start",
     "event_jp": "本決算シーズン開始",
     "category": "earnings", "importance": "critical"},
    {"date": "2026-07-27", "event": "Q1 Earnings Season Start",
     "event_jp": "第1四半期決算シーズン開始",
     "category": "earnings", "importance": "high"},
    {"date": "2026-10-26", "event": "Q2 Earnings Season Start",
     "event_jp": "第2四半期決算シーズン開始",
     "category": "earnings", "importance": "high"},

    # 日本市場休場日（主要）
    {"date": "2026-01-01", "event": "Market Holiday: New Year", "event_jp": "休場: 元日",
     "category": "holiday", "importance": "info"},
    {"date": "2026-01-02", "event": "Market Holiday: New Year", "event_jp": "休場: 年始休暇",
     "category": "holiday", "importance": "info"},
    {"date": "2026-01-03", "event": "Market Holiday: New Year", "event_jp": "休場: 年始休暇",
     "category": "holiday", "importance": "info"},
    {"date": "2026-01-12", "event": "Market Holiday: Coming of Age Day",
     "event_jp": "休場: 成人の日", "category": "holiday", "importance": "info"},
    {"date": "2026-02-11", "event": "Market Holiday: National Foundation Day",
     "event_jp": "休場: 建国記念の日", "category": "holiday", "importance": "info"},
    {"date": "2026-02-23", "event": "Market Holiday: Emperor's Birthday",
     "event_jp": "休場: 天皇誕生日", "category": "holiday", "importance": "info"},
    {"date": "2026-03-20", "event": "Market Holiday: Vernal Equinox",
     "event_jp": "休場: 春分の日", "category": "holiday", "importance": "info"},
    {"date": "2026-04-29", "event": "Market Holiday: Showa Day",
     "event_jp": "休場: 昭和の日", "category": "holiday", "importance": "info"},
    {"date": "2026-05-03", "event": "Market Holiday: Constitution Day",
     "event_jp": "休場: 憲法記念日", "category": "holiday", "importance": "info"},
    {"date": "2026-05-04", "event": "Market Holiday: Greenery Day",
     "event_jp": "休場: みどりの日", "category": "holiday", "importance": "info"},
    {"date": "2026-05-05", "event": "Market Holiday: Children's Day",
     "event_jp": "休場: こどもの日", "category": "holiday", "importance": "info"},
    {"date": "2026-07-20", "event": "Market Holiday: Marine Day",
     "event_jp": "休場: 海の日", "category": "holiday", "importance": "info"},
    {"date": "2026-08-11", "event": "Market Holiday: Mountain Day",
     "event_jp": "休場: 山の日", "category": "holiday", "importance": "info"},
    {"date": "2026-09-21", "event": "Market Holiday: Respect for the Aged Day",
     "event_jp": "休場: 敬老の日", "category": "holiday", "importance": "info"},
    {"date": "2026-09-23", "event": "Market Holiday: Autumnal Equinox",
     "event_jp": "休場: 秋分の日", "category": "holiday", "importance": "info"},
    {"date": "2026-10-12", "event": "Market Holiday: Sports Day",
     "event_jp": "休場: スポーツの日", "category": "holiday", "importance": "info"},
    {"date": "2026-11-03", "event": "Market Holiday: Culture Day",
     "event_jp": "休場: 文化の日", "category": "holiday", "importance": "info"},
    {"date": "2026-11-23", "event": "Market Holiday: Labor Thanksgiving Day",
     "event_jp": "休場: 勤労感謝の日", "category": "holiday", "importance": "info"},
    {"date": "2026-12-31", "event": "Market Holiday: Year End",
     "event_jp": "休場: 大晦日", "category": "holiday", "importance": "info"},
]


class EconomicCalendarSource:
    """日本の経済カレンダーデータソース"""

    def get_upcoming_events(self, days: int = 30, category: str = None,
                            importance: str = None) -> dict:
        today = date.today()
        target_end = date(today.year, today.month, today.day)

        from datetime import timedelta
        target_end = today + timedelta(days=days)

        events = []
        for evt in JAPAN_ECONOMIC_CALENDAR_2026:
            evt_date = date.fromisoformat(evt["date"])
            if today <= evt_date <= target_end:
                if category and evt["category"] != category:
                    continue
                if importance and evt["importance"] != importance:
                    continue
                days_until = (evt_date - today).days
                events.append({
                    **evt,
                    "days_until": days_until,
                    "is_today": days_until == 0,
                    "is_this_week": days_until <= 7,
                })

        # 次のクリティカルイベント
        critical = [e for e in events if e["importance"] == "critical"]
        next_critical = critical[0] if critical else None

        return {
            "period": {"from": today.isoformat(), "to": target_end.isoformat(), "days": days},
            "total_events": len(events),
            "events": events,
            "next_critical_event": next_critical,
            "categories": list(set(e["category"] for e in events)),
            "source": "Japan Intelligence Economic Calendar",
            "note": "Dates are approximate for 2026. Actual dates confirmed by respective agencies.",
        }

    def get_market_holidays(self, month: int = None) -> dict:
        holidays = [e for e in JAPAN_ECONOMIC_CALENDAR_2026 if e["category"] == "holiday"]
        if month:
            holidays = [h for h in holidays
                        if date.fromisoformat(h["date"]).month == month]
        return {
            "total": len(holidays),
            "holidays": holidays,
            "source": "TSE Market Calendar 2026",
        }

    def get_available_categories(self) -> list:
        return [
            {"key": "monetary_policy", "label": "金融政策", "description": "BOJ政策決定会合"},
            {"key": "survey", "label": "企業調査", "description": "日銀短観等"},
            {"key": "gdp", "label": "GDP", "description": "GDP速報・確報"},
            {"key": "inflation", "label": "物価", "description": "CPI"},
            {"key": "employment", "label": "雇用", "description": "雇用統計"},
            {"key": "earnings", "label": "決算", "description": "決算シーズン"},
            {"key": "holiday", "label": "休場日", "description": "東証休場日"},
        ]
