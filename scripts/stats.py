#!/usr/bin/env python3
"""サーバーのアクセスログから、記事サイトの閲覧数を日ごとに集計する。

使い方: python3 scripts/stats.py <ログをつなげたファイル> <これまでの集計.json> <新しい集計.json> [地域データベース.mmdb]
- 地域データベース（DB-IP の無料版。IP Geolocation by DB-IP https://db-ip.com ）を渡すと、都道府県ごとの数も出す。
  IPアドレスは外部に送らず、手元のデータベースで引く。スマホ回線は実際の場所と違う地域になることがある。
- 出力（標準出力）は件数だけ。IP アドレスなど生のログは出さない（リポジトリが公開のため）。
- 数えるのは「人が開いたページ」：GET・200・HTMLページ・機械（検索エンジンの巡回など）を除く。
- 訪問者数は、IPアドレスとブラウザの組み合わせの数（日ごと）。集計ファイルには数だけを残す。
"""
import sys, re, json, hashlib, datetime, collections, urllib.parse, unicodedata

PREF = dict(zip("hokkaido aomori iwate miyagi akita yamagata fukushima ibaraki tochigi gunma saitama chiba tokyo kanagawa niigata toyama ishikawa fukui yamanashi nagano gifu shizuoka aichi mie shiga kyoto osaka hyogo nara wakayama tottori shimane okayama hiroshima yamaguchi tokushima kagawa ehime kochi fukuoka saga nagasaki kumamoto oita miyazaki kagoshima okinawa".split(),
                "北海道 青森 岩手 宮城 秋田 山形 福島 茨城 栃木 群馬 埼玉 千葉 東京 神奈川 新潟 富山 石川 福井 山梨 長野 岐阜 静岡 愛知 三重 滋賀 京都 大阪 兵庫 奈良 和歌山 鳥取 島根 岡山 広島 山口 徳島 香川 愛媛 高知 福岡 佐賀 長崎 熊本 大分 宮崎 鹿児島 沖縄".split()))

def region(db, ip):
    """IPアドレス → 「神奈川」などの地域名。日本以外は「海外（国名）」。分からなければ「不明」。"""
    if not db or not ip: return "不明"
    try: r = db.get(ip)
    except Exception: r = None
    if not r: return "不明"
    cc = (r.get("country") or {}).get("iso_code", "")
    if cc != "JP":
        return "海外（" + ((r.get("country") or {}).get("names", {}).get("ja") or (r.get("country") or {}).get("names", {}).get("en") or cc or "不明") + "）"
    sub = (r.get("subdivisions") or [{}])[0].get("names", {}).get("en", "")
    k = unicodedata.normalize("NFKD", sub).encode("ascii", "ignore").decode().lower()
    k = re.sub(r"[^a-z]", "", re.sub(r"prefecture|\b(ken|to|fu)\b", "", k.replace("-", " ")))
    return PREF.get(k, "日本（都道府県不明）")

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

def main(logf, oldf, newf, mmdb=None):
    db = None
    if mmdb:
        try:
            import maxminddb; db = maxminddb.open_database(mmdb)
        except Exception as e: print("地域データベースを開けませんでした:", type(e).__name__)
    days = collections.defaultdict(lambda: {"geo": collections.Counter(), "geouv": collections.defaultdict(set), "pv": 0, "uvset": set(), "bot": 0, "pages": collections.Counter(), "src": collections.Counter(), "dev": collections.Counter(), "hours": collections.Counter()})
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
        if db:
            g = region(db, ip); d["geo"][g] += 1; d["geouv"][g].add(ip + "|" + ua)
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
        if db:
            rec["geo"] = dict(d["geo"].most_common(30)); rec["geo_uv"] = {g: len(v) for g, v in d["geouv"].items()}
            # 国内だけの数。海外からのアクセスは、ブラウザを名乗る機械であることが多いので分けて数える。
            rec["jp_pv"] = sum(n for g, n in d["geo"].items() if not g.startswith(("海外", "不明")))
            rec["jp_uv"] = sum(len(v) for g, v in d["geouv"].items() if not g.startswith(("海外", "不明")))
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
        geo = collections.Counter(); geouv = collections.Counter()
        for k in last7:
            geo.update(data[k].get("geo", {})); geouv.update(data[k].get("geo_uv", {}))
        geo_txt = ""
        if geo:
            print(f"== 直近{len(last7)}日の地域（閲覧数／訪問者のべ）※スマホ回線は実際と違う地域になることがあります。IP Geolocation by DB-IP ==")
            for g, n in geo.most_common(15): print(f"{g}: {n}／{geouv.get(g, 0)}")
            jp = [(g, n) for g, n in geouv.most_common() if not g.startswith(("海外", "不明"))]
            jp7 = sum(data[k].get("jp_pv", 0) for k in last7); jpu7 = sum(data[k].get("jp_uv", 0) for k in last7)
            print(f"== 国内だけ（閲覧数／訪問者数）==")
            for k in last7: print(f"{k}: {data[k].get('jp_pv', '-')}／{data[k].get('jp_uv', '-')}")
            geo_txt = (f"／うち国内：{y[5:].replace('-', '/')}の閲覧数{r.get('jp_pv', 0)}・訪問者{r.get('jp_uv', 0)}、直近{len(last7)}日の閲覧数{jp7}・訪問者のべ{jpu7}"
                       + "（" + "・".join(f"{g}{n}" for g, n in jp[:6]) + "）" + f"／海外からの閲覧{pv7 - jp7}は機械の可能性が高い")
        print(f"REPORT: {y[5:].replace('-', '/')}の閲覧数{r['pv']}・訪問者{r['uv']}／直近{len(last7)}日の閲覧数{pv7}・訪問者のべ{uv7}／記録開始からの閲覧数{sum(data[k]['pv'] for k in done)}{geo_txt}")

if __name__ == "__main__":
    main(*sys.argv[1:5])
