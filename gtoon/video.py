"""릴스 영상 제작 — 장면 이미지(1080x1920)들을 천천히 확대(켄번스) + 부드러운 전환 + 배경음악으로 MP4 합성.

ffmpeg는 pip 패키지 imageio-ffmpeg에 들어 있는 실행 파일을 사용(별도 설치 불필요).
"""
from __future__ import annotations

import glob
import json
import os
import random
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MUSIC_DIR = os.path.join(ROOT, "assets", "music")


def ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def scene_durations(script: dict, cfg: dict) -> list[float]:
    """대사 길이에 맞춰 장면별 노출 시간 계산(읽을 시간 확보)."""
    r = cfg["reels"]
    out = [r["cover_sec"]]
    for p in script["panels"]:
        chars = sum(len(l.get("text", "")) for l in p.get("lines", []))
        out.append(min(r["max_sec"], max(r["min_sec"], r["base_sec"] + chars * r["sec_per_char"])))
    out.append(r["outro_sec"])
    return out


def pick_music(mood: str, recent: list[str]) -> str | None:
    """assets/music/<분위기>_*.mp3 중 최근에 안 쓴 곡을 무작위 선택. 없으면 아무 곡이나."""
    files = sorted(glob.glob(os.path.join(MUSIC_DIR, f"{mood}_*.mp3"))) or \
        sorted(glob.glob(os.path.join(MUSIC_DIR, "*.mp3")))
    if not files:
        return None
    fresh = [f for f in files if os.path.basename(f) not in recent[-3:]] or files
    return random.choice(fresh)


def make_reel(images: list[str], durations: list[float], music: str | None, out_path: str, cfg: dict) -> float:
    r = cfg["reels"]
    W, H, fps, xf = cfg["comic"]["width"], cfg["comic"]["height"], r["fps"], r["transition_sec"]
    args = [ffmpeg_exe(), "-y", "-loglevel", "error"]
    for img in images:
        args += ["-i", img]
    if music:
        args += ["-stream_loop", "-1", "-i", music]
    else:
        args += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]

    parts = []
    for i, d in enumerate(durations):
        frames = int(round((d + xf) * fps))
        zoom = r["zoom"] if i % 2 == 0 else r["zoom"] * 0.8
        # 2배 확대 후 zoompan → 떨림 없는 부드러운 확대
        parts.append(
            f"[{i}:v]scale={W * 2}:{H * 2},zoompan=z='min(zoom+{zoom / frames:.6f},{1 + zoom})'"
            f":d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={fps},"
            f"setsar=1,format=yuv420p[v{i}]")
    last, offset = "v0", 0.0
    for i in range(1, len(images)):
        offset += durations[i - 1]
        parts.append(f"[{last}][v{i}]xfade=transition={r['transition']}:duration={xf}:offset={offset:.3f}[x{i}]")
        last = f"x{i}"
    total = sum(durations) + xf
    a = len(images)
    parts.append(f"[{a}:a]atrim=0:{total:.3f},asetpts=PTS-STARTPTS,volume={r['music_volume']},"
                 f"afade=t=in:d=0.6,afade=t=out:st={max(0, total - 1.8):.3f}:d=1.8[a]")
    args += ["-filter_complex", ";".join(parts), "-map", f"[{last}]", "-map", "[a]",
             "-t", f"{total:.3f}", "-r", str(fps),
             "-c:v", "libx264", "-preset", "medium", "-crf", str(r["crf"]), "-maxrate", "8M", "-bufsize", "16M",
             "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1",
             # 인스타 릴스 권장: 닫힌 GOP, 2초 간격 키프레임, 고정 프레임레이트
             "-g", str(fps * 2), "-keyint_min", str(fps * 2), "-sc_threshold", "0",
             "-flags", "+cgop", "-fps_mode", "cfr",
             "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
             "-movflags", "+faststart", out_path]
    subprocess.run(args, check=True)
    return total


def music_credit(path: str | None) -> str:
    """assets/music/credits.json 에 곡별 출처가 있으면 캡션에 표기."""
    if not path:
        return ""
    try:
        with open(os.path.join(MUSIC_DIR, "credits.json"), encoding="utf-8") as f:
            return json.load(f).get(os.path.basename(path), "")
    except Exception:
        return ""
