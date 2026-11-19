#!/usr/bin/env python3
"""サーバーのアクセスログから、記事サイトの閲覧数を日ごとに集計する。

使い方: python3 scripts/stats.py <ログをつなげたファイル> <これまでの集計.json> <新しい集計.json>
- 出力（標準出力）は件数だけ。IP アドレスなど生のログは出さない（リポジトリが公開のため）。
- 数えるのは「人が開いたページ」：GET・200・HTMLページ・機械（検索エンジンの巡回など）を除く。
- 訪問者数は、IPアドレスとブラウザの組み合わせの数（日ごと）。集計ファイルには数だけを残す。
"""
import sys, re, json, hashlib, datetime, collections, urllib.parse

LINE = re.compile(r'\[(\d{2})/(\w{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2}) ([+-]\d{4})\] "(\S+) (\S+)[^"]*" (\d{3}) \S+(?: "([^"]*)" "([^"]*)")?')
IP = re.compile(r'(\d{1,3}(?:\.\d{1,3}){3}|[0-9a-fA-F:]*:[0-9a-fA-F:]+)')
MON = {m: i + 1 for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}
BOT = re.compile(r"bot|crawl|spider|slurp|curl|wget|python|java/|go-http|headless|lighthouse|preview|monitor|scan|facebookexternalhit|feed|rss|zapier|http-client|okhttp|axios|node-fetch|libwww|pingdom|uptime|semrush|ahrefs|mj12|dotbot|bytespider|gptbot|claude|perplexity|ccbot|dataforseo|petal|yandex|baidu", re.I)
SEARCH = [("google.", "Google検索"), ("yahoo.", "Yahoo検索"), ("bing.", "Bing検索"), ("duckduckgo.", "DuckDuckGo")]
JST = datetime.timezone(datetime.timedelta(hours=9))

def source(ref):
    if not ref or ref == "-": return "直接・不明"
    h = urllib.parse.urlparse(ref).netloc.lower()
    if not h: return "直接・不明"
    if h.endswith("guide.clarie.jp"): return None  # サイト内の移動
    if h.endswith("clarie.jp"): return "クラリエ本体サイト"
    for k, v in SEARCH:
        if k in h: return v
    if "zehitomo" in h: return "ゼヒトモ"
    if "curama" in h: return "くらしのマーケット"
    if h in ("t.co", "x.com") or "twitter" in h: return "X"
    if "instagram" in h: return "Instagram"
    if "facebook" in h: return "Facebook"
    if "line." in h or h.endswith("line.me"): return "LINE"
    return h

def main(logf, oldf, newf):
    days = collections.defaultdict(lambda: {"pv": 0, "uvset": set(), "bot": 0, "pages": collections.Counter(), "src": collections.Counter(), "dev": collections.Counter(), "hours": collections.Counter()})
    total = bad = 0
    for line in open(logf, encoding="utf-8", errors="replace"):
        total += 1
        m = LINE.search(line)
        if not m: bad += 1; continue
        dd, mon, yy, hh, mi, ss, tz, method, path, status, ref, ua = m.groups()
        off = datetime.timedelta(hours=int(tz[1:3]), minutes=int(tz[3:5])) * (1 if tz[0] == "+" else -1)
        t = datetime.datetime(int(yy), MON[mon], int(dd), int(hh), int(mi), int(ss), tzinfo=datetime.timezone(off)).astimezone(JST)
        d = days[t.date().isoformat()]
        p = path.split("?")[0]
        is_page = method == "GET" and status == "200" and (p.endswith("/") or p.endswith(".html"))
        if not is_page: continue
        if ua is None or ua in ("", "-") or BOT.search(ua): d["bot"] += 1; continue
        ipm = IP.search(line[:m.start()])
        ip = ipm.group(1) if ipm else ""
        d["pv"] += 1
        d["uvset"].add(hashlib.sha256((ip + "|" + ua).encode()).hexdigest())
        d["pages"][p] += 1
        s = source(ref)
        if s: d["src"][s] += 1
        d["dev"]["スマホ" if re.search(r"Mobile|iPhone|Android", ua) else "パソコン"] += 1
        d["hours"][f"{t.hour:02d}"] += 1
    try: old = json.load(open(oldf, encoding="utf-8"))
    except Exception: old = {}
    data = old.get("days", {})
    today = datetime.datetime.now(JST).date().isoformat()
    for k, d in days.items():
        rec = {"pv": d["pv"], "uv": len(d["uvset"]), "bot": d["bot"], "pages": dict(d["pages"].most_common(40)), "src": dict(d["src"].most_common(15)), "dev": dict(d["dev"]), "hours": dict(sorted(d["hours"].items()))}
        if k not in data or rec["pv"] >= data[k].get("pv", 0): data[k] = rec
    json.dump({"updated": datetime.datetime.now(JST).isoformat(timespec="minutes"), "days": dict(sorted(data.items()))}, open(newf, "w", encoding="utf-8"), ensure_ascii=False)

    print(f"読んだログ: {total}行（読めなかった行 {bad}）")
    if total and bad > total / 2:  # 書式が想定と違うとき：数字を伏せた見本を1行だけ出す
        for line in open(logf, encoding="utf-8", errors="replace"):
            if not LINE.search(line): print("書式の見本:", re.sub(r"[0-9a-f]", "N", line.strip())[:300]); break
    ks = sorted(data)
    print("== 日ごと（閲覧数／訪問者数／機械のアクセス）==")
    for k in ks[-10:]:
        r = data[k]; print(f"{k}{'（途中）' if k == today else ''}: {r['pv']}／{r['uv']}／{r.get('bot', 0)}")
    done = [k for k in ks if k < today]
    if done:
        y = done[-1]; r = data[y]; last7 = done[-7:]
        pv7 = sum(data[k]["pv"] for k in last7); uv7 = sum(data[k]["uv"] for k in last7)
        print(f"== {y} によく読まれたページ ==")
        for p, n in list(r["pages"].items())[:10]: print(f"{n}  {p}")
        agg = collections.Counter(); dev = collections.Counter()
        for k in last7:
            agg.update(data[k].get("src", {})); dev.update(data[k].get("dev", {}))
        print(f"== 直近{len(last7)}日の流入元 ==")
        for s, n in agg.most_common(10): print(f"{n}  {s}")
        print("== 直近の端末 ==", "・".join(f"{a}{b}" for a, b in dev.most_common()))
        print(f"REPORT: {y[5:].replace('-', '/')}の閲覧数{r['pv']}・訪問者{r['uv']}／直近{len(last7)}日の閲覧数{pv7}・訪問者のべ{uv7}／記録開始からの閲覧数{sum(data[k]['pv'] for k in done)}")

if __name__ == "__main__":
    main(*sys.argv[1:4])
