"""컷 그림 생성 — Cloudflare Workers AI(무료 일 1만 뉴런)의 FLUX 모델을 순서대로 시도.

- 2D 컬러 만화체 고정 스타일 + 고정 등장인물(cast) 묘사로 화풍·캐릭터 일관성 확보
- FLUX.2 모델은 '캐릭터 기준 이미지(assets/cast_ref.png)'를 참고 이미지로 함께 보내 얼굴·옷을 유지
- 무료 대체(placeholder)는 테스트용이며, 대체 그림이 섞이면 게시하지 않음
"""
from __future__ import annotations

import base64
import hashlib
import io
import os
import random
import re
import time

import requests
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAST_REF = os.path.join(ROOT, "assets", "cast_ref.png")
PUBLISHABLE = {"flux-2-dev", "flux-2-klein-4b", "flux-1-schnell"}


class ImageError(RuntimeError):
    pass


def expand_cast(scene: str, cfg: dict) -> str:
    """대본의 HANA, BOSS 같은 배역 이름을 고정 외모 묘사로 치환."""
    for key, desc in cfg["image"]["cast"].items():
        scene = re.sub(rf"\b{key}\b", f"{key} ({desc})", scene)
    return scene


def build_prompt(scene: str, cfg: dict) -> str:
    return (f"{cfg['comic']['style_prompt']}. Scene: {expand_cast(scene, cfg)}. "
            f"{cfg['comic']['layout_prompt']}")


def _cf_url(model: str) -> tuple[str, dict]:
    acc, tok = os.environ.get("CF_ACCOUNT_ID"), os.environ.get("CF_API_TOKEN")
    if not (acc and tok):
        raise ImageError("CF_ACCOUNT_ID/CF_API_TOKEN 없음")
    return (f"https://api.cloudflare.com/client/v4/accounts/{acc.strip()}/ai/run/{model}",
            {"Authorization": f"Bearer {tok.strip()}"})


def _decode(r: requests.Response) -> Image.Image:
    if r.status_code >= 400:
        raise ImageError(f"HTTP {r.status_code}: {r.text[:400]}")   # 원인 파악용 본문 출력
    if r.headers.get("content-type", "").startswith("image/"):
        return Image.open(io.BytesIO(r.content)).convert("RGB")
    data = r.json()
    img = (data.get("result") or {}).get("image") or data.get("image")
    if not img:
        raise ImageError(f"이미지 없음: {str(data)[:300]}")
    return Image.open(io.BytesIO(base64.b64decode(img))).convert("RGB")


def _flux2(model: str, prompt: str, cfg: dict, seed: int, ref: bytes | None) -> Image.Image:
    url, hdr = _cf_url(f"@cf/black-forest-labs/{model}")
    w, h = cfg["image"]["width"], cfg["image"]["height"]
    form = {"prompt": (None, prompt[:2000]), "width": (None, str(w)),
            "height": (None, str(h)), "seed": (None, str(seed))}
    if model == "flux-2-dev":
        form["steps"] = (None, str(cfg["image"].get("steps_dev", 20)))
    if ref:
        form["input_image_0"] = ("cast.png", ref, "image/png")
    return _decode(requests.post(url, headers=hdr, files=form, timeout=180))


def _schnell(prompt: str, cfg: dict, seed: int) -> Image.Image:
    url, hdr = _cf_url("@cf/black-forest-labs/flux-1-schnell")
    return _decode(requests.post(url, headers=hdr, timeout=120,
                                 json={"prompt": prompt[:2000], "steps": 8}))  # schnell은 seed 미지원


def placeholder(cfg: dict, seed: int) -> Image.Image:
    rnd = random.Random(seed)
    w, h = cfg["image"]["width"], cfg["image"]["height"]
    c1 = tuple(rnd.randint(170, 240) for _ in range(3))
    img = Image.new("RGB", (w, h), c1)
    d = ImageDraw.Draw(img)
    for _ in range(10):
        x, y, r = rnd.randint(0, w), rnd.randint(0, h), rnd.randint(40, 200)
        d.ellipse([x - r, y - r, x + r, y + r], fill=tuple(rnd.randint(120, 230) for _ in range(3)))
    return img.filter(ImageFilter.GaussianBlur(16))


def _ref_bytes() -> bytes | None:
    if not os.path.exists(CAST_REF):
        return None
    im = Image.open(CAST_REF).convert("RGB")
    im.thumbnail((500, 500))                       # FLUX.2 참고 이미지는 512px 미만
    buf = io.BytesIO(); im.save(buf, "PNG")
    return buf.getvalue()


def ensure_cast_ref(cfg: dict) -> None:
    """캐릭터 기준 이미지가 없으면 1회 생성해 assets/에 저장(이후 매일 재사용 → 캐릭터 고정)."""
    if os.path.exists(CAST_REF) or "placeholder" in cfg["image"]["models"][:1]:
        return
    cast = "; ".join(f"{k}: {v}" for k, v in cfg["image"]["cast"].items())
    prompt = (f"{cfg['comic']['style_prompt']}. Character model sheet on plain white background, "
              f"the characters standing side by side, full body, front view, friendly poses. {cast}. no text")
    for model in cfg["image"]["models"]:
        try:
            img = _flux2(model, prompt, {**cfg, "image": {**cfg["image"], "width": 1024, "height": 768}}, 7, None) \
                if model.startswith("flux-2") else _schnell(prompt, cfg, 7)
            img.save(CAST_REF)
            print(f"[image] 캐릭터 기준 이미지 생성({model}) → assets/cast_ref.png")
            return
        except Exception as e:
            print(f"[image] cast_ref {model} 실패: {e}")


def generate(scene: str, cfg: dict, key: str) -> tuple[Image.Image, str]:
    prompt = build_prompt(scene, cfg)
    seed = int(hashlib.md5(key.encode()).hexdigest()[:7], 16)
    ref = _ref_bytes()
    for model in cfg["image"]["models"]:
        if model == "placeholder":
            return placeholder(cfg, seed), "placeholder"
        for attempt in range(2):
            try:
                if model.startswith("flux-2"):
                    img = _flux2(model, prompt, cfg, seed + attempt, ref)
                else:
                    img = _schnell(prompt, cfg, seed + attempt)
                print(f"[image] {model} OK")
                return img, model
            except Exception as e:
                print(f"[image] {model} 실패({attempt + 1}): {e}")
                time.sleep(5)
    raise ImageError("모든 이미지 모델 실패")
