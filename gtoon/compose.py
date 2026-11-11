"""뉴스툰 합성 — 실사 배경 사진 + 진행자 캐릭터 + 한글 말풍선 / 표지 / 요약 페이지."""
from __future__ import annotations

import glob
import os
from datetime import datetime

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import characters

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BG = (255, 248, 238)
INK = (28, 30, 40)

_FONT_CANDIDATES = {
    "bold": [
        (os.path.join(ROOT, "assets/fonts/bold.ttf"), 0),
        ("/usr/share/fonts/truetype/nanum/NanumSquareRoundEB.ttf", 0),
        ("/usr/share/fonts/truetype/nanum/NanumGothicExtraBold.ttf", 0),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc", 1),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 1),
        ("C:/Windows/Fonts/malgunbd.ttf", 0),
    ],
    "regular": [
        (os.path.join(ROOT, "assets/fonts/regular.ttf"), 0),
        ("/usr/share/fonts/truetype/nanum/NanumSquareRoundB.ttf", 0),
        ("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf", 0),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc", 1),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 1),
        ("C:/Windows/Fonts/malgun.ttf", 0),
    ],
}
_cache: dict = {}


def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    k = (kind, size)
    if k not in _cache:
        for path, idx in _FONT_CANDIDATES[kind]:
            if os.path.exists(path):
                _cache[k] = ImageFont.truetype(path, size, index=idx)
                break
        else:
            hits = glob.glob("/usr/share/fonts/**/*CJK*.tt*", recursive=True)
            if not hits:
                raise RuntimeError("한글 폰트를 찾을 수 없습니다. assets/fonts/bold.ttf를 넣어주세요.")
            _cache[k] = ImageFont.truetype(hits[0], size, index=1 if hits[0].endswith("ttc") else 0)
    return _cache[k]


