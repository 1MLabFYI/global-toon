"""인스타그램 공식 API로 캐러셀 게시."""
from __future__ import annotations

import os
import time

import requests


class IGError(RuntimeError):
    pass


def _base(cfg: dict) -> str:
    host = "graph.instagram.com" if cfg["instagram"]["api"] == "instagram_login" else "graph.facebook.com"
    return f"https://{host}/{cfg['instagram']['version']}"


def _call(method: str, url: str, **params) -> dict:
    r = requests.request(method, url, params=params, timeout=60)
    data = r.json() if r.content else {}
    if r.status_code >= 400 or "error" in data:
        raise IGError(f"{r.status_code} {data.get('error', data)}")
    return data


def _wait(base: str, cid: str, token: str, limit_s: int = 600):
    t0 = time.time()
    while time.time() - t0 < limit_s:
        st = _call("GET", f"{base}/{cid}", fields="status_code", access_token=token).get("status_code")
        if st == "FINISHED":
            return
        if st in ("ERROR", "EXPIRED"):
            raise IGError(f"container {cid} status={st}")
        time.sleep(8)
    raise IGError(f"container {cid} 처리 시간 초과")


def publish_carousel(image_urls: list[str], caption: str, cfg: dict) -> str:
    token = os.environ.get("IG_ACCESS_TOKEN")
    uid = os.environ.get("IG_USER_ID")
    if not (token and uid):
        raise IGError("IG_ACCESS_TOKEN / IG_USER_ID 환경변수가 없습니다.")
    base = _base(cfg)
    children = []
    for u in image_urls[:10]:
        c = _call("POST", f"{base}/{uid}/media", image_url=u, is_carousel_item="true", access_token=token)
        children.append(c["id"])
        print(f"[ig] item container {c['id']}")
    for cid in children:
        _wait(base, cid, token)
    car = _call("POST", f"{base}/{uid}/media", media_type="CAROUSEL",
                children=",".join(children), caption=caption[:2200], access_token=token)
    _wait(base, car["id"], token)
    pub = _call("POST", f"{base}/{uid}/media_publish", creation_id=car["id"], access_token=token)
    print(f"[ig] published media id {pub['id']}")
    return pub["id"]


def publish_reel(video_url: str, cover_url: str, caption: str, cfg: dict) -> str:
    """릴스 게시: 영상 컨테이너 생성 → 처리 완료 대기(최대 10분) → 게시. 피드에도 함께 노출."""
    token = os.environ.get("IG_ACCESS_TOKEN")
    uid = os.environ.get("IG_USER_ID")
    if not (token and uid):
        raise IGError("IG_ACCESS_TOKEN / IG_USER_ID 환경변수가 없습니다.")
    base = _base(cfg)
    c = _call("POST", f"{base}/{uid}/media", media_type="REELS", video_url=video_url,
              cover_url=cover_url, caption=caption[:2200], share_to_feed="true", access_token=token)
    print(f"[ig] reel container {c['id']}")
    _wait(base, c["id"], token)
    pub = _call("POST", f"{base}/{uid}/media_publish", creation_id=c["id"], access_token=token)
    print(f"[ig] published reel id {pub['id']}")
    return pub["id"]


def refresh_token(cfg: dict) -> str:
    """Instagram Login 장기 토큰(60일) 갱신 — 24시간 이상 지난 토큰만 가능."""
    token = os.environ["IG_ACCESS_TOKEN"]
    if cfg["instagram"]["api"] != "instagram_login":
        raise IGError("facebook_login 방식은 시스템 사용자 토큰(만료 없음) 사용을 권장합니다.")
    data = _call("GET", "https://graph.instagram.com/refresh_access_token",
                 grant_type="ig_refresh_token", access_token=token)
    return data["access_token"]
