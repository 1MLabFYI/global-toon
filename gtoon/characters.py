"""고정 진행자 캐릭터(남 M / 여 F)의 표정·동작 이미지 관리.

assets/characters/
  M_intro.png, F_intro.png   : 원본 그림에서 오려낸 기본 동작(항상 존재)
  M_ref.png,  F_ref.png      : AI 동작 생성용 기준 그림(흰 배경, 500px)
  M_<pose>.png, F_<pose>.png : AI로 1회 생성한 동작(없거나 지우면 다음 실행 때 다시 생성)
"""
from __future__ import annotations

import io
import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "assets", "characters")

POSES = {
    "explain":   "explaining something with one open palm raised, friendly smile",
    "point":     "pointing to the side with index finger, excited open-mouth smile",
    "surprised": "shocked surprised face, wide eyes, mouth open, both hands on cheeks",
    "laugh":     "laughing happily with eyes closed, hand near mouth",
    "think":     "thinking, hand on chin, curious eyes looking up",
    "worried":   "worried nervous face with a sweat drop, awkward smile",
    "thumbsup":  "giving a thumbs up with a confident wink",
    "shrug":     "shrugging with both palms up, puzzled smile",
}


def path(who: str, pose: str) -> str:
    return os.path.join(DIR, f"{who}_{pose}.png")


def load(who: str, pose: str) -> Image.Image:
    """요청한 동작이 없으면 기본(intro) 동작으로 대체."""
    p = path(who, pose)
    if not os.path.exists(p):
        p = path(who, "intro")
    return Image.open(p).convert("RGBA")


def missing_poses() -> list[tuple[str, str]]:
    return [(w, p) for w in ("M", "F") for p in POSES if not os.path.exists(path(w, p))]


def build_missing(cfg: dict, limit: int = 16) -> int:
    """빠진 동작을 FLUX.2(기준 그림 참고)로 생성 → rembg로 배경 제거 → 저장. 1회성 작업."""
    todo = missing_poses()[:limit]
    if not todo:
        return 0
    from rembg import new_session, remove      # 무거운 패키지라 필요할 때만 import
    from . import imagegen
    session = new_session("isnet-anime")
    made = 0
    for who, pose in todo:
        desc = cfg["characters"][who]["look"]
        prompt = (f"The exact same character as in the reference image ({desc}), identical face, hairstyle, "
                  f"outfit and 2D anime cartoon art style. Pose: {POSES[pose]}. Upper body, centered, "
                  f"isolated on a plain pure white background, clean outlines, no text, no props except the outfit")
        with open(path(who, "ref"), "rb") as f:
            ref = f.read()
        conf = {**cfg, "image": {**cfg["image"], "width": 768, "height": 1024}}
        for model in ("flux-2-dev", "flux-2-klein-4b"):
            try:
                img = imagegen._flux2(model, prompt, conf, 11 + made, ref)
                cut = remove(img, session=session).convert("RGBA")
                cut.putalpha(cut.getchannel("A").point(lambda v: 0 if v < 25 else v))
                cut = cut.crop(cut.getbbox())
                cut.save(path(who, pose))
                print(f"[char] {who}_{pose} 생성({model})")
                made += 1
                break
            except Exception as e:
                print(f"[char] {who}_{pose} {model} 실패: {e}")
    return made
