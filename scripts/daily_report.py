#!/usr/bin/env python3
"""毎日の報告用に、投稿数とチェックマークを出す。

使い方:
  python3 scripts/daily_report.py [--date 2026-11-19] [--live ok|ng] [--gbp-month "2026年10月: 閲覧数175 …"]

--live   … GitHub Actions の「本番URLで公開を確認」ステップの結果（ok / ng）。省略時は「未確認」。
--gbp-month … Gmail に届く Googleビジネスプロフィールの月次レポートの数字（セッションが読んで渡す）。
先に python3 scripts/build.py を実行して dist/gbp.xml を作っておくこと。
"""
import argparse, datetime, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parent.parent
ZEHITOMO_ID = 'id="ref_6af6721afb91c8d6b1ea7668_estate-items-liquidator"'

ap = argparse.ArgumentParser()
ap.add_argument("--date", default=(datetime.datetime.utcnow() + datetime.timedelta(hours=9)).date().isoformat())
ap.add_argument("--live", choices=["ok", "ng"], default=None)
ap.add_argument("--gbp-month", default="")
ap.add_argument("--lp-views", default="", help="stats.yml の実行ログの REPORT: 行の中身")
a = ap.parse_args()

posts = sorted((ROOT / "content" / "posts").glob("*.md"))
def date_of(p):
    m = re.search(r"^date:\s*'?([0-9-]+)", p.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else ""
today = [p for p in posts if date_of(p) == a.date]
published = [p for p in posts if date_of(p) <= a.date]
zeh_all = [p for p in published if ZEHITOMO_ID in p.read_text(encoding="utf-8")]
zeh_today = [p for p in today if ZEHITOMO_ID in p.read_text(encoding="utf-8")]

slugs_today = set()
for p in today:
    m = re.search(r"^slug:\s*(\S+)", p.read_text(encoding="utf-8"), re.M)
    if m: slugs_today.add(m.group(1))
gbp_xml = ROOT / "dist" / "gbp.xml"
gbp_today = 0
if gbp_xml.exists():
    links = re.findall(r"<link>[^<]*/posts/([^/<]+)/</link>", gbp_xml.read_text(encoding="utf-8"))
    gbp_today = sum(1 for s in links if s in slugs_today)

def mark(ok):
    return "✅" if ok else "❌"

lp_ok = len(today) >= 3 and a.live == "ok"
lp_note = "" if a.live else "（本番の公開は未確認）"
print(f"クラリエLP {mark(lp_ok)} 今日{len(today)}本／累計{len(published)}本{lp_note}" + (f"／{a.lp_views}" if a.lp_views else ""))
gbp_line = f"グーグルマップ {mark(gbp_today >= 1)} 投稿用一覧に今日{gbp_today}本"
if a.gbp_month:
    gbp_line += f"／{a.gbp_month}"
print(gbp_line)
print("くらしのマーケット － 確認できる情報がありません")
print(f"ゼヒトモ {mark(len(zeh_today) == 1)} 今日{len(zeh_today)}本にタグ／累計{len(zeh_all)}本")
