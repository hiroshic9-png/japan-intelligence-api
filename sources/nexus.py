"""
NEXUS Power Network Source — NEXUSグラフから人物・関係データを取得

Neo4j上のNEXUSインテリジェンスグラフに接続し、
企業の役員ネットワーク、天下り関係、パスファインディングを提供する。

接続情報:
  NEO4J_URI  - bolt://192.168.1.39:7687
  NEO4J_USER - neo4j
  NEO4J_PASS - NexusGraph2026
"""

import os
from datetime import datetime

# Neo4j接続はオプション（Mac Mini到達不能時にも起動可能にする）
try:
    from neo4j import GraphDatabase
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False


class NexusSource:
    """NEXUSパワーネットワークグラフへのアクセス"""

    def __init__(self):
        self.uri = os.getenv("NEO4J_URI", "bolt://192.168.1.39:7687")
        self.user = os.getenv("NEO4J_USER", "neo4j")
        self.password = os.getenv("NEO4J_PASS", "NexusGraph2026")
        self._driver = None

    def _get_driver(self):
        """遅延接続: 初回アクセス時にのみ接続"""
        if not NEO4J_AVAILABLE:
            raise RuntimeError("neo4j Python driver not installed")
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                self.uri, auth=(self.user, self.password)
            )
        return self._driver

    def _safe_query(self, query: str, params: dict = None) -> list:
        """接続エラーをハンドリングしてクエリ実行"""
        try:
            driver = self._get_driver()
            with driver.session() as session:
                result = session.run(query, **(params or {}))
                return [dict(r) for r in result]
        except Exception as e:
            print(f"[NEXUS] Query failed: {e}")
            return []

    def get_company_network(self, company_name: str) -> dict:
        """
        企業の役員ネットワークを取得。
        天下り関係、役員の経歴カテゴリ、パワースコアを含む。
        """
        # Step 1: 企業の役員一覧
        officers = self._safe_query('''
            MATCH (p:Person)-[r:OFFICER_OF]->(o:Organization)
            WHERE o.name CONTAINS $company_name AND r.actionable = true
            OPTIONAL MATCH (p)-[bt:BUREAUCRATIC_TIE]->(ministry:Organization)
            WHERE bt.subtype = "amakudari"
            RETURN p.name_ja AS name,
                   p.category AS category,
                   p.power_score AS power_score,
                   r.role AS role,
                   o.name AS company,
                   ministry.name AS amakudari_from,
                   bt.source_position AS former_position
            ORDER BY p.power_score DESC
        ''', {"company_name": company_name})

        # Step 2: 天下り人物のカウント
        amakudari_count = sum(1 for o in officers if o.get("amakudari_from"))
        categories = {}
        for o in officers:
            cat = o.get("category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1

        return {
            "company": company_name,
            "officer_count": len(officers),
            "amakudari_count": amakudari_count,
            "category_breakdown": categories,
            "officers": officers,
            "queried_at": datetime.now().isoformat(),
        }

    def find_path(self, person_a: str, person_b: str, max_hops: int = 5) -> dict:
        """
        2人の人物間の最短パスを検索。
        """
        results = self._safe_query('''
            MATCH (a:Person), (b:Person)
            WHERE replace(a.name_ja, ' ', '') = replace($person_a, ' ', '')
              AND replace(b.name_ja, ' ', '') = replace($person_b, ' ', '')
            MATCH path = shortestPath((a)-[*..''' + str(max_hops) + ''']-(b))
            RETURN [n IN nodes(path) | coalesce(n.name_ja, n.name)] AS route,
                   [r IN relationships(path) | type(r)] AS relationships,
                   length(path) AS hops
        ''', {"person_a": person_a, "person_b": person_b})

        if results:
            r = results[0]
            return {
                "from": person_a,
                "to": person_b,
                "found": True,
                "hops": r["hops"],
                "route": r["route"],
                "relationships": r["relationships"],
                "queried_at": datetime.now().isoformat(),
            }
        return {
            "from": person_a,
            "to": person_b,
            "found": False,
            "hops": None,
            "route": [],
            "relationships": [],
            "queried_at": datetime.now().isoformat(),
        }

    def get_person(self, person_name: str) -> dict:
        """人物の詳細情報と接続先を取得"""
        results = self._safe_query('''
            MATCH (p:Person)
            WHERE replace(p.name_ja, ' ', '') = replace($name, ' ', '')
            OPTIONAL MATCH (p)-[r:OFFICER_OF {actionable: true}]->(o:Organization)
            OPTIONAL MATCH (p)-[bt:BUREAUCRATIC_TIE]->(ministry:Organization)
            WHERE bt.subtype = "amakudari"
            RETURN p.name_ja AS name,
                   p.category AS category,
                   p.power_score AS power_score,
                   p.primary_affiliation AS affiliation,
                   p.primary_title AS title,
                   collect(DISTINCT {company: o.name, role: r.role}) AS companies,
                   collect(DISTINCT {ministry: ministry.name, position: bt.source_position}) AS amakudari
        ''', {"name": person_name})

        if results:
            r = results[0]
            return {
                "name": r["name"],
                "category": r["category"],
                "power_score": r["power_score"],
                "affiliation": r["affiliation"],
                "title": r["title"],
                "companies": [c for c in r["companies"] if c.get("company")],
                "amakudari": [a for a in r["amakudari"] if a.get("ministry")],
                "queried_at": datetime.now().isoformat(),
            }
        return {"name": person_name, "found": False}

    def get_stats(self) -> dict:
        """NEXUSグラフの基本統計"""
        results = self._safe_query('''
            MATCH (p:Person) WITH count(p) AS persons
            MATCH (o:Organization) WITH persons, count(o) AS orgs
            MATCH ()-[r:BUREAUCRATIC_TIE]->() WHERE r.subtype = "amakudari"
            RETURN persons, orgs, count(r) AS amakudari_edges
        ''')
        if results:
            r = results[0]
            return {
                "persons": r["persons"],
                "organizations": r["orgs"],
                "amakudari_edges": r["amakudari_edges"],
                "status": "connected",
                "queried_at": datetime.now().isoformat(),
            }
        return {"status": "disconnected", "queried_at": datetime.now().isoformat()}
