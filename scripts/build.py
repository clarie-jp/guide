#!/usr/bin/env python3
"""content/posts の Markdown から静的サイトを dist/ に生成する。
記事ページ・トップ・カテゴリ・タグ・著者・sitemap.xml・feed.xml・robots.txt を作る。
"""
import re, json, shutil, pathlib, datetime, html
import yaml, markdown
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import consistency

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE = yaml.safe_load((ROOT / "site.yaml").read_text(encoding="utf-8"))
POSTS = ROOT / "content" / "posts"
DIST = ROOT / "dist"
TPL = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
BASE = SITE["base_url"].rstrip("/")
CATS = SITE["categories"]
MD = markdown.Markdown(extensions=["tables", "toc", "sane_lists"], extension_configs={"toc": {"toc_depth": "2-3"}})


IMG_DIR = ROOT / "static" / "img"


def pick_image(p):
    """記事に合う写真を static/img/<category>/ から選ぶ。front matter に image があればそれを優先。
    無ければカテゴリの写真を slug のハッシュで固定的に割り当て、カテゴリに無ければ common から。"""
    if p.get("image"):
        return p["image"]
    for folder in (p.get("category", ""), "common"):
        files = sorted(x for x in (IMG_DIR / folder).glob("*") if x.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")) if (IMG_DIR / folder).exists() else []
        if files:
            return f"img/{folder}/{files[sum(map(ord, p['slug'])) % len(files)].name}"
    return ""


def parse(path):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    fm = yaml.safe_load(m.group(1)); body = m.group(2)
    fm["body_md"] = body
    fm["words"] = len(re.sub(r"\s", "", body))
    fm["date"] = str(fm["date"])
    return fm


def render_md(body):
    MD.reset()
    h = MD.convert(body)
    toc = MD.toc if getattr(MD, "toc_tokens", None) else ""
    return h, toc


def page(title, desc, body_html, url, extra_head="", kind="WebPage", og_type="website", image=""):
    a = SITE["author"]
    og = f'<meta property="og:image" content="{BASE}/{image}"><meta name="twitter:card" content="summary_large_image">' if image else ""
    extra_head = og + extra_head
    return (TPL.replace("{{title}}", html.escape(title)).replace("{{description}}", html.escape(desc))
            .replace("{{site_name}}", SITE["site_name"]).replace("{{canonical}}", url).replace("{{base}}", BASE)
            .replace("{{brand_url}}", SITE["brand_url"]).replace("{{contact_url}}", SITE["contact_url"])
            .replace("{{tel_raw}}", SITE["tel"].replace("-", "")).replace("{{tel}}", SITE["tel"]).replace("{{tel_hours}}", SITE["tel_hours"]).replace("{{test_url}}", SITE["test_url"])
            .replace("{{company}}", SITE["company"]).replace("{{license}}", SITE["license"]).replace("{{area}}", SITE["area"])
            .replace("{{author_name}}", a["name"]).replace("{{author_title}}", a["title"]).replace("{{author_bio}}", a["bio"])
            .replace("{{year}}", str(datetime.date.today().year)).replace("{{og_type}}", og_type)
            .replace("{{nav}}", nav_html()).replace("{{extra_head}}", extra_head).replace("{{body}}", body_html))


def nav_html():
    return "".join(f'<a href="{BASE}/category/{k}/">{v}</a>' for k, v in CATS.items())


def cta_html():
    return f"""<aside class="cta">
<p class="cta-h">片付けと買取を、ひとつの窓口で</p>
<p>クラリエは、生前整理・遺品整理の作業と、貴金属・ブランド品・骨董・楽器などの買取を同じ担当が行います。買取額は整理費用から差し引けるので、持ち出しを抑えられます。出張査定・お見積りは無料です（{SITE['area']}）。</p>
<p class="cta-btns"><a class="btn" href="tel:{SITE['tel'].replace('-', '')}">電話で相談 {SITE['tel']}</a><a class="btn ghost" href="{SITE['contact_url']}">フォームで無料見積り</a><a class="btn ghost" href="{BASE}/#ryokin">費用の目安を見る</a></p>
<p class="cta-sub">まず自分の準備度を知りたい方は <a href="{SITE['test_url']}">生前整理・相続・遺品整理 理解度テスト（無料・3分）</a></p>
</aside>"""


def is_new(p, days=7):
    """公開から7日以内なら NEW 表示。"""
    today = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)).date()
    try:
        return (today - datetime.date.fromisoformat(str(p["date"]))).days < days
    except ValueError:
        return False


