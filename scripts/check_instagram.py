"""설정 점검 (게시하지 않음) — Instagram 토큰·계정, Cloudflare 그림 모델, Gemini 키를 차례로 확인.
GitHub Actions의 'Check Instagram' 워크플로에서 실행."""
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gtoon import imagegen  # noqa: E402
from gtoon.instagram import _base  # noqa: E402
from gtoon.main import load_cfg  # noqa: E402

cfg = load_cfg()
ok = True

# 1) Instagram
tok, uid = os.environ.get("IG_ACCESS_TOKEN"), os.environ.get("IG_USER_ID")
base = _base(cfg)
r = requests.get(f"{base}/{uid}", params={"fields": "id,username", "access_token": tok}, timeout=30)
if r.status_code == 200:
    print(f"✅ Instagram 연결: @{r.json().get('username')}")
else:
    ok = False
    print(f"❌ Instagram: {r.status_code} {r.text[:300]}")

# 2) Cloudflare — 모델별 작은 그림 1장씩 (뉴런 소모 미미)
small = {**cfg, "image": {**cfg["image"], "width": 256, "height": 256}}
for m in cfg["image"]["models"]:
    if m == "placeholder":
        continue
    try:
        if m.startswith("flux-2"):
            imagegen._flux2(m, "a cartoon cat, 2D comic style", small, 1, None)
        else:
            imagegen._schnell("a cartoon cat, 2D comic style", cfg, 1)
        print(f"✅ Cloudflare {m}")
    except Exception as e:
        print(f"❌ Cloudflare {m}: {e}")
        ok = False if m == cfg["image"]["models"][0] else ok

# 3) Gemini
key = os.environ.get("GEMINI_API_KEY")
if key:
    g = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                     headers={"x-goog-api-key": key}, timeout=30)
    print("✅ Gemini 키" if g.status_code == 200 else f"❌ Gemini: {g.status_code} {g.text[:200]}")
    ok = ok and g.status_code == 200

sys.exit(0 if ok else "일부 점검 실패 — 위 ❌ 메시지를 확인하세요.")
