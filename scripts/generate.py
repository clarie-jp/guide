#!/usr/bin/env python3
"""キーワード表（4領域）から未着手のものを比率どおりに取り、Claude API で記事を生成して content/posts に保存する。

使い方:
  ANTHROPIC_API_KEY=... python3 scripts/generate.py            # site.yaml の posts_per_run 本
  ANTHROPIC_API_KEY=... python3 scripts/generate.py --count 1  # 本数を指定
  python3 scripts/generate.py --dry-run                        # 次に書く対象を表示するだけ

4領域（keywords.csv の domain 列 / site.yaml の mix）:
  basic : 費用・手順・相続など全国共通の基礎記事
  area  : 市区 × サービスの地域記事（区固有の情報を必ず入れる）
  case  : cases.csv の現場データから書く事例記事（架空の事例は作らない）
  item  : 遺品・生前整理で出てくる品目別の買取記事

生成の流れ:
  1. 領域ごとの進捗を見て、mix の比率に一番足りていない領域から順に選ぶ
  2. 既存記事のタイトル一覧を渡して重複を避け、内部リンク候補も渡す
  3. JSON で返させる（title / description / slug / body_md / faq）
  4. 品質チェックに通ったものだけ保存し、表の status を done にする
"""
import argparse, csv, json, os, re, sys, datetime, pathlib, urllib.request, urllib.error, collections

ROOT = pathlib.Path(__file__).resolve().parent.parent
import yaml
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import consistency
SITE = yaml.safe_load((ROOT / "site.yaml").read_text(encoding="utf-8"))
KW = ROOT / "keywords.csv"
CASES = ROOT / "cases.csv"
POSTS = ROOT / "content" / "posts"
DRAFTS = ROOT / "content" / "drafts"
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")

BANNED = ["必ず売れる", "絶対に", "最安", "日本一", "No.1", "ナンバーワン", "業界最安", "100%", "完全無料で全部"]
MIN_CHARS = {"basic": 2600, "area": 2400, "case": 1800, "item": 2000}
KW_FIELDS = ["priority", "category", "keyword", "intent", "angle", "status", "slug", "domain"]
CASE_FIELDS = ["id", "month", "area", "age", "units", "visitors", "sales_man", "items", "notes", "takeaway", "status", "slug"]


def load_csv(path):
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_csv(path, rows, fields):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)


def parse_frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    return yaml.safe_load(m.group(1)) if m else None


def existing_posts():
    out = []
    for p in sorted(POSTS.glob("*.md")):
        fm = parse_frontmatter(p.read_text(encoding="utf-8"))
        if fm:
            out.append({"title": fm.get("title", ""), "slug": fm.get("slug", p.stem),
                        "category": fm.get("category", ""), "domain": fm.get("domain", "basic")})
    return out


# ---------- 対象の選び方（比率制御） ----------

def pick_targets(count, kws, cases, posts):
    """mix の比率に対して一番遅れている領域から1本ずつ選ぶ。候補が尽きた領域は飛ばす。"""
    mix = SITE.get("mix", {"basic": 1.0})
    done = collections.Counter(p["domain"] for p in posts)
    pools = {
        "basic": sorted([r for r in kws if r["status"] == "todo" and r.get("domain", "basic") == "basic"], key=lambda r: int(r["priority"])),
        "area": sorted([r for r in kws if r["status"] == "todo" and r.get("domain") == "area"], key=lambda r: int(r["priority"])),
        "item": sorted([r for r in kws if r["status"] == "todo" and r.get("domain") == "item"], key=lambda r: int(r["priority"])),
        "case": [c for c in cases if c["status"] == "todo"],
    }
    targets = []
    for _ in range(count):
        total = sum(done.values()) + 1
        # 「目標比率 − 現在比率」が最大の領域。候補がない領域は除く
        cand = [(mix.get(d, 0) - done[d] / total, d) for d in pools if pools[d] and mix.get(d, 0) > 0]
        if not cand: break
        _, dom = max(cand)
        row = pools[dom].pop(0)
        targets.append((dom, row))
        done[dom] += 1
    return targets


# ---------- プロンプト ----------

