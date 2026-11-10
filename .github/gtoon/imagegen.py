"""컷 그림 생성 — 무료 공급자를 순서대로 시도하고 모두 실패하면 대체 그림을 만든다."""
from __future__ import annotations

import base64
import hashlib
import io
import os
import random
import time
import urllib.parse

import requests
from PIL import Image, ImageDraw, ImageFilter


def _cloudflare(prompt: str, cfg: dict, seed: int) -> Image.Image:
    acc, tok = os.environ.get("CF_ACCOUNT_ID"), os.environ.get("CF_API_TOKEN")
    if not (acc and tok):
        raise RuntimeError("CF_ACCOUNT_ID/CF_API_TOKEN 없음")
    model = cfg["image"]["cloudflare_model"]
    url = f"https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/{model}"
    r = requests.post(url, headers={"Authorization": f"Bearer {tok}"}, timeout=120,
                      json={"prompt": prompt[:2000], "steps": min(8, cfg["image"]["steps"]),
                            "seed": seed})
    r.raise_for_status()
    if r.headers.get("content-type", "").startswith("image/"):
        return Image.open(io.BytesIO(r.content)).convert("RGB")
    b64 = r.json()["result"]["image"]
    return Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")


def _pollinations(prompt: str, cfg: dict, seed: int) -> Image.Image:
    size = cfg["image"]["size"]
    q = urllib.parse.quote(prompt[:900])
    url = (f"https://image.pollinations.ai/prompt/{q}"
           f"?width={size}&height={size}&seed={seed}&nologo=true&model=flux")
    headers = {}
    if os.environ.get("POLLINATIONS_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['POLLINATIONS_TOKEN']}"
    r = requests.get(url, headers=headers, timeout=180)
    r.raise_for_status()
    return Image.open(io.BytesIO(r.content)).convert("RGB")


def _placeholder(prompt: str, cfg: dict, seed: int) -> Image.Image:
    """네트워크 없이도 동작하는 대체 그림(파스텔 그라데이션 + 도형)."""
    rnd = random.Random(seed)
    size = cfg["image"]["size"]
    c1 = tuple(rnd.randint(150, 240) for _ in range(3))
    c2 = tuple(rnd.randint(90, 200) for _ in range(3))
    img = Image.new("RGB", (size, size), c1)
    d = ImageDraw.Draw(img)
    for y in range(size):
        t = y / size
        d.line([(0, y), (size, y)], fill=tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3)))
    for _ in range(14):
        x, y, r = rnd.randint(0, size), rnd.randint(0, size), rnd.randint(40, 220)
        col = tuple(min(255, v + rnd.randint(10, 60)) for v in c2)
        d.ellipse([x - r, y - r, x + r, y + r], fill=col)
    return img.filter(ImageFilter.GaussianBlur(18))


PROVIDERS = {"cloudflare": _cloudflare, "pollinations": _pollinations,
             "placeholder": _placeholder}


def generate(scene: str, cfg: dict, key: str) -> tuple[Image.Image, str]:
    prompt = f"{scene}. {cfg['comic']['style_prompt']}"
    seed = int(hashlib.md5(key.encode()).hexdigest()[:8], 16)
    for name in cfg["image"]["providers"]:
        for attempt in range(2):
            try:
                img = PROVIDERS[name](prompt, cfg, seed + attempt)
                print(f"[image] {name} OK")
                return img, name
            except Exception as e:
                print(f"[image] {name} fail({attempt + 1}): {e}")
                time.sleep(4)
    return _placeholder(prompt, cfg, seed), "placeholder"
