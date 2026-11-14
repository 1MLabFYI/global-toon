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
        info = _call("GET", f"{base}/{cid}", fields="status_code,status", access_token=token)
        st = info.get("status_code")
        if st == "FINISHED":
            print(f"[ig] container {cid} 처리 완료: {info.get('status', '')}")
            return
        if st in ("ERROR", "EXPIRED"):
            raise IGError(f"container {cid} status={st} detail={info.get('status', '')}")
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


def _upload_resumable(base: str, uid: str, token: str, path: str, caption: str, cover_url: str | None) -> str:
    """영상 파일을 인스타 서버(rupload)에 직접 업로드 — URL로 가져가는 방식보다 안정적."""
    params = dict(media_type="REELS", upload_type="resumable", caption=caption[:2200],
                  share_to_feed="true", access_token=token)
    if cover_url:
        params["cover_url"] = cover_url
    c = _call("POST", f"{base}/{uid}/media", **params)
    uri = c.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{base.rsplit('/', 1)[-1]}/{c['id']}"
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        r = requests.post(uri, data=f, timeout=300, headers={
            "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)})
    if r.status_code >= 400:
        raise IGError(f"업로드 실패 {r.status_code} {r.text[:300]}")
    print(f"[ig] 영상 직접 업로드 완료 ({size / 1e6:.1f}MB) → container {c['id']}")
    return c["id"]


def _publish(base: str, uid: str, token: str, cid: str, tries: int = 3) -> str:
    last = None
    for attempt in range(tries):
        time.sleep(20 + attempt * 30)          # FINISHED 직후 바로 게시하면 실패하는 경우가 있어 잠시 대기
        try:
            return _call("POST", f"{base}/{uid}/media_publish", creation_id=cid, access_token=token)["id"]
        except IGError as e:
            last = e
            print(f"[ig] 게시 실패({attempt + 1}/{tries}): {e}")
    raise last


def publish_reel(video_url: str, cover_url: str, caption: str, cfg: dict, local_path: str | None = None,
                 simple_path: str | None = None) -> str:
    """릴스 게시. 시도 순서: ①직접 업로드 ②직접 업로드(단순 인코딩본) ③URL 방식. 모두 실패하면 예외."""
    token = os.environ.get("IG_ACCESS_TOKEN")
    uid = os.environ.get("IG_USER_ID")
    if not (token and uid):
        raise IGError("IG_ACCESS_TOKEN / IG_USER_ID 환경변수가 없습니다.")
    base = _base(cfg)
    attempts = []
    if local_path and os.path.exists(local_path):
        attempts.append(("직접 업로드", lambda: _upload_resumable(base, uid, token, local_path, caption, cover_url)))
    if simple_path and os.path.exists(simple_path):
        attempts.append(("직접 업로드·단순 인코딩", lambda: _upload_resumable(base, uid, token, simple_path, caption, None)))
    attempts.append(("URL 방식", lambda: _call("POST", f"{base}/{uid}/media", media_type="REELS", video_url=video_url,
                                               caption=caption[:2200], share_to_feed="true",
                                               access_token=token)["id"]))
    last = None
    for name, make in attempts:
        try:
            cid = make()
            print(f"[ig] [{name}] container {cid}")
            _wait(base, cid, token)
            pid = _publish(base, uid, token, cid, tries=2)
            print(f"[ig] published reel id {pid} ({name})")
            return pid
        except Exception as e:
            last = e
            print(f"[ig] [{name}] 실패: {e}")
    raise IGError(f"릴스 게시 실패: {last}")


def refresh_token(cfg: dict) -> str:
    """Instagram Login 장기 토큰(60일) 갱신 — 24시간 이상 지난 토큰만 가능."""
    token = os.environ["IG_ACCESS_TOKEN"]
    if cfg["instagram"]["api"] != "instagram_login":
        raise IGError("facebook_login 방식은 시스템 사용자 토큰(만료 없음) 사용을 권장합니다.")
    data = _call("GET", "https://graph.instagram.com/refresh_access_token",
                 grant_type="ig_refresh_token", access_token=token)
    return data["access_token"]