def common_rules(posts, extra_links=40):
    links = "\n".join(f"- {p['title']}（/posts/{p['slug']}/）" for p in posts[-extra_links:]) or "（まだありません）"
    a = SITE["author"]
    return f"""【書き手】{a['name']}（{a['title']}）。{a['bio']}
【会社】{SITE['company']}。生前整理・遺品整理サービス「クラリエ」。買取（古物商）と整理を一括で行い、買取額を整理費用から差し引ける。対応エリアは{SITE['area']}。

{consistency.facts_for_prompt(SITE)}

【守ること】
- 見出しは「## 」と「### 」を使い、## は4〜7個。最初の## の前に、結論を3行以内で書く導入を置く
- 一次情報を入れる：現場で実際にある場面、見積りで見る項目、作業の段取り、よくある失敗。一般論の羅列にしない
- 数字は目安として幅で書き、「2026年時点の目安」と添える。法律・税務・医療は断定せず「専門家に確認」を添える
- 他社や特定の業者、管理会社、個人の名前は出さない。「{'」「'.join(BANNED)}」などの誇張表現は使わない
- 文体は「です・ます」。一文は60文字以内を目安に、短く。箇条書きと表を適度に使う（表はMarkdownの表）
- 読者が自分で判断できる基準を示したうえで、最後にクラリエへの相談を「選択肢のひとつ」として案内する。押し売りにしない
- 内部リンクを2〜4本、本文中に自然に入れる。リンク先は次の既存記事から選ぶ（存在しないURLを作らない）：
{links}
- 記事の最後に「よくある質問」を3〜5問。質問は検索されそうな言い回しにする

【出力形式】次のJSONだけを返す（前後に説明文を付けない）:
{{
  "title": "32文字以内。キーワードを自然に含む。記号は「｜」のみ可",
  "description": "110〜130文字。検索結果に出る要約。キーワードを含む",
  "slug": "英小文字とハイフンのみ、40文字以内、意味が分かる英語",
  "tags": ["3〜5個の日本語タグ"],
  "body_md": "本文のMarkdown（## 見出しから。タイトルのH1は書かない。『よくある質問』の見出しは書かない）",
  "faq": [{{"q": "質問", "a": "回答 80〜200文字"}}]
}}"""


def prompt_basic(kw, posts):
    cats = SITE["categories"]
    return f"""あなたは「{SITE['site_name']}」の編集者です。読者は、親の家の片付けや自分の身辺整理に直面している40〜70代で、横浜・神奈川・東京に住んでいます。
検索キーワード「{kw['keyword']}」で検索した人が、読み終えたときに「次に何をすればいいか」が分かる記事を書いてください。本文は3,000〜4,500文字。

【この記事の切り口】{kw['angle']}
【検索意図】{kw['intent']}
【カテゴリ】{cats.get(kw['category'], kw['category'])}

{common_rules(posts)}"""


def prompt_area(kw, posts):
    place = kw["keyword"].rsplit(" ", 1)[0]
    return f"""あなたは「{SITE['site_name']}」の編集者です。読者は「{place}」に住んでいる、または{place}にある親の家を片付けようとしている人です。
検索キーワード「{kw['keyword']}」で検索した人向けに、その地域に特化した記事を書いてください。本文は2,800〜4,000文字。

【この記事の切り口】{kw['angle']}
【地域記事で必ず入れること】
- {place}の住宅の特徴（分譲マンション・団地・戸建の多さ、築年の傾向、駅からの距離、エレベーターの有無など、一般に知られている範囲で）と、それが片付け・搬出・費用にどう影響するか
- {place}の自治体（市区）の粗大ごみ・家電リサイクル・不用品回収の仕組みの概要。料金や収集日は変わるので具体額は書かず、「自治体の案内で確認」を添える
- {place}で相談が多いケース（例：遠方に住む子世代からの依頼、施設入居前の整理、賃貸退去）
- 他の地域の記事と同じ文章にならないよう、{place}固有の話を中心にする。地名を差し替えただけの文章は不可
【カテゴリ】地域別

{common_rules(posts)}"""


def prompt_item(kw, posts):
    item = kw["keyword"].replace("遺品 ", "").replace(" 買取", "")
    return f"""あなたは「{SITE['site_name']}」の編集者です。読者は、遺品整理や生前整理の最中に「{item}」が出てきて、売れるのか、捨てるべきか迷っている人です。
検索キーワード「{kw['keyword']}」で検索した人向けに、買取の専門家として記事を書いてください。本文は2,400〜3,500文字。

【この記事の切り口】{kw['angle']}
【品目記事で必ず入れること】
- {item}に値段が付く条件と付かない条件（状態・付属品・年代・ブランドや作家・需要）
- 査定の前にやってはいけないこと（洗う・磨く・分解する・付属品を捨てる など、品目に応じて）
- 相場は「幅」で書き、「2026年時点の目安」と添える。相場が変動しやすい物（貴金属など）はその旨を書く
- 値段が付かない場合の処分方法（自治体回収・リサイクル・寄付など）
- 遺品整理・生前整理の中で{item}が出てきたときに、整理と買取を同じ窓口で頼むとどう楽になるか
【カテゴリ】買取と処分

{common_rules(posts)}"""


