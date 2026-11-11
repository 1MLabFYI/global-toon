"""배경 실사 사진 — Pixabay(기본) 또는 Pexels 무료 라이선스 사진을 키워드로 검색 (상업적 이용 가능, 출처 표기).

- Pixabay: 이미지를 내려받아 사용(직접 링크 금지 규정 준수), 출처 '이름 / Pixabay' 표기
- Pexels: 2026년 신규 키 발급 중단 → 이미 키가 있는 경우에만 사용

실제 보도사진(통신사·언론사 저작물)은 쓰지 않는다. 기사 내용과 어울리는 장소·사물 사진을 고른다.
"""
from __future__ import annotations

import io
import os
from dataclasses import dataclass

import requests
from PIL import Image, ImageDraw, ImageFilter

API = "https://api.pexels.com/v1/search"
PIXABAY = "https://pixabay.com/api/"


@dataclass
class Photo:
    image: Image.Image
    credit: str            # "Photo: 이름 / Pexels"
    url: str
    source: str            # pexels | fallback


def _search(query: str, used: set, orientation: str) -> dict | None:
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        raise RuntimeError("PEXELS_API_KEY 없음")
    r = requests.get(API, headers={"Authorization": key.strip()}, timeout=30,
                     params={"query": query, "orientation": orientation, "per_page": 15,
                             "size": "medium", "locale": "en-US"})
    r.raise_for_status()
    for p in r.json().get("photos", []):
        if p["id"] not in used:
            return p
    return None


def _pixabay(query: str, used: set) -> dict | None:
    key = os.environ.get("PIXABAY_API_KEY")
    if not key:
        raise RuntimeError("PIXABAY_API_KEY 없음")
    r = requests.get(PIXABAY, timeout=30, params={
        "key": key.strip(), "q": query[:100], "image_type": "photo", "orientation": "vertical",
        "safesearch": "true", "per_page": 20, "min_height": 900, "order": "popular"})
    r.raise_for_status()
    for h in r.json().get("hits", []):
        if h["id"] not in used:
            return {"id": h["id"], "img": h["largeImageURL"], "who": h.get("user", ""),
                    "url": h["pageURL"], "site": "Pixabay"}
    return None


def _pexels(query: str, used: set) -> dict | None:
    p = _search(query, used, "portrait")
    if p:
        return {"id": p["id"], "img": p["src"]["large2x"], "who": p["photographer"], "url": p["url"], "site": "Pexels"}
    return None


def fallback(w: int, h: int, color=(40, 70, 140)) -> Image.Image:
    """사진을 못 구했을 때: 뉴스 스튜디오 느낌의 그라데이션 배경."""
    img = Image.new("RGB", (w, h), color)
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=(int(30 + 40 * t), int(60 + 50 * t), int(130 + 60 * t)))
    for i in range(0, w + h, 60):
        d.line([(i, 0), (i - h, h)], fill=(255, 255, 255), width=1)
    return img.filter(ImageFilter.GaussianBlur(1))


def get_photo(queries: list[str], used: set, size: tuple[int, int], provider: str = "pixabay") -> Photo:
    """여러 검색어를 순서대로 시도(구체적 → 일반적). 같은 게시물에서 사진 중복 방지."""
    finder = _pexels if provider == "pexels" else _pixabay
    for q in [q for q in queries if q]:
        try:
            p = finder(q, used)
        except Exception as e:
            print(f"[photo] '{q}' 검색 실패: {e}")
            continue
        if not p:
            print(f"[photo] '{q}' 결과 없음")
            continue
        try:
            img = Image.open(io.BytesIO(requests.get(p["img"], timeout=60).content)).convert("RGB")
        except Exception as e:
            print(f"[photo] 다운로드 실패: {e}")
            continue
        used.add(p["id"])
        print(f"[photo] '{q}' → {p['who']} / {p['site']} ({p['url']})")
        return Photo(img, f"Photo: {p['who']} / {p['site']}", p["url"], p["site"].lower())
    print("[photo] 사진 없음 → 기본 배경 사용")
    return Photo(fallback(*size), "", "", "fallback")
