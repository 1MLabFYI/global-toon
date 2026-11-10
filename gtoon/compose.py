"""컷 이미지 + 한글 말풍선/해설/표지/마무리 컷 합성 (AI가 한글을 그리지 않도록 직접 렌더)."""
from __future__ import annotations

import glob
import os
from datetime import datetime

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .mascot import draw_mascot

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


def _rounded_paste(base, img, xy, radius, border=5):
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, *img.size], radius=radius, fill=255)
    base.paste(img, xy, mask)
    x, y = xy
    ImageDraw.Draw(base).rounded_rectangle([x, y, x + img.width, y + img.height],
                                           radius=radius, outline=INK, width=border)


def _bubble(d: ImageDraw.ImageDraw, box, text, side, speaker, theme):
    x0, y0, max_w = box
    f, lines, size = fit_text(text, "bold", max_w - 60, 200, 40, 26)
    lh = int(size * 1.3)
    tw = max(f.getlength(l) for l in lines)
    w, h = int(tw + 64), int(len(lines) * lh + 44)
    if side == "right":
        x0 = x0 - w
    x1, y1 = x0 + w, y0 + h
    # 꼬리
    tx = x0 + w * (0.3 if side == "left" else 0.7)
    tail = [(tx - 22, y1 - 6), (tx + 22, y1 - 6), (tx + (-30 if side == "left" else 30), y1 + 46)]
    d.polygon(tail, fill="white", outline=INK)
    d.rounded_rectangle([x0, y0, x1, y1], radius=min(46, h // 2), fill="white", outline=INK, width=5)
    d.polygon([(tail[0][0] + 5, tail[0][1] - 4), (tail[1][0] - 5, tail[1][1] - 4),
               (tail[2][0] + (4 if side == 'left' else -4), tail[2][1] - 10)], fill="white")
    # 화자 라벨
    if speaker:
        sf = font("bold", 24)
        sw = sf.getlength(speaker) + 24
        d.rounded_rectangle([x0 + 18, y0 - 18, x0 + 18 + sw, y0 + 16], radius=14, fill=theme)
        d.text((x0 + 30, y0 - 15), speaker, font=sf, fill="white")
    for i, l in enumerate(lines):
        d.text((x0 + (w - f.getlength(l)) / 2, y0 + 22 + i * lh), l, font=f, fill=INK)
    return y1 + 60


def _header(d, W, cfg, tag, page, total):
    theme = hex2rgb(cfg["comic"]["theme_color"])
    d.rectangle([0, 0, W, 86], fill=INK)
    d.text((36, 22), cfg["account"]["name"], font=font("bold", 36), fill="white")
    tf = font("bold", 26)
    tx = 36 + font("bold", 36).getlength(cfg["account"]["name"]) + 20
    d.rounded_rectangle([tx, 24, tx + tf.getlength(tag) + 28, 62], radius=19, fill=theme)
    d.text((tx + 14, 27), tag, font=tf, fill="white")
    pg = f"{page}/{total}"
    d.text((W - 36 - font("bold", 30).getlength(pg), 26), pg, font=font("bold", 30), fill=(200, 200, 210))


def render_panel(img: Image.Image, panel: dict, cfg: dict, tag: str, page: int, total: int) -> Image.Image:
    W, H = cfg["comic"]["width"], cfg["comic"]["height"]
    theme = hex2rgb(cfg["comic"]["theme_color"])
    mascot_name = cfg["account"]["mascot_name"]
    canvas = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(canvas)
    _header(d, W, cfg, tag, page, total)

    # 그림 영역
    pic_y, pic_h = 108, 930
    _rounded_paste(canvas, cover_crop(img, W - 48, pic_h), (24, pic_y), 28)

    # 말풍선
    y = pic_y + 40
    for i, b in enumerate((panel.get("bubbles") or [])[:2]):
        side = b.get("side") or ("left" if i % 2 == 0 else "right")
        x = 56 if side == "left" else W - 56
        spk = b.get("speaker", "")
        y = _bubble(d, (x, y, 620), b.get("text", ""), side,
                    spk if spk != mascot_name else mascot_name, theme)

    # 해설 박스 + 마스코트
    ny = pic_y + pic_h + 22
    d.rounded_rectangle([24, ny, W - 24, H - 24], radius=28, fill="white", outline=INK, width=5)
    m = draw_mascot(170, "think" if page % 3 == 0 else "happy")
    canvas.paste(m, (40, ny + 18), m)
    f, lines, size = fit_text(panel.get("narration", ""), "regular", W - 290, H - 24 - ny - 50, 38, 26)
    lh = int(size * 1.35)
    ty = ny + ((H - 24 - ny) - len(lines) * lh) // 2
    for i, l in enumerate(lines):
        d.text((228, ty + i * lh), l, font=f, fill=INK)
    return canvas


def render_cover(img: Image.Image, script: dict, cfg: dict, total: int) -> Image.Image:
    W, H = cfg["comic"]["width"], cfg["comic"]["height"]
    theme = hex2rgb(cfg["comic"]["theme_color"])
    bg = cover_crop(img, W, H)
    canvas = bg.copy()
    # 하단 어둡게
    grad = Image.new("L", (1, H))
    for y in range(H):
        grad.putpixel((0, y), int(max(0, (y - H * .35) / (H * .65)) * 235))
    dark = Image.new("RGB", (W, H), (12, 14, 24))
    canvas.paste(dark, (0, 0), grad.resize((W, H)))
    d = ImageDraw.Draw(canvas)

    # 상단 라벨
    tag = script.get("category_tag", "이슈")
    date = datetime.now().strftime("%Y.%m.%d")
    d.rounded_rectangle([40, 40, 40 + font("bold", 34).getlength(f"오늘의 {tag} 이슈") + 48, 104],
                        radius=32, fill=theme)
    d.text((64, 50), f"오늘의 {tag} 이슈", font=font("bold", 34), fill="white")
    d.text((W - 40 - font("bold", 30).getlength(date), 56), date, font=font("bold", 30), fill="white",
           stroke_width=3, stroke_fill=INK)

    # 제목
    f, lines, size = fit_text(script["topic_title"], "bold", W - 380, 330, 92, 52, 1.18)
    y = H - 140 - 90 - len(lines) * int(size * 1.18)
    for l in lines:
        d.text((60, y), l, font=f, fill="white", stroke_width=6, stroke_fill=INK)
        y += int(size * 1.18)
    d.rectangle([60, y + 24, 200, y + 34], fill=theme)
    hf, hl, hs = fit_text(script.get("hook", ""), "regular", W - 360, 120, 40, 28)
    for i, l in enumerate(hl):
        d.text((60, y + 56 + i * int(hs * 1.3)), l, font=hf, fill=(235, 235, 240))

    m = draw_mascot(260, "surprised")
    canvas.paste(m, (W - 290, H - 330), m)
    d.text((60, H - 70), f"{cfg['account']['handle']} · 넘겨서 보기 →", font=font("bold", 30), fill=(210, 210, 220))
    return canvas


def render_outro(script: dict, cfg: dict, page: int, total: int) -> Image.Image:
    W, H = cfg["comic"]["width"], cfg["comic"]["height"]
    theme = hex2rgb(cfg["comic"]["theme_color"])
    canvas = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(canvas)
    _header(d, W, cfg, script.get("category_tag", "이슈"), page, total)

    d.text((60, 140), "3줄 요약", font=font("bold", 72), fill=INK)
    d.rectangle([60, 236, 240, 248], fill=theme)
    y = 300
    for i, s in enumerate(script.get("summary", [])[:3]):
        d.ellipse([60, y, 124, y + 64], fill=theme)
        d.text((80, y + 6), str(i + 1), font=font("bold", 42), fill="white")
        f, lines, size = fit_text(s, "bold", W - 220, 140, 44, 30)
        for j, l in enumerate(lines):
            d.text((150, y + 4 + j * int(size * 1.3)), l, font=f, fill=INK)
        y += max(110, len(lines) * int(size * 1.3) + 46)

    # 질문 카드
    qy = y + 40
    d.rounded_rectangle([40, qy, W - 40, qy + 250], radius=30, fill="white", outline=INK, width=5)
    d.text((80, qy + 30), "여러분 생각은?", font=font("bold", 36), fill=theme)
    f, lines, size = fit_text(script.get("question", ""), "regular", W - 400, 150, 38, 26)
    for j, l in enumerate(lines):
        d.text((80, qy + 90 + j * int(size * 1.35)), l, font=f, fill=INK)
    m = draw_mascot(230, "happy")
    canvas.paste(m, (W - 280, qy + 10), m)

    src = script.get("source", {})
    n = src.get("n_sources")
    stext = (f"참고: {src.get('source', '')} 등 {n}개 언론 보도 종합" if n else f"참고: {src.get('source', '')}") + " · 그림은 AI 생성 일러스트"
    sf = font("regular", 24)
    d.text((40, H - 150), stext, font=sf, fill=(120, 120, 130))
    d.rounded_rectangle([40, H - 110, W - 40, H - 30], radius=40, fill=INK)
    cta = f"매일 세계 이슈를 웹툰으로  {cfg['account']['handle']}  팔로우"
    cf = font("bold", 32)
    d.text(((W - cf.getlength(cta)) / 2, H - 92), cta, font=cf, fill="white")
    return canvas