def prompt_case(c, posts):
    return f"""あなたは「{SITE['site_name']}」の編集者です。次の現場データは、マンション管理会社と共催した「居住者向け買取相談会」の実際の記録です。これをもとに、読者（同じようなマンションに住む人や、親の家の片付けを考えている人）の参考になる事例記事を書いてください。本文は2,000〜3,000文字。

【現場データ（この範囲の事実だけを使う。数字を盛らない、架空の人物やセリフを作らない）】
- 時期：{c['month']}
- 場所：{c['area']}の分譲マンション（{c['age']}・{c['units']}）
- 来場・成約：{c['visitors']}
- 買取額の合計：約{c['sales_man']}万円
- 多かった品目：{c['items']}
- 現場の記録：{c['notes']}
- 現場からの学び：{c['takeaway']}

【事例記事で必ず入れること】
- マンション名・管理会社名・個人名は書かない。「{c['area']}の築約○年・約○戸のマンション」と表現する
- 何が持ち込まれ、どう査定し、居住者がどんな相談をしたかを具体的に。読者が「自分の家にもある」と思える描写にする
- この事例から読者が持ち帰れる判断基準を2〜3点、見出しを立てて書く
- 「買取相談会」は管理会社と提携して開いているもので、個人宅への出張査定も同じ流れで対応できることを自然に伝える
【カテゴリ】現場の事例
【タイトル】地域名と築年数か品目を含める（例：「○○区・築25年のマンションで出た貴金属と楽器｜買取相談会の記録」）

{common_rules(posts)}"""


def build_prompt(dom, row, posts):
    return {"basic": prompt_basic, "area": prompt_area, "item": prompt_item, "case": prompt_case}[dom](row, posts)


# ---------- API ----------

def _post(payload):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("ANTHROPIC_API_KEY が設定されていません")
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(payload).encode(), headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        # 原因が分かるように、APIが返したエラー本文を出す（キーは出さない）
        detail = e.read().decode("utf-8", "replace")[:600]
        raise RuntimeError(f"HTTP {e.code}: {detail}") from None


def ping():
    """記事は作らず、APIにつながるかだけ確認する（数円未満）。"""
    data = _post({"model": MODEL, "max_tokens": 16, "messages": [{"role": "user", "content": "OKとだけ返してください"}]})
    print("API接続OK:", MODEL, "/", "".join(b.get("text", "") for b in data["content"]).strip())


ARTICLE_TOOL = {
    "name": "save_article",
    "description": "書き上げた記事を保存する",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string"}, "description": {"type": "string"}, "slug": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "body_md": {"type": "string"},
            "faq": {"type": "array", "items": {"type": "object", "properties": {"q": {"type": "string"}, "a": {"type": "string"}}, "required": ["q", "a"]}},
        },
        "required": ["title", "description", "slug", "tags", "body_md", "faq"],
    },
}


def call_claude(prompt):
    # 記事は save_article ツールの引数（JSON）として受け取る。本文中の記号でJSONが壊れて不採用になるのを防ぐ
    prompt = prompt + "\n\n【重要】記事は文章で返さず、必ず save_article ツールを1回だけ呼び出して渡してください。項目は上の出力形式と同じです。"
    data = _post({"model": MODEL, "max_tokens": 12000, "messages": [{"role": "user", "content": prompt}],
                  "tools": [ARTICLE_TOOL]})
    for b in data["content"]:
        if b.get("type") == "tool_use":
            return b["input"]
    text = "".join(b.get("text", "") for b in data["content"])
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0))


# ---------- 品質チェック ----------

