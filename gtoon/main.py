"""Global Toon 실행 진입점.

  python -m gtoon.main make --slot morning          # 뉴스→대본→이미지→합성 (output/날짜/슬롯/)
  python -m gtoon.main make --slot noon --sample    # 키 없이 샘플 대본으로 렌더링 테스트
  python -m gtoon.main publish --dir output/2026-11-10/morning --base-url https://...
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import yaml

from . import characters, compose
from .photos import get_photo
from .news import fetch_news

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KST = timezone(timedelta(hours=9))
HIST = os.path.join(ROOT, "data", "history.json")


def load_cfg() -> dict:
    with open(os.path.join(ROOT, "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_hist() -> list:
    if os.path.exists(HIST):
        with open(HIST, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_hist(h: list):
    os.makedirs(os.path.dirname(HIST), exist_ok=True)
    with open(HIST, "w", encoding="utf-8") as f:
        json.dump(h[-300:], f, ensure_ascii=False, indent=1)


def build_caption(s: dict, cfg: dict) -> str:
    src = s.get("source", {})
    tags = " ".join(t if t.startswith("#") else "#" + t for t in s.get("hashtags", [])[:20])
    return (f"{s.get('caption', '').strip()}\n\n"
            f"💬 {s.get('question', '')}\n\n"
            f"📰 참고: {src.get('source', '')} 등 {src.get('n_sources', '여러')}개 언론 보도 종합\n"
            f"📷 배경 사진: {', '.join(c.replace('Photo: ', '') for c in s.get('photo_credits', [])) or '-'}\n"
            f"🎨 진행자 캐릭터는 AI로 만든 일러스트입니다.\n\n{tags}")[:2200]


def cmd_make(args, cfg):
    now = datetime.now(KST)
    out = os.path.join(ROOT, "output", now.strftime("%Y-%m-%d"), args.slot)
    os.makedirs(out, exist_ok=True)
    for old in glob.glob(os.path.join(out, "*.jpg")):   # 같은 슬롯 재실행 시 이전 이미지 정리
        os.remove(old)
    hist = load_hist()

    if args.sample:
        with open(os.path.join(ROOT, "assets", "sample_script.json"), encoding="utf-8") as f:
            script = json.load(f)
    else:
        from .script import build_script
        items = fetch_news(cfg, cfg["slots"][args.slot]["categories"])
        used = {h.get("link") for h in hist}
        items = [i for i in items if i.link not in used]
        if not items:
            print("[make] SKIP: 검증·필터를 통과한 뉴스 없음")
            return
        print(f"[make] 후보 {len(items)}건, 1위: {items[0].title}")
        recent = [h["title"] for h in hist[-20:]]
        try:
            script = build_script(cfg, args.slot, items, recent)
        except ValueError as e:          # 검증 통과 이슈 없음 → 이번 회차 게시 생략(정상 종료)
            print(f"[make] SKIP: {e}")
            return

    with open(os.path.join(out, "script.json"), "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=1)

    n_body = min(cfg["comic"]["panels"], cfg["comic"].get("max_images", 6) - 2)
    panels = script["panels"] = script["panels"][:n_body]
    total = len(panels) + 2
    tag = script.get("category_tag", "이슈")
    files = []

    # 진행자 표정·동작 이미지가 비어 있으면 1회 생성 (Cloudflare + rembg 필요)
    if characters.missing_poses() and os.environ.get("CF_API_TOKEN"):
        try:
            characters.build_missing(cfg)
        except Exception as e:
            print(f"[char] 동작 생성 건너뜀: {e}")

    # 배경 사진 (Pexels 무료 라이선스)
    W, H = cfg["comic"]["width"], cfg["comic"]["height"]
    used: set = set()
    prov = cfg.get("photos", {}).get("provider", "pixabay")
    cover = get_photo(script.get("cover_photo") or panels[0].get("photo", []), used, (W, H), prov)
    pics = [get_photo(p.get("photo", []), used, (W, H), prov) for p in panels]
    sources = [cover.source] + [p.source for p in pics]

    pages = [compose.render_cover(cover, script, cfg, total)]
    pages += [compose.render_panel(ph, p, cfg, tag, i + 2, total) for i, (ph, p) in enumerate(zip(pics, panels))]
    pages.append(compose.render_outro(script, cfg, total, total))
    for i, pg in enumerate(pages, 1):
        fn = os.path.join(out, f"{i:02d}.jpg")
        pg.convert("RGB").save(fn, "JPEG", quality=cfg["comic"]["jpeg_quality"], optimize=True)
        files.append(os.path.relpath(fn, ROOT).replace("\\", "/"))
    script["photo_credits"] = sorted({p.credit for p in [cover, *pics] if p.credit})

    caption = build_caption(script, cfg)
    with open(os.path.join(out, "caption.txt"), "w", encoding="utf-8") as f:
        f.write(caption)
    meta = {"slot": args.slot, "created": now.isoformat(), "files": files,
            "photo_sources": sources, "photo_urls": [p.url for p in [cover, *pics]],
            "title": script["topic_title"],
            "publishable": sources.count("fallback") <= 1}
    with open(os.path.join(out, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    if not args.sample:
        hist.append({"date": now.strftime("%Y-%m-%d"), "slot": args.slot,
                     "title": script["topic_title"], "link": script["source"]["link"],
                     "dir": os.path.relpath(out, ROOT).replace("\\", "/"), "status": "made"})
        save_hist(hist)
    print(f"[make] 완료 → {out} ({len(files)}장, 사진: {sources})")
    # GitHub Actions 다음 단계로 경로 전달
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"dir={os.path.relpath(out, ROOT)}\n")


def cmd_publish(args, cfg):
    from .instagram import publish_carousel
    d = os.path.join(ROOT, args.dir)
    with open(os.path.join(d, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    with open(os.path.join(d, "caption.txt"), encoding="utf-8") as f:
        caption = f.read()
    if not meta.get("publishable", False):
        sys.exit(f"[publish] 배경 사진을 충분히 구하지 못해 게시하지 않습니다: {meta.get('photo_sources')}")
    urls = [f"{args.base_url.rstrip('/')}/{p}" for p in meta["files"]]
    media_id = publish_carousel(urls, caption, cfg)
    hist = load_hist()
    for h in reversed(hist):
        if h.get("dir") == args.dir.replace("\\", "/"):
            h.update(status="published", media_id=media_id)
            break
    save_hist(hist)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make"); m.add_argument("--slot", required=True); m.add_argument("--sample", action="store_true")
    p = sub.add_parser("publish"); p.add_argument("--dir", required=True); p.add_argument("--base-url", required=True)
    args = ap.parse_args()
    cfg = load_cfg()
    {"make": cmd_make, "publish": cmd_publish}[args.cmd](args, cfg)


if __name__ == "__main__":
    main()
