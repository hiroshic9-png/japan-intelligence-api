#!/usr/bin/env python3
"""
EDINET コードリスト自動更新スクリプト

EDINET公式サイトからEDINETコードリストZIPをダウンロードし、
edinetCode → secCode マッピングJSONを更新する。

ソース: https://disclosure2dl.edinet-fsa.go.jp/searchdocument/codelist/Edinetcode.zip
フォーマット: Shift_JIS CSV (EdinetcodeDlInfo.csv)
  - 列0: EDINETコード
  - 列2: 上場区分 (「上場」のみ対象)
  - 列6: 提出者名
  - 列11: 証券コード (5桁→4桁に正規化)

Usage:
    python scripts/update_edinet_mapping.py
"""
import csv
import io
import json
import os
import sys
import zipfile
import requests
from datetime import datetime

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, '..', 'data')
MAPPING_FILE = os.path.join(DATA_DIR, 'edinet_code_map.json')

# EDINET code list ZIP URL
EDINET_CODE_LIST_URL = "https://disclosure2dl.edinet-fsa.go.jp/searchdocument/codelist/Edinetcode.zip"


def download_edinet_code_list() -> list[dict]:
    """EDINETコードリストZIPをダウンロードしてパースする。"""
    print(f"[UPDATE] Downloading EDINET code list from {EDINET_CODE_LIST_URL}...")
    resp = requests.get(EDINET_CODE_LIST_URL, timeout=30)
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        csv_name = [n for n in zf.namelist() if n.endswith('.csv')][0]
        raw_bytes = zf.read(csv_name)

    # Shift_JIS → UTF-8
    text = raw_bytes.decode('cp932')
    reader = csv.reader(io.StringIO(text))

    # Skip header lines
    next(reader)  # ダウンロード実行日行
    headers = next(reader)
    print(f"[UPDATE] Headers: {headers[:6]}...")

    entries = []
    for row in reader:
        if len(row) < 12:
            continue
        edinet_code = row[0].strip()
        listing = row[2].strip()
        name = row[6].strip()
        sec_code_raw = row[11].strip()

        if listing != '上場' or not sec_code_raw or len(sec_code_raw) < 4:
            continue

        entries.append({
            'edinet_code': edinet_code,
            'sec_code': sec_code_raw[:4],  # 5桁→4桁
            'name': name,
        })

    print(f"[UPDATE] Parsed {len(entries)} listed companies from EDINET code list")
    return entries


def update_mapping(entries: list[dict]) -> dict:
    """既存マッピングに新エントリをマージし保存する。"""
    # 既存マッピングを読み込み
    existing = {}
    if os.path.exists(MAPPING_FILE):
        with open(MAPPING_FILE, 'r', encoding='utf-8') as f:
            existing = json.load(f)
    print(f"[UPDATE] Existing mapping: {len(existing)} entries")

    new_count = 0
    updated_count = 0
    for entry in entries:
        code = entry['edinet_code']
        if code not in existing:
            existing[code] = {
                'sec_code': entry['sec_code'],
                'name': entry['name'],
            }
            new_count += 1
        else:
            # 公式リストの方が正確なので名前を更新
            if existing[code].get('name') != entry['name']:
                existing[code]['name'] = entry['name']
                updated_count += 1
            # sec_codeも更新（変更があった場合）
            if existing[code].get('sec_code') != entry['sec_code']:
                existing[code]['sec_code'] = entry['sec_code']
                updated_count += 1

    # 保存
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(MAPPING_FILE, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=0)

    print(f"[UPDATE] New entries: {new_count}")
    print(f"[UPDATE] Updated entries: {updated_count}")
    print(f"[UPDATE] Total mapping: {len(existing)} entries")
    print(f"[UPDATE] Saved to {MAPPING_FILE}")

    return existing


def main():
    try:
        entries = download_edinet_code_list()
        mapping = update_mapping(entries)
        sec_codes = set(v['sec_code'] for v in mapping.values())
        print(f"\n[UPDATE] ✅ Complete — {len(mapping)} EDINET codes → {len(sec_codes)} unique tickers")
        print(f"[UPDATE] Updated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    except Exception as e:
        print(f"[UPDATE] ❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
