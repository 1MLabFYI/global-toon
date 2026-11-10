"""오리지널 해설 캐릭터 '지구톤' — 코드로 그려서 매 컷 일관된 모습 유지."""
from __future__ import annotations

from PIL import Image, ImageDraw

OCEAN = (64, 156, 255)
LAND = (98, 204, 120)
LINE = (30, 34, 48)
CHEEK = (255, 140, 150)


def draw_mascot(size: int = 400, mood: str = "happy") -> Image.Image:
    S = 4  # 슈퍼샘플링
    W = size * S
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    lw = int(W * 0.022)

    # 몸통 + 팔
    bx0, by0, bx1, by1 = W * .30, W * .70, W * .70, W * .98
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=W * .1, fill=(255, 214, 92), outline=LINE, width=lw)
    if mood == "surprised":
        d.line([(bx0, by0 + W * .06), (W * .12, W * .62)], fill=LINE, width=lw * 2)
        d.line([(bx1, by0 + W * .06), (W * .88, W * .62)], fill=LINE, width=lw * 2)
    else:
        d.line([(bx0, by0 + W * .08), (W * .16, W * .90)], fill=LINE, width=lw * 2)
        d.line([(bx1, by0 + W * .08), (W * .86, W * .64)], fill=LINE, width=lw * 2)  # 손 들기

    # 지구 머리
    cx, cy, r = W * .5, W * .40, W * .34
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=OCEAN, outline=LINE, width=lw)
    # 추상 대륙(실제 지도 아님)
    for (x, y, rx, ry) in [(-.18, -.16, .13, .09), (.12, -.20, .10, .07),
                           (.17, .10, .09, .12), (-.20, .14, .08, .06), (.0, .26, .12, .05)]:
        d.ellipse([cx + (x - rx) * W, cy + (y - ry) * W, cx + (x + rx) * W, cy + (y + ry) * W], fill=LAND)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=LINE, width=lw)
    # 하이라이트
    d.arc([cx - r * .82, cy - r * .82, cx + r * .82, cy + r * .82], 200, 250, fill=(255, 255, 255), width=lw)

    # 얼굴
    ey, ex, er = cy - W * .01, W * .11, W * .052
    for sx in (-1, 1):
        x = cx + sx * ex
        if mood == "think" and sx == 1:
            d.line([(x - er, ey), (x + er, ey)], fill=LINE, width=lw)
        else:
            d.ellipse([x - er, ey - er * 1.2, x + er, ey + er * 1.2], fill=(255, 255, 255), outline=LINE, width=lw // 2)
            d.ellipse([x - er * .55, ey - er * .5, x + er * .55, ey + er * .8], fill=LINE)
            d.ellipse([x - er * .1, ey - er * .35, x + er * .25, ey], fill=(255, 255, 255))
        d.ellipse([x - er * 1.1, ey + er * 1.5, x + er * .9, ey + er * 2.3], fill=CHEEK)
    my = cy + W * .12
    if mood == "surprised":
        d.ellipse([cx - W * .035, my - W * .03, cx + W * .035, my + W * .05], fill=LINE)
    elif mood == "think":
        d.line([(cx - W * .04, my), (cx + W * .04, my - W * .01)], fill=LINE, width=lw)
    else:
        d.chord([cx - W * .07, my - W * .05, cx + W * .07, my + W * .06], 0, 180, fill=LINE)
    return img.resize((size, size), Image.LANCZOS)
