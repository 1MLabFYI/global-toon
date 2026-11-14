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
tok, uid = (os.environ.get("IG_ACCESS_TOKEN") or "").strip(), (os.environ.get("IG_USER_ID") or "").strip()
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
        # Cloudflare는 진행자 표정 생성(최초 1회)에만 쓰므로 실패해도 경고만 표시
        msg = "오늘 무료 한도 소진(매일 09:00 KST 초기화)" if "429" in str(e) else str(e)[:200]
        print(f"⚠️ Cloudflare {m}: {msg}")

# 3) 배경 사진 (Pixabay 기본)
prov = cfg.get("photos", {}).get("provider", "pixabay")
if prov == "pixabay":
    k = os.environ.get("PIXABAY_API_KEY")
    if k:
        px = requests.get("https://pixabay.com/api/", params={"key": k.strip(), "q": "coffee", "per_page": 3},
                          timeout=30)
        print("✅ Pixabay 키" if px.status_code == 200 else f"❌ Pixabay: {px.status_code} {px.text[:200]}")
        ok = ok and px.status_code == 200
    else:
        print("❌ Pixabay: PIXABAY_API_KEY 비밀값 없음"); ok = False
else:
    k = os.environ.get("PEXELS_API_KEY")
    px = requests.get("https://api.pexels.com/v1/search", params={"query": "coffee", "per_page": 1},
                      headers={"Authorization": (k or "").strip()}, timeout=30)
    print("✅ Pexels 키" if px.status_code == 200 else f"❌ Pexels: {px.status_code} {px.text[:200]}")
    ok = ok and px.status_code == 200

# 4) Gemini
key = os.environ.get("GEMINI_API_KEY")
if key:
    g = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                     headers={"x-goog-api-key": key}, timeout=30)
    print("✅ Gemini 키" if g.status_code == 200 else f"❌ Gemini: {g.status_code} {g.text[:200]}")
    ok = ok and g.status_code == 200

sys.exit(0 if ok else "일부 점검 실패 — 위 ❌ 메시지를 확인하세요.")