def hex2rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def wrap(text: str, f: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    """띄어쓰기 우선, 긴 단어는 글자 단위로 줄바꿈."""
    lines, cur = [], ""
    for word in text.replace("\n", " \n ").split(" "):
        if word == "\n":
            lines.append(cur.strip()); cur = ""; continue
        trial = (cur + " " + word).strip()
        if f.getlength(trial) <= max_w:
            cur = trial
        elif f.getlength(word) > max_w:
            for ch in word:
                if f.getlength(cur + ch) > max_w:
                    lines.append(cur); cur = ch
                else:
                    cur += ch
        else:
            lines.append(cur); cur = word
    if cur:
        lines.append(cur)
    return [l for l in lines if l is not None]


def fit_text(text, kind, max_w, max_h, start, min_size=22, spacing=1.3):
    size = start
    while size >= min_size:
        f = font(kind, size)
        lines = wrap(text, f, max_w)
        if len(lines) * size * spacing <= max_h:
            return f, lines, size
        size -= 2
    f = font(kind, min_size)
    lines = wrap(text, f, max_w)
    return f, lines[: max(1, int(max_h // (min_size * spacing)))], min_size


def cover_crop(img: Image.Image, w: int, h: int) -> Image.Image:
    r = max(w / img.width, h / img.height)
    img = img.resize((int(img.width * r + 1), int(img.height * r + 1)), Image.LANCZOS)
    x, y = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


CHAR_COLOR = {"M": (36, 52, 110), "F": (226, 92, 70)}


def sticker(img: Image.Image, border: int = 7) -> Image.Image:
    """캐릭터 외곽에 흰 테두리(스티커 효과) — 사진 위에서 또렷하게."""
    pad = border * 2
    base = Image.new("RGBA", (img.width + pad * 2, img.height + pad * 2), (0, 0, 0, 0))
    base.paste(img, (pad, pad), img)
    a = base.getchannel("A").filter(ImageFilter.MaxFilter(border * 2 + 1))
    out = Image.new("RGBA", base.size, (255, 255, 255, 0))
    out.putalpha(a.point(lambda v: 255 if v > 30 else 0))
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    shadow.putalpha(a.point(lambda v: 90 if v > 30 else 0).filter(ImageFilter.GaussianBlur(6)))
    final = Image.new("RGBA", base.size, (0, 0, 0, 0))
    final.alpha_composite(shadow, (4, 6))
    final.alpha_composite(out)
    final.alpha_composite(base)
    return final


def place_char(canvas: Image.Image, who: str, pose: str, height: int, side: str, flip=False) -> tuple:
    """캐릭터를 화면 아래쪽에 배치(아래 일부가 화면 밖으로 나가게). 머리 위치를 반환."""
    W, H = canvas.size
    ch = characters.load(who, pose)
    if flip:
        ch = ch.transpose(Image.FLIP_LEFT_RIGHT)
    r = height / ch.height
    ch = ch.resize((int(ch.width * r), height), Image.LANCZOS)
    st = sticker(ch)
    y = H - int(height * 0.90)
    x = -int(st.width * 0.06) if side == "left" else W - st.width + int(st.width * 0.06)
    canvas.alpha_composite(st, (x, y))
    return (x + st.width // 2, y + 20, x, x + st.width)


def bottom_shade(img: Image.Image, start=0.45, strength=200) -> Image.Image:
    W, H = img.size
    grad = Image.new("L", (1, H))
    for y in range(H):
        grad.putpixel((0, y), int(max(0, (y - H * start) / (H * (1 - start))) ** 1.4 * strength))
    dark = Image.new("RGBA", (W, H), (10, 12, 22, 255))
    dark.putalpha(grad.resize((W, H)))
    out = img.convert("RGBA")
    out.alpha_composite(dark)
    return out


def top_shade(img: Image.Image, h=260, strength=150) -> Image.Image:
    W, _ = img.size
    grad = Image.new("L", (1, h))
    for y in range(h):
        grad.putpixel((0, y), int((1 - y / h) * strength))
    dark = Image.new("RGBA", (W, h), (10, 12, 22, 255))
    dark.putalpha(grad.resize((W, h)))
    img.alpha_composite(dark, (0, 0))
    return img


def news_chip(d, cfg, tag, page=None, total=None, x=34, y=30):
    theme = hex2rgb(cfg["comic"]["theme_color"])
    f1, f2 = font("bold", 30), font("bold", 26)
    name = cfg["account"]["name"]
    w1 = f1.getlength(name) + 34
    d.rounded_rectangle([x, y, x + w1, y + 52], radius=10, fill=theme)
    d.text((x + 17, y + 8), name, font=f1, fill="white")
    w2 = f2.getlength(tag) + 28
    d.rounded_rectangle([x + w1 + 8, y + 4, x + w1 + 8 + w2, y + 48], radius=10, fill=(255, 255, 255))
    d.text((x + w1 + 22, y + 10), tag, font=f2, fill=INK)
    if page:
        pg = f"{page} / {total}"
        pw = f2.getlength(pg) + 28
        W = d.im.size[0]
        d.rounded_rectangle([W - 34 - pw, y + 4, W - 34, y + 48], radius=22, fill=(0, 0, 0, 160))
        d.text((W - 34 - pw + 14, y + 10), pg, font=f2, fill="white")


def speech(d, cx, top, max_w, text, who, name, tail_to, big=True):
    """말풍선: 위쪽에 배치, 꼬리는 화자 머리(tail_to) 쪽으로."""
    f, lines, size = fit_text(text, "bold", max_w - 80, 330 if big else 150, 48 if big else 36, 26, 1.28)
    lh = int(size * 1.28)
    tw = max(f.getlength(l) for l in lines)
    w, h = int(tw + 84), int(len(lines) * lh + 62)
    x0 = int(min(max(cx - w / 2, 28), d.im.size[0] - 28 - w))
    y0, x1, y1 = top, x0 + w, top + h
    # 꼬리
    bx = min(max(tail_to[0], x0 + 70), x1 - 70)
    tip = (tail_to[0] * 0.5 + bx * 0.5, min(tail_to[1], y1 + 120))
    d.polygon([(bx - 30, y1 - 8), (bx + 30, y1 - 8), tip], fill="white", outline=INK, width=5)
    d.rounded_rectangle([x0 + 6, y0 + 8, x1 + 6, y1 + 8], radius=38, fill=(0, 0, 0, 90))
    d.rounded_rectangle([x0, y0, x1, y1], radius=38, fill="white", outline=INK, width=5)
    d.polygon([(bx - 24, y1 - 12), (bx + 24, y1 - 12), (tip[0], tip[1] - 14)], fill="white")
    # 화자 이름표
    nf = font("bold", 26)
    nw = nf.getlength(name) + 30
    d.rounded_rectangle([x0 + 28, y0 - 22, x0 + 28 + nw, y0 + 20], radius=21, fill=CHAR_COLOR[who])
    d.text((x0 + 43, y0 - 17), name, font=nf, fill="white")
    for i, l in enumerate(lines):
        d.text((x0 + (w - f.getlength(l)) / 2, y0 + 32 + i * lh), l, font=f, fill=INK)
    return y1


def credit(d, text, W, H, color=(235, 235, 240)):
    if text:
        cf = font("regular", 22)
        d.text((W - 26 - cf.getlength(text), H - 40), text, font=cf, fill=color,
               stroke_width=2, stroke_fill=(0, 0, 0))


def render_panel(photo, panel: dict, cfg: dict, tag: str, page: int, total: int) -> Image.Image:
    W, H = cfg["comic"]["width"], cfg["comic"]["height"]
    names = {k: v["name"] for k, v in cfg["characters"].items()}
    canvas = bottom_shade(cover_crop(photo.image, W, H), 0.55, 150)
    canvas = top_shade(canvas)
    lines = (panel.get("lines") or [])[:2]
    if not lines:
        lines = [{"who": "F", "pose": "explain", "text": panel.get("narration", "")}]
    main = lines[0]
    main_who = main.get("who", "F") if main.get("who") in ("M", "F") else "F"
    main_side = "left" if main_who == "M" else "right"
    other = lines[1] if len(lines) > 1 and lines[1].get("who") in ("M", "F") else None

    # 리액션 캐릭터(작게) 먼저, 메인 캐릭터(크게) 나중
    heads = {}
    if other and other["who"] != main_who:
        heads[other["who"]] = place_char(canvas, other["who"], other.get("pose", "laugh"), int(H * 0.40),
                                         "left" if main_side == "right" else "right")
    heads[main_who] = place_char(canvas, main_who, main.get("pose", "explain"), int(H * 0.58), main_side)

    d = ImageDraw.Draw(canvas, "RGBA")
    news_chip(d, cfg, tag, page, total)
    y = speech(d, W // 2, 130, W - 70, main.get("text", ""), main_who, names[main_who],
               heads[main_who][:2], big=True)
    if other:
        who = other["who"]
        tgt = heads.get(who, heads[main_who])[:2]
        cx = W * (0.30 if (who == "M") else 0.70)
        speech(d, int(cx), y + 70, 520, other.get("text", ""), who, names[who], tgt, big=False)
    credit(d, photo.credit, W, H)
    return canvas.convert("RGB")


def render_cover(photo, script: dict, cfg: dict, total: int) -> Image.Image:
    W, H = cfg["comic"]["width"], cfg["comic"]["height"]
    theme = hex2rgb(cfg["comic"]["theme_color"])
    canvas = bottom_shade(cover_crop(photo.image, W, H), 0.25, 225)
    canvas = top_shade(canvas)
    place_char(canvas, "M", "intro", int(H * 0.47), "left")
    place_char(canvas, "F", "intro", int(H * 0.45), "right")
    d = ImageDraw.Draw(canvas, "RGBA")
    tag = script.get("category_tag", "이슈")
    date = datetime.now().strftime("%Y.%m.%d")
    news_chip(d, cfg, f"오늘의 {tag}")
    df = font("bold", 28)
    d.text((W - 36 - df.getlength(date), 40), date, font=df, fill="white", stroke_width=2, stroke_fill=INK)

    # 제목 블록 (상단~중단)
    f, lines, size = fit_text(script["topic_title"], "bold", W - 110, 300, 100, 60, 1.15)
    y = 190
    for l in lines:
        d.text((56, y), l, font=f, fill="white", stroke_width=7, stroke_fill=INK)
        y += int(size * 1.15)
    d.rectangle([58, y + 16, 230, y + 28], fill=theme)
    hf, hl, hs = fit_text(script.get("hook", ""), "bold", W - 120, 130, 42, 28)
    for i, l in enumerate(hl):
        d.text((58, y + 50 + i * int(hs * 1.3)), l, font=hf, fill="white", stroke_width=4, stroke_fill=INK)
    sw = font("bold", 30)
    msg = "넘겨서 보기 →"
    d.rounded_rectangle([W / 2 - sw.getlength(msg) / 2 - 26, H - 112, W / 2 + sw.getlength(msg) / 2 + 26, H - 58],
                        radius=27, fill=theme)
    d.text((W / 2 - sw.getlength(msg) / 2, H - 104), msg, font=sw, fill="white")
    credit(d, photo.credit, W, H)
    return canvas.convert("RGB")


def render_outro(script: dict, cfg: dict, page: int, total: int) -> Image.Image:
    W, H = cfg["comic"]["width"], cfg["comic"]["height"]
    theme = hex2rgb(cfg["comic"]["theme_color"])
    canvas = Image.new("RGBA", (W, H), (255, 248, 238, 255))
    place_char(canvas, "M", "thumbsup", int(H * 0.40), "left")
    place_char(canvas, "F", "laugh", int(H * 0.38), "right")
    d = ImageDraw.Draw(canvas, "RGBA")
    news_chip(d, cfg, script.get("category_tag", "이슈"), page, total)

    d.text((60, 120), "3줄 요약", font=font("bold", 70), fill=INK)
    d.rectangle([60, 212, 240, 224], fill=theme)
    y = 262
    for i, s in enumerate(script.get("summary", [])[:3]):
        d.ellipse([60, y, 122, y + 62], fill=theme)
        d.text((80, y + 6), str(i + 1), font=font("bold", 40), fill="white")
        f, lines, size = fit_text(s, "bold", W - 210, 130, 42, 30)
        for j, l in enumerate(lines):
            d.text((146, y + 6 + j * int(size * 1.3)), l, font=f, fill=INK)
        y += max(100, len(lines) * int(size * 1.3) + 40)

    qy = y + 20
    f, lines, size = fit_text(script.get("question", ""), "bold", W - 180, 120, 38, 26)
    qh = 80 + len(lines) * int(size * 1.35)
    d.rounded_rectangle([40, qy, W - 40, qy + qh], radius=28, fill="white", outline=INK, width=5)
    d.text((76, qy + 22), "여러분 생각은?", font=font("bold", 32), fill=theme)
    for j, l in enumerate(lines):
        d.text((76, qy + 66 + j * int(size * 1.35)), l, font=f, fill=INK)

    src = script.get("source", {})
    n = src.get("n_sources")
    site = "Pixabay" if cfg.get("photos", {}).get("provider", "pixabay") == "pixabay" else "Pexels"
    stext = f"참고: {src.get('source', '')} 등 {n}개 언론 보도 종합 · 배경 사진: {site}" if n else f"배경 사진: {site}"
    cf = font("regular", 22)
    d.text(((W - cf.getlength(stext)) / 2, qy + qh + 14), stext, font=cf, fill=(110, 110, 120))
    cta = f"매일 세계 이슈를 쉽고 재밌게  {cfg['account']['handle']}"
    tf = font("bold", 30)
    cy = qy + qh + 60
    d.rounded_rectangle([W / 2 - tf.getlength(cta) / 2 - 30, cy, W / 2 + tf.getlength(cta) / 2 + 30, cy + 56],
                        radius=28, fill=INK)
    d.text((W / 2 - tf.getlength(cta) / 2, cy + 8), cta, font=tf, fill="white")
    return canvas.convert("RGB")
