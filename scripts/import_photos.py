#!/usr/bin/env python3
"""写真を取り込む：指定フォルダの画像を長辺1200pxのJPEGに縮小し、EXIF（位置情報など）を外して static/img/<category>/ に置く。
使い方: python3 scripts/import_photos.py <元フォルダ> <category: ihin|seizen|jikka|souzoku|hiyou|kaitori|area|common>
"""
import sys, pathlib
from PIL import Image, ImageOps
src, cat = pathlib.Path(sys.argv[1]), sys.argv[2]
dst = pathlib.Path(__file__).resolve().parent.parent / "static" / "img" / cat
dst.mkdir(parents=True, exist_ok=True)
n = 0
for f in sorted(src.iterdir()):
    if f.suffix.lower() not in (".jpg", ".jpeg", ".png", ".heic", ".webp"): continue
    try:
        im = ImageOps.exif_transpose(Image.open(f)).convert("RGB")
    except Exception as e:
        print("skip", f.name, e); continue
    im.thumbnail((1200, 1200))
    out = dst / f"{cat}-{n+1:02d}.jpg"
    im.save(out, "JPEG", quality=82, optimize=True)  # EXIFは付けない
    n += 1
print(f"{n}枚を {dst} に保存")