def card(p):
    img = pick_image(p)
    thumb = f'<img src="{BASE}/{img}" alt="" loading="lazy">' if img else ""
    new = '<span class="new">NEW</span>' if is_new(p) else ""
    return f"""<li class="card"><a href="{BASE}/posts/{p['slug']}/">{thumb}<span class="cat">{new}{CATS.get(p['category'], p['category'])}</span><span class="t">{html.escape(p['title'])}</span><span class="d">{html.escape(p['description'][:70])}…</span><time>{p['date']}</time></a></li>"""


def related(p, posts, n=4):
    same = [q for q in posts if q["slug"] != p["slug"] and q["category"] == p["category"]]
    other = [q for q in posts if q["slug"] != p["slug"] and q["category"] != p["category"]]
    return (same + other)[:n]


def post_html(p, posts):
    a = SITE["author"]
    body, toc = render_md(p["body_md"])
    url = f"{BASE}/posts/{p['slug']}/"
    faq = p.get("faq") or []
    faq_html = ""
    if faq:
        faq_html = "<h2 id=\"faq\">よくある質問</h2>" + "".join(f"<details class=\"faq\"><summary>{html.escape(f['q'])}</summary><p>{html.escape(f['a'])}</p></details>" for f in faq)
    ld = [
        {"@context": "https://schema.org", "@type": "Article", "headline": p["title"], "description": p["description"],
         "datePublished": p["date"], "dateModified": p.get("updated", p["date"]), "mainEntityOfPage": url, "inLanguage": "ja",
         "author": {"@type": "Person", "name": a["name"], "jobTitle": a["title"], "url": f"{BASE}/author/"},
         "publisher": {"@type": "Organization", "name": SITE["company"], "url": SITE["brand_url"]}},
        {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "ホーム", "item": BASE + "/"},
            {"@type": "ListItem", "position": 2, "name": CATS.get(p["category"], p["category"]), "item": f"{BASE}/category/{p['category']}/"},
            {"@type": "ListItem", "position": 3, "name": p["title"], "item": url}]},
    ]
    if faq:
        ld.append({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": f["q"], "acceptedAnswer": {"@type": "Answer", "text": f["a"]}} for f in faq]})
    extra = "".join(f'<script type="application/ld+json">{json.dumps(x, ensure_ascii=False)}</script>' for x in ld)
    img = pick_image(p)
    if img: ld[0]["image"] = f"{BASE}/{img}"
    hero = f'<img class="hero" src="{BASE}/{img}" alt="{html.escape(p["title"])}" width="1200" height="800" loading="eager">' if img else ""
    rel = "".join(card(q) for q in related(p, posts))
    tags = "".join(f'<a class="tag" href="{BASE}/tag/{html.escape(t)}/">#{html.escape(t)}</a>' for t in p.get("tags", []))
    inner = f"""<article>
<p class="crumb"><a href="{BASE}/">ホーム</a> › <a href="{BASE}/category/{p['category']}/">{CATS.get(p['category'], p['category'])}</a></p>
<h1>{html.escape(p['title'])}</h1>
<p class="meta">公開 <time datetime="{p['date']}">{p['date']}</time>{('　更新 ' + str(p['updated'])) if p.get('updated') else ''}　｜　執筆 <a href="{BASE}/author/">{a['name']}（{a['title']}）</a>　｜　約{max(1, p['words'] // 500)}分で読めます</p>
<p class="lead">{html.escape(p['description'])}</p>
{hero}
{'<nav class="toc"><p>この記事の内容</p>' + toc + '</nav>' if toc else ''}
<div class="body">{body}</div>
{faq_html}
{cta_html()}
<div class="author-box"><p class="an">この記事を書いた人</p><p><b>{a['name']}</b>　{a['title']}</p><p>{a['bio']}</p><p class="lic">{SITE['company']}　{SITE['license']}</p></div>
<p class="tags">{tags}</p>
</article>
<section class="rel"><h2>あわせて読みたい</h2><ul class="cards">{rel}</ul></section>"""
    return page(p["title"], p["description"], inner, url, extra, og_type="article", image=img)


def gbp_text(p):
    """Googleビジネスプロフィールの投稿文。
    Googleの投稿ポリシーで却下されないよう、本文に電話番号・URLは書かない
    （リンクは投稿の「詳細」ボタン、電話はプロフィールの電話ボタンで案内される）。"""
    body = re.sub(r"[#*`>|_]+", " ", p["body_md"])
    body = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", body)
    body = re.sub(r"https?://\S+", "", body)
    lead = re.split(r"\n\s*\n", body.strip())[0].strip()
    lead = re.sub(r"\s+", " ", lead)[:300]
    lead = re.sub(r"0\d{1,4}-\d{1,4}-\d{3,4}", "", lead)
    t = (f"【{p['title']}】\n\n{lead}\n\n"
         "続きは「詳細」から記事でご覧いただけます。\n\n"
         f"生前整理・遺品整理・買取のご相談は、クラリエへ。出張査定・お見積り無料、土日も受付しています。対応エリアは{SITE['area']}です。")
    return t[:1400]


def gbp_image(p):
    """マップ投稿に付ける画像。記事の写真があればそれ、無ければカテゴリのブランド画像。"""
    img = pick_image(p)
    if img:
        return f"{BASE}/{img}"
    cat = p.get("category", "ihin")
    if (ROOT / "static" / "img" / "gbp" / f"{cat}.jpg").exists():
        return f"{BASE}/img/gbp/{cat}.jpg"
    return f"{BASE}/img/gbp/ihin.jpg"


def quiz_html(posts):
    """30秒診断：3問を選ぶと、状況に合った進め方・最初の一歩・先に読む記事を出す。静的・匿名。"""
    def picks(cat, n=2):
        return [{"t": p["title"], "u": f"{BASE}/posts/{p['slug']}/"} for p in posts if p["category"] == cat][:n]
    data = {"articles": {k: picks(k) for k in CATS}, "tel": SITE["tel"], "tel_raw": SITE["tel"].replace("-", ""),
            "contact": SITE["contact_url"], "test": SITE["test_url"], "base": BASE}
    tel_raw = data["tel_raw"]
    ic = {  # 選択肢の小さなアイコン（線画）
        "home": '<svg viewBox="0 0 32 32"><path d="M4 16 16 5l12 11M8 14v12h16V14M13 26v-7h6v7"/></svg>',
        "flower": '<svg viewBox="0 0 32 32"><circle cx="16" cy="12" r="4"/><path d="M16 16v11M16 5v3M9 9l2 2M23 9l-2 2M8 15h3M21 15h3M11 27h10"/></svg>',
        "person": '<svg viewBox="0 0 32 32"><circle cx="16" cy="10" r="5"/><path d="M6 28c1-6 5-9 10-9s9 3 10 9"/></svg>',
        "clock1": '<svg viewBox="0 0 32 32"><circle cx="16" cy="16" r="11"/><path d="M16 9v7l5 3"/></svg>',
        "clock2": '<svg viewBox="0 0 32 32"><rect x="5" y="7" width="22" height="20" rx="2"/><path d="M5 13h22M11 4v6M21 4v6"/></svg>',
        "cloud": '<svg viewBox="0 0 32 32"><path d="M9 25a6 6 0 0 1-1-11.9A8 8 0 0 1 23.5 12 5.5 5.5 0 0 1 24 25z"/></svg>',
        "yen": '<svg viewBox="0 0 32 32"><path d="M9 6l7 10 7-10M16 16v11M10 19h12M10 23h12"/></svg>',
        "steps": '<svg viewBox="0 0 32 32"><path d="M5 27h7v-6h7v-6h7V8"/></svg>',
        "family": '<svg viewBox="0 0 32 32"><circle cx="11" cy="11" r="4"/><circle cx="22" cy="12" r="3.2"/><path d="M3 27c1-5 4-8 8-8s7 3 8 8M17 26c.6-3.5 2.6-5.6 5.5-5.6S28 22.5 29 26"/></svg>',
        "doc": '<svg viewBox="0 0 32 32"><path d="M8 4h11l6 6v18H8zM19 4v6h6M12 16h9M12 21h9"/></svg>',
    }
    def opt(v, icon, label, sub):
        return f'<button type="button" data-v="{v}"><span class="ico">{ic[icon]}</span><span class="lb">{label}</span><span class="sb">{sub}</span></button>'
    q1 = opt("parent", "home", "親の家", "親は元気。先々のために") + opt("bereaved", "flower", "亡くなった家族の家", "遺品の整理と手続き") + opt("self", "person", "自分の身辺整理", "元気なうちに自分で")
    q2 = opt("soon", "clock1", "1か月以内", "退去・売却など期限がある") + opt("half", "clock2", "半年くらい", "急がないが進めたい") + opt("undecided", "cloud", "まだ決めていない", "まず知りたい段階")
    q3 = opt("cost", "yen", "費用はいくら？", "見積りの見方、安くする方法") + opt("how", "steps", "何から始める？", "手順と順番") + opt("family", "family", "家族との話し合い", "切り出し方、もめない進め方") + opt("house", "doc", "家・相続のこと", "売る・残す、手続きの順番")
    return f"""<section class="sec shindan" id="shindan">
<div class="quiz" id="quiz">
 <div class="qhead">
  <p class="qeyebrow">30秒診断・無料・入力は残りません</p>
  <h2>3つ選ぶだけで、<br class="sp">あなたに合う進め方がわかります</h2>
  <p class="qlead">費用の目安、最初の一歩、先に読むべき記事を、その場でお出しします。</p>
  <div class="qtest"><p class="qtest-t">もっと詳しく知りたい方は</p><a class="btn ghost light" href="{SITE['test_url']}">理解度テストを受ける（無料・3分）<small>生前整理・遺品整理の基礎知識をチェック</small></a></div>
 </div>
 <div class="qbody">
  <div class="qbar"><span class="qnum">質問 <b>1</b> / 3</span><span class="qdots"><i class="on"></i><i></i><i></i></span><button type="button" class="qback" hidden>← 戻る</button></div>
  <div class="qstep" data-q="1"><p class="qq">どなたの片付けですか？</p><div class="qopts">{q1}</div></div>
  <div class="qstep" data-q="2" hidden><p class="qq">いつまでに終えたいですか？</p><div class="qopts">{q2}</div></div>
  <div class="qstep" data-q="3" hidden><p class="qq">いちばん気になることは？</p><div class="qopts four">{q3}</div></div>
  <div class="qresult" hidden>
   <p class="qr-k">診断結果</p>
   <p class="qr-h"></p>
   <p class="qr-b"></p>
   <div class="qr-grid">
    <div class="qr-box"><p class="qr-t">最初の一歩</p><ol class="qr-steps"></ol></div>
    <div class="qr-box"><p class="qr-t">先に読む記事</p><ul class="qr-list"></ul></div>
   </div>
   <div class="qr-cta">
    <p class="qr-cta-t">読む前に聞いてしまったほうが早いときは</p>
    <p class="cta-btns"><a class="btn" href="tel:{tel_raw}">電話で相談する {SITE['tel']}</a><a class="btn navy" href="{SITE['contact_url']}">フォームで無料見積り</a><a class="btn ghost light" href="{SITE['test_url']}">理解度テストを受ける（3分）</a></p>
    <p class="qr-note">{html.escape(SITE['tel_hours'])}。相談・見積りは無料、お断りいただいても費用はかかりません。</p>
   </div>
   <button type="button" class="qagain">もう一度、選び直す</button>
  </div>
 </div>
</div>
<script>
(function(){{
var D={json.dumps(data, ensure_ascii=False)};
var A={{}};var root=document.getElementById('quiz');if(!root)return;
var steps=root.querySelectorAll('.qstep'),res=root.querySelector('.qresult'),dots=root.querySelectorAll('.qdots i'),num=root.querySelector('.qnum b'),back=root.querySelector('.qback'),bar=root.querySelector('.qbar');
var cur=1;
function show(n){{cur=n;steps.forEach(function(s){{s.hidden=(+s.dataset.q!==n);}});res.hidden=true;bar.hidden=false;num.textContent=n;dots.forEach(function(d,i){{d.className=i<n-1?'done':(i===n-1?'on':'');}});back.hidden=(n===1);
 steps.forEach(function(s){{s.querySelectorAll('button').forEach(function(b){{b.classList.toggle('sel',A['q'+s.dataset.q]===b.dataset.v);}});}});}}
var H={{
 parent:{{h:'親が元気なうちに始める「生前整理」が向いています',b:'物より先に、通帳・保険・連絡先などの「情報」から整えると、家族の負担が大きく減ります。価値のある物は、捨てる前に一度査定を。',
  steps:['親に「困ったときのために、大事な物の場所だけ教えて」と切り出す','通帳・保険証券・権利証など書類の置き場所を1か所にまとめる','使っていない貴金属・着物・骨董は、処分の前に無料査定へ'],cats:['seizen','jikka']}},
 bereaved:{{h:'期限と手続きを意識して進める「遺品整理」です',b:'先に貴重品と書類を確認し、相続放棄の可能性があれば処分の前に専門家へ。見積りは「買取額を差し引いた金額」で比べてください。',
  steps:['通帳・印鑑・保険・年金の書類、鍵、現金を先に確保する','相続放棄の可能性があるなら、物を処分する前に司法書士・弁護士へ','整理費用と買取額を同じ見積書で出す業者に相見積りを取る'],cats:['ihin','souzoku']}},
 self:{{h:'自分のペースで進める「身辺整理」です',b:'残す・手放す・託すの3つに分け、託す物は査定を受けてから行き先を決めると無駄がありません。',
  steps:['1日1引き出し。小さく始めて、止まらないことを優先する','写真・手紙など「残す物」の箱を先に決める','手放す物は、捨てる前に値段が付くかだけ確認する'],cats:['seizen','kaitori']}}
}};
var T={{soon:'期限が近いので、見積りを先に取り、仕分けと搬出を同時に進める段取りが向いています。',half:'半年あれば、貴重品の確認→家族で仕分け→業者に搬出、の順で費用を抑えられます。',undecided:'まずは費用の目安と手順を知るところから。急いで決める必要はありません。'}};
var C={{cost:'hiyou',how:'ihin',family:'seizen',house:'jikka'}};
function finish(){{steps.forEach(function(s){{s.hidden=true;}});bar.hidden=true;
 var h=H[A.q1]||H.parent;root.querySelector('.qr-h').textContent=h.h;root.querySelector('.qr-b').textContent=h.b+' '+(T[A.q2]||'');
 root.querySelector('.qr-steps').innerHTML=h.steps.map(function(t){{return '<li>'+t+'</li>';}}).join('');
 var cats=[C[A.q3]].concat(h.cats);var seen={{}};var list=[];cats.forEach(function(c){{(D.articles[c]||[]).forEach(function(a){{if(!seen[a.u]&&list.length<3){{seen[a.u]=1;list.push(a);}}}});}});
 root.querySelector('.qr-list').innerHTML=list.map(function(a){{return '<li><a href="'+a.u+'">'+a.t+'</a></li>';}}).join('')||'<li>記事を準備しています。まずはお電話でご相談ください。</li>';
 res.hidden=false;root.scrollIntoView({{behavior:'smooth',block:'start'}});
 if(window.gtag)gtag('event','shindan_complete',{{q1:A.q1,q2:A.q2,q3:A.q3}});}}
root.addEventListener('click',function(e){{var b=e.target.closest('button');if(!b)return;
 if(b.classList.contains('qagain')){{A={{}};show(1);root.scrollIntoView({{behavior:'smooth',block:'start'}});return;}}
 if(b.classList.contains('qback')){{if(cur>1)show(cur-1);return;}}
 var st=b.closest('.qstep');if(!st)return;var n=+st.dataset.q;A['q'+n]=b.dataset.v;
 b.classList.add('sel');
 setTimeout(function(){{if(n<3)show(n+1);else finish();}},180);
}});
}})();
</script></section>"""


def lp_html(posts):
    """トップページ（LP）。文言は site.yaml の lp: から。"""
    L = SITE["lp"]; tel_raw = SITE["tel"].replace("-", "")
    def esc(x): return html.escape(str(x))
    # ヒーロー右：はじめに読む3本（基礎カテゴリ優先）
    first = [p for p in posts if p.get("category") in ("hiyou", "ihin", "seizen")][:3] or posts[:3]
    side = "".join(f'<li><a href="{BASE}/posts/{p["slug"]}/">{esc(p["title"])}<small>{CATS.get(p["category"], "")}・約{max(1, p["words"] // 500)}分</small></a></li>' for p in first)
    hero_side = f'<aside class="hero-side"><p class="hs-t">はじめて読む方へ</p><p class="hs-s">まず読んでほしい3本。タップして読めます</p><ol>{side}</ol><a class="hs-more" href="{BASE}/#articles">記事をすべて見る →</a></aside>' if first else ""
    cta_btns = f'<p class="cta-btns"><a class="btn" href="tel:{tel_raw}">電話で相談する {SITE["tel"]}</a><a class="btn ghost" href="{SITE["contact_url"]}">フォームで無料見積り</a></p>'
    lamp = '<svg class="lamp" viewBox="0 0 64 64" aria-hidden="true"><path d="M32 6c9 12 14 19 14 27a14 14 0 0 1-28 0c0-8 5-15 14-27z" fill="#C9A961"/><path d="M32 18c4.5 6 7 10 7 14a7 7 0 0 1-14 0c0-4 2.5-8 7-14z" fill="#fff"/><rect x="23" y="52" width="18" height="5" rx="2.5" fill="#C9A961"/></svg>'
    ticons = [
        '<svg viewBox="0 0 32 32"><path d="M16 3l10 4v8c0 7-4.5 11.5-10 14C10.5 26.5 6 22 6 15V7z"/><path d="M11.5 16l3 3 6-7"/></svg>',
        '<svg viewBox="0 0 32 32"><circle cx="16" cy="11" r="6"/><path d="M12 16l-2 12 6-3.5 6 3.5-2-12"/></svg>',
        '<svg viewBox="0 0 32 32"><path d="M4 26h24M7 26V14l9-7 9 7v12M13 26v-7h6v7"/></svg>',
        '<svg viewBox="0 0 32 32"><rect x="6" y="5" width="20" height="22" rx="2"/><path d="M11 12h10M11 17h10M11 22h6"/></svg>',
        '<svg viewBox="0 0 32 32"><rect x="7" y="14" width="18" height="13" rx="2"/><path d="M11 14V10a5 5 0 0 1 10 0v4M16 19v4"/></svg>',
    ]
    trust = "".join(f'<li><span class="ti">{ticons[i % len(ticons)]}</span><b>{esc(t[0])}</b><span class="td">{esc(t[1])}</span></li>' for i, t in enumerate(L.get("trust", [])))
    trust_bar = f'<div class="trust-wrap"><p class="trust-t">安心してご相談いただくために</p><ul class="trust">{trust}</ul></div>' if trust else ""
    hero = f"""<section class="lp-hero"><div class="in"><div>{lamp}<h1>{esc(L["hero_title"])}</h1><p>{esc(L["hero_sub"])}</p>{cta_btns}<p class="note">{esc(SITE["tel_hours"])}／出張査定・お見積り無料／対応エリア {esc(SITE["area"])}</p></div>{hero_side}</div>{trust_bar}</section>"""
    # 悩み別：各カテゴリの記事3本
    pains = ""
    for x in L["pains"]:
        ps = [p for p in posts if p["category"] == x["category"]][:3]
        items = "".join(f'<li><a href="{BASE}/posts/{p["slug"]}/">{esc(p["title"])}</a></li>' for p in ps) or '<li><a href="' + f'{BASE}/category/{x["category"]}/' + '">記事を準備しています</a></li>'
        pains += f'<li><p class="q">{esc(x["title"])}</p><p class="d">{esc(x["desc"])}</p><ul>{items}</ul><a class="more" href="{BASE}/category/{x["category"]}/">{CATS.get(x["category"], "")}の記事をすべて見る</a></li>'
    before = "".join(f"<li>{esc(t)}</li>" for t in L["before"]); after = "".join(f"<li>{esc(t)}</li>" for t in L["after"])
    price = "".join(f'<li><p class="pl">{esc(r[0])}</p><p class="pv">{esc(r[1])}<small>万円〜</small></p><p class="pd">{esc(r[2])}</p></li>' for r in L["pricing"]["rows"])
    steps = "".join(f"<li><b>{esc(x[0])}</b><p>{esc(x[1])}</p></li>" for x in L["steps"])
    faq = "".join(f'<details class="faq"><summary>{esc(f["q"])}</summary><p>{esc(f["a"])}</p></details>' for f in L["faq"])
    cases = [p for p in posts if p.get("category") == "jirei"][:3]
    case_sec = f'<section class="sec" id="jirei"><div class="sec-h"><h2>現場の記録</h2></div><p class="sec-sub">マンションの買取相談会や、ご自宅の整理で実際にあったことを、地域・築年・持ち込まれた品とともに記録しています。</p><ul class="cards">{"".join(card(p) for p in cases)}</ul></section>' if cases else ""
    cat_blocks = "".join(f'<li><a href="{BASE}/category/{k}/"><b>{v}</b><span>{len([p for p in posts if p["category"] == k])}記事</span></a></li>' for k, v in CATS.items())
    return f"""<div class="lp">
{hero}
<section class="sec" id="new"><div class="sec-h"><h2>新着記事</h2></div><ul class="cards">{"".join(card(p) for p in posts[:3])}</ul><p class="more-link"><a href="{BASE}/#list">記事一覧を見る</a></p></section>
<section class="sec"><div class="sec-h"><h2>いま困っていることから</h2></div><ul class="pains">{pains}</ul></section>
{quiz_html(posts)}
<section class="sec" id="tokucho"><div class="sec-h"><h2>窓口は、ひとつだけ</h2></div><p class="sec-sub">クラリエは買取を先に勧めません。まず整理の見積りを出し、買取額を費用から差し引く。お客さまが損をしない順番で進めます。</p>
<div class="compare"><div class="col before"><h3>これまでの実家じまい</h3><ul>{before}</ul></div><div class="arrow" aria-hidden="true">→</div><div class="col after"><h3>クラリエなら</h3><ul>{after}</ul></div></div></section>
<section class="sec" id="ryokin"><div class="sec-h"><h2>費用の目安</h2></div><ul class="price">{price}</ul><p class="pnote">{esc(L["pricing"]["note"])}</p></section>
<section class="sec" id="nagare"><div class="sec-h"><h2>お電話から、解決まで</h2></div><ol class="steps">{steps}</ol></section>
{case_sec}
<section class="sec" id="faq"><div class="sec-h"><h2>よくあるご質問</h2></div>{faq}</section>
<section class="contact" id="contact"><h2>まず、状況を聞かせてください</h2><p>間取り・時期・地域が分かれば、電話で概算をお伝えできます。見積り後にお断りいただいても費用はかかりません。</p><a class="tel" href="tel:{tel_raw}">{SITE["tel"]}</a><p class="hours">{esc(SITE["tel_hours"])}</p><p class="cta-btns"><a class="btn" href="{SITE["contact_url"]}">フォームで無料見積りを頼む</a><a class="btn ghost" href="{SITE["test_url"]}">理解度テストを受ける（無料・3分）</a></p></section>
<section class="sec" id="articles"><div class="sec-h"><h2>テーマから記事を探す</h2></div><ul class="catgrid">{cat_blocks}</ul></section>
<section class="sec" id="list"><div class="sec-h"><h2>記事一覧</h2></div><ul class="cards">{"".join(card(p) for p in posts[:12])}</ul></section>
</div>"""


def listing(title, desc, posts, url, intro=""):
    cards = "".join(card(p) for p in posts)
    inner = f"<h1>{html.escape(title)}</h1><p class=\"lead\">{html.escape(desc)}</p>{intro}<ul class=\"cards\">{cards}</ul>{cta_html()}"
    return page(title, desc, inner, url)


def main():
    if DIST.exists(): shutil.rmtree(DIST)
    DIST.mkdir()
    # 公開日が未来の記事はまだ出さない（毎朝のビルドで日付が来たものから公開される）
    today = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)).date().isoformat()
    posts = sorted([x for x in (parse(p) for p in POSTS.glob("*.md")) if str(x["date"]) <= today], key=lambda x: x["date"], reverse=True)
    # 整合性チェック：料金・電話番号などが site.yaml（＝LP）と違う記事があれば公開しない
    bad = []
    for p in posts:
        txt = " ".join([p["title"], p["description"], p["body_md"]] + [f.get("q", "") + f.get("a", "") for f in p.get("faq", [])])
        bad += [f"{p['slug']}: {x}" for x in consistency.check_text(txt, SITE)]
    if bad:
        sys.exit("整合性チェックで止めました（LPと記事の内容が食い違っています）:\n" + "\n".join(bad))
    for p in posts:
        d = DIST / "posts" / p["slug"]; d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(post_html(p, posts), encoding="utf-8")
    # トップ
    a = SITE["author"]
    ld = {"@context": "https://schema.org", "@type": "LocalBusiness", "name": "クラリエ（" + SITE["company"] + "）",
          "url": SITE["brand_url"], "telephone": SITE["tel"], "areaServed": SITE["area"],
          "address": {"@type": "PostalAddress", "addressRegion": "神奈川県", "addressLocality": "横浜市西区", "streetAddress": "みなとみらい2-2-1 ランドマークプラザ5階"},
          "description": "生前整理・遺品整理と買取をひとつの窓口で行うサービス"}
    top = page("生前整理・遺品整理・実家じまいの費用と手順", SITE["tagline"], lp_html(posts), BASE + "/", f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>')
    (DIST / "index.html").write_text(top, encoding="utf-8")
    # カテゴリ・タグ・著者
    for k, v in CATS.items():
        d = DIST / "category" / k; d.mkdir(parents=True, exist_ok=True)
        ps = [p for p in posts if p["category"] == k]
        (d / "index.html").write_text(listing(f"{v}の記事一覧", f"{v}に関する記事をまとめました。横浜・神奈川・東京で{v}を考えている方向けに、費用・手順・注意点を解説しています。", ps, f"{BASE}/category/{k}/"), encoding="utf-8")
    tags = {}
    for p in posts:
        for t in p.get("tags", []): tags.setdefault(t, []).append(p)
    for t, ps in tags.items():
        d = DIST / "tag" / t; d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(listing(f"#{t} の記事", f"{t}に関する記事の一覧です。", ps, f"{BASE}/tag/{t}/"), encoding="utf-8")
    d = DIST / "author"; d.mkdir(exist_ok=True)
    (d / "index.html").write_text(page(f"{a['name']}（{a['title']}）", a["bio"], f"<h1>{a['name']}</h1><p class=\"lead\">{a['title']}</p><p>{a['bio']}</p><p>{SITE['company']}　{SITE['license']}</p><h2>執筆記事</h2><ul class=\"cards\">{''.join(card(p) for p in posts)}</ul>", f"{BASE}/author/"), encoding="utf-8")
    # sitemap / feed / robots / static
    urls = [BASE + "/"] + [f"{BASE}/posts/{p['slug']}/" for p in posts] + [f"{BASE}/category/{k}/" for k in CATS] + [f"{BASE}/tag/{t}/" for t in tags] + [f"{BASE}/author/"]
    today = datetime.date.today().isoformat()
    (DIST / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(f"<url><loc>{u}</loc><lastmod>{today}</lastmod></url>" for u in urls) + "</urlset>", encoding="utf-8")
    items = "".join(f"<item><title>{html.escape(p['title'])}</title><link>{BASE}/posts/{p['slug']}/</link><guid>{BASE}/posts/{p['slug']}/</guid><pubDate>{p['date']}</pubDate><description>{html.escape(p['description'])}</description></item>" for p in posts[:50])
    (DIST / "feed.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{html.escape(SITE["site_name"])}</title><link>{BASE}/</link><description>{html.escape(SITE["tagline"])}</description>{items}</channel></rss>', encoding="utf-8")
    # Google ビジネスプロフィール投稿用フィード（Zapier/Make の「RSS→投稿」で使う。本文は1,500字以内の投稿文）
    gbp = "".join(f"<item><title>{html.escape(p['title'])}</title><link>{BASE}/posts/{p['slug']}/</link><guid>{BASE}/posts/{p['slug']}/</guid><pubDate>{p['date']}</pubDate><description>{html.escape(gbp_text(p))}</description><enclosure url=\"{gbp_image(p)}\" type=\"image/jpeg\" length=\"0\"/><image>{gbp_image(p)}</image></item>" for p in posts[:20])
    (DIST / "gbp.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>クラリエ 投稿用</title><link>{BASE}/</link><description>Googleビジネスプロフィール投稿用</description>{gbp}</channel></rss>', encoding="utf-8")
    (DIST / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n", encoding="utf-8")
    (DIST / ".nojekyll").write_text("", encoding="utf-8")
    for f in (ROOT / "static").iterdir():
        if f.is_dir(): shutil.copytree(f, DIST / f.name, dirs_exist_ok=True)
        else: shutil.copy(f, DIST / f.name)
    print(f"built {len(posts)} posts, {len(urls)} urls -> {DIST}")


if __name__ == "__main__":
    main()
