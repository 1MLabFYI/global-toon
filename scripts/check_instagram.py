"""토큰·계정 ID 연결 확인 (게시하지 않음). GitHub Actions의 'Check Instagram' 워크플로에서 실행."""
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gtoon.instagram import _base  # noqa: E402
from gtoon.main import load_cfg  # noqa: E402

cfg = load_cfg()
tok, uid = os.environ.get("IG_ACCESS_TOKEN"), os.environ.get("IG_USER_ID")
base = _base(cfg)
if not tok:
    sys.exit("IG_ACCESS_TOKEN 비밀값이 없습니다.")
r = requests.get(f"{base}/{uid}", params={"fields": "id,username,media_count", "access_token": tok}, timeout=30)
print("계정 조회:", r.status_code, r.json())
lim = requests.get(f"{base}/{uid}/content_publishing_limit", params={"access_token": tok}, timeout=30)
print("게시 한도:", lim.status_code, lim.json())
if r.status_code != 200:
    sys.exit("연결 실패 — 토큰 권한(instagram_business_content_publish) 또는 IG_USER_ID를 확인하세요.")
print(f"✅ 연결 성공: @{r.json().get('username')}")
