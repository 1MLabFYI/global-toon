"""인스타그램 장기 토큰 갱신 → GitHub Secret 자동 교체 (refresh-token 워크플로에서 실행).
시스템 사용자 토큰(facebook_login, 만료 없음)이면 아무것도 하지 않고 정상 종료."""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gtoon.instagram import refresh_token  # noqa: E402
from gtoon.main import load_cfg  # noqa: E402

cfg = load_cfg()
if cfg["instagram"]["api"] != "instagram_login":
    print("시스템 사용자 토큰(만료 없음) 사용 중 → 갱신 불필요")
    sys.exit(0)
new = refresh_token(cfg)
print(f"::add-mask::{new}")
subprocess.run(["gh", "secret", "set", "IG_ACCESS_TOKEN", "--body", new], check=True)
print("IG_ACCESS_TOKEN 갱신 완료")
