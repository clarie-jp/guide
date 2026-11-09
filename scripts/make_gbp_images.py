"""Googleマップ投稿用の写真が無い記事に付ける、カテゴリ別のブランド画像を作る（ローカルで実行してコミット）。
料金の文言は site.yaml から取るので、LPとずれない。"""
import glob, pathlib, yaml
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops
ROOT = pathlib.Path(__file__).resolve().parent.parent
S = yaml.safe_load(open(ROOT / "site.yaml", encoding="utf-8"))
serif = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"
sans = (sorted(glob.glob("/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc")) or [serif])[0]
NAVY, DEEP, GOLD, LG = (25, 34, 64), (9, 23, 63), (174, 145, 93), (230, 207, 156)
r0 = S["lp"]["pricing"]["rows"][0]
SUB = {"ihin": "遺品整理の費用・手順・業者の選び方", "seizen": "親が元気なうちに始める、生前整理", "jikka": "売る・残す・貸す。実家じまいの進め方",
       "souzoku": "相続と手続きの順番", "hiyou": f"{r0[0]} {r0[1]}万円〜／買取額を費用から差し引き", "kaitori": "捨てる前に、値段が付くか確かめる",
       "area": S["area"], "jirei": "現場で実際にあったこと"}
def jp(path, size):
    for i in range(12):
        try:
            f = ImageFont.truetype(path, size, index=i)
            if "JP" in f.getname()[0]: return f
        except OSError: break
    return ImageFont.truetype(path, size)
W, H = 1200, 900
out = ROOT / "static" / "img" / "gbp"; out.mkdir(parents=True, exist_ok=True)
for k, name in S["categories"].items():
    im = Image.new("RGB", (W, H)); d = ImageDraw.Draw(im)
    for y in range(H):
        t = y / H; d.line([(0, y), (W, y)], fill=tuple(int(NAVY[i] * (1 - t) + DEEP[i] * t) for i in range(3)))
    glow = Image.new("RGB", (W, H)); ImageDraw.Draw(glow).ellipse((760, -120, 1300, 420), fill=(60, 52, 36))
    im = ImageChops.add(im, glow.filter(ImageFilter.GaussianBlur(140))); d = ImageDraw.Draw(im)
    cx, cy = 150, 200
    d.polygon([(cx, cy - 70), (cx + 42, cy + 10), (cx - 42, cy + 10)], fill=GOLD); d.ellipse((cx - 42, cy - 25, cx + 42, cy + 55), fill=GOLD)
    d.polygon([(cx, cy - 30), (cx + 20, cy + 15), (cx - 20, cy + 15)], fill=(255, 255, 255)); d.ellipse((cx - 20, cy, cx + 20, cy + 38), fill=(255, 255, 255))
    d.rounded_rectangle((cx - 38, cy + 75, cx + 38, cy + 92), radius=8, fill=GOLD)
    d.text((240, 140), "クラリエ", font=jp(serif, 64), fill=(255, 255, 255))
    d.text((245, 225), "CLARIE　生前整理・遺品整理ガイド", font=jp(sans, 28), fill=LG)
    d.line((100, 340, 1100, 340), fill=(120, 110, 90), width=2)
    d.text((100, 420), name, font=jp(serif, 120), fill=(255, 255, 255))
    d.text((104, 600), SUB.get(k, ""), font=jp(sans, 40), fill=LG)
    d.text((100, 790), f"出張査定・お見積り無料　｜　土日も受付　｜　{S['area']}", font=jp(sans, 28), fill=(201, 207, 221))
    im.save(out / f"{k}.jpg", quality=88)
print("ok")
