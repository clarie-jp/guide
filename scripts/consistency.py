"""サイト全体の整合性チェック。

LP・記事・Googleマップ投稿で、料金や連絡先などの「公式情報」が食い違わないようにする。
公式情報の出どころは site.yaml だけ（lp.pricing / tel / tel_hours / area / lp.trust）。
- generate.py：生成した記事をこのチェックに通し、食い違いがあれば不採用にする
- build.py：公開前に全記事をチェックし、食い違いがあればビルドを止める（＝公開されない）
"""
import re

# 間取り・住まいの規模を指す語。これが近くにある金額は「整理費用」とみなす
ROOM_WORDS = r"(1R|1K|1DK|1LDK|2K|2DK|2LDK|3DK|3LDK|4LDK|LDK|DK|戸建|一戸建|間取り|部屋|家全体|ワンルーム)"


def official_facts(site):
    """site.yaml から公式情報を取り出す。"""
    rows = site["lp"]["pricing"]["rows"]  # [["1K〜1LDK", "5", "..."], ...]
    return {
        "prices": [(r[0], r[1]) for r in rows],
        "allowed_starts": {str(r[1]) for r in rows},
        "tel": site["tel"],
        "tel_hours": site["tel_hours"],
        "area": site["area"],
    }


def facts_for_prompt(site):
    """記事生成プロンプトに入れる「変えてはいけない公式情報」。"""
    f = official_facts(site)
    price = "、".join(f"{label} {start}万円〜" for label, start in f["prices"])
    return (
        "【クラリエの公式情報（このとおりに書く。別の金額や条件を作らない）】\n"
        f"- 整理費用の目安：{price}（2026年時点、買取額を差し引く前の金額）。間取り別の費用に触れるときは必ずこの金額を使い、"
        "「3〜8万円」のような別の幅や、業界相場として別の数字を書かない\n"
        "- 見積り：出張査定・お見積りは無料。お断りいただいても費用はかからない。訪問見積りで条件を確認し、作業後の追加請求はしない\n"
        f"- 電話：{f['tel']}（{f['tel_hours']}）\n"
        f"- 対応エリア：{f['area']}\n"
        "- 提携している管理会社・企業の名前は出さない"
    )


def check_text(text, site):
    """公式情報と食い違う箇所のリストを返す（空なら問題なし）。"""
    f = official_facts(site)
    problems = []
    # 1) 間取りの近くにある「N〜M万円」形式の幅（公式は「N万円〜」の書き方だけ）
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*万?円?\s*[〜~～ー-]\s*(\d+(?:\.\d+)?)\s*万円", text):
        ctx = text[max(0, m.start() - 40):m.start()]
        if re.search(ROOM_WORDS, ctx):
            problems.append(f"料金が公式と違う：「{m.group(0)}」（公式は {', '.join(f'{l} {s}万円〜' for l, s in f['prices'])}）")
    # 2) 間取りの近くにある「N万円〜」で、N が公式の金額にないもの
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*万円\s*[〜~～]", text):
        ctx = text[max(0, m.start() - 40):m.start()]
        if re.search(ROOM_WORDS, ctx) and m.group(1) not in f["allowed_starts"]:
            problems.append(f"料金の下限が公式と違う：「{m.group(0)}」")
    # 3) 電話番号
    for m in re.finditer(r"0\d{1,4}-\d{1,4}-\d{3,4}", text):
        if m.group(0) != f["tel"]:
            problems.append(f"電話番号が公式と違う：「{m.group(0)}」")
    # 4) 追加請求について「ある」と読める書き方
    if re.search(r"クラリエ[^。]{0,30}追加(料金|請求)が(かかります|発生します)", text):
        problems.append("クラリエの追加請求の扱いが公式（追加請求なし）と違う")
    return problems