def check(article, dom, row, posts):
    problems = []
    body = article.get("body_md", "")
    full = " ".join([article.get("title", ""), article.get("description", ""), body] + [x.get("q", "") + x.get("a", "") for x in article.get("faq", [])])
    problems += consistency.check_text(full, SITE)
    if len(body) < MIN_CHARS[dom]: problems.append(f"本文が短い（{len(body)}文字）")
    if body.count("## ") < 4: problems.append("## 見出しが4つ未満")
    if len(article.get("title", "")) > 34: problems.append("タイトルが長い")
    if not (100 <= len(article.get("description", "")) <= 140): problems.append("descriptionの長さ")
    if not re.fullmatch(r"[a-z0-9-]{3,40}", article.get("slug", "")): problems.append("slugの形式")
    for w in BANNED:
        if w in body or w in article.get("title", ""): problems.append(f"誇張表現: {w}")
    if dom in ("basic", "area", "item"):
        kw_head = row["keyword"].split()[0]
        if kw_head not in article.get("title", "") and kw_head not in body[:400]: problems.append("キーワードが冒頭にない")
    if dom == "area":
        place = row["keyword"].rsplit(" ", 1)[0].split()[-1]
        if body.count(place) < 3: problems.append("地域名が本文にほとんど出てこない")
    if dom == "case":
        if row["area"] not in body: problems.append("事例の地域名が本文にない")
        if "万円" not in body: problems.append("買取額の記述がない")
    if len(article.get("faq", [])) < 3: problems.append("FAQが3問未満")
    for p in posts:
        if p["slug"] == article.get("slug"): problems.append("slugが既存記事と重複")
        if p["title"] == article.get("title"): problems.append("タイトルが既存記事と重複")
    return problems


def write_post(article, dom, row, draft=False):
    today = datetime.date.today().isoformat()
    category = {"case": "jirei", "item": "kaitori", "area": "area"}.get(dom, row.get("category", "ihin"))
    fm = {
        "title": article["title"], "description": article["description"], "slug": article["slug"],
        "date": today, "category": category, "domain": dom,
        "keyword": row.get("keyword", f"事例 {row.get('area', '')}"), "tags": article.get("tags", []),
        "faq": article.get("faq", []), "author": SITE["author"]["name"],
    }
    text = "---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False) + "---\n\n" + article["body_md"].strip() + "\n"
    folder = DRAFTS if draft else POSTS
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{today}-{article['slug']}.md"
    path.write_text(text, encoding="utf-8")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=int(SITE.get("posts_per_run", 3)))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ping", action="store_true", help="記事は作らずAPI接続だけ確認")
    ap.add_argument("--cases", default="", help="事例IDを指定して生成（例 c001,c002）")
    args = ap.parse_args()
    if args.ping:
        ping(); return
    kws = load_csv(KW)
    cases = load_csv(CASES) if CASES.exists() else []
    posts = existing_posts()
    if args.cases:
        ids = [x.strip() for x in args.cases.split(",") if x.strip()]
        targets = [("case", c) for c in cases if c["id"] in ids]
    else:
        targets = pick_targets(args.count, kws, cases, posts)
    if not targets:
        print("生成できる対象がありません（keywords.csv / cases.csv の todo を確認）"); return
    if args.dry_run:
        for dom, r in targets:
            print(f"[{dom}] {r.get('keyword') or ('事例 ' + r.get('area', ''))} — {r.get('angle') or r.get('takeaway', '')}")
        return
    done = 0
    for dom, row in targets:
        label = row.get("keyword") or f"事例 {row.get('area')}"
        print(f"生成[{dom}]: {label}")
        article = None
        for attempt in range(2):
            try:
                cand = call_claude(build_prompt(dom, row, posts))
            except Exception as e:
                print(f"  APIエラー: {e}"); continue
            problems = check(cand, dom, row, posts)
            if not problems:
                article = cand; break
            print(f"  品質チェックで差し戻し（{attempt+1}回目）: {', '.join(problems)}")
        if not article:
            row["status"] = "failed"; continue
        path = write_post(article, dom, row, draft=bool(SITE.get("review_before_publish")))
        row["status"] = "draft" if SITE.get("review_before_publish") else "done"
        row["slug"] = article["slug"]
        posts.append({"title": article["title"], "slug": article["slug"], "category": row.get("category", ""), "domain": dom})
        print(f"  保存: {path.name}（{len(article['body_md'])}文字）")
        done += 1
    save_csv(KW, kws, KW_FIELDS)
    if cases: save_csv(CASES, cases, CASE_FIELDS)
    print(f"完了: {done}本")


if __name__ == "__main__":
    main()
