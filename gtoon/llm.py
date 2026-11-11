"""Google Gemini(무료 티어) REST 호출 — JSON 응답 전용."""
from __future__ import annotations

import json
import os
import re
import time

import requests

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class LLMError(RuntimeError):
    pass


def _extract_json(text: str):
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"[\[{].*[\]}]", text, re.S)
        if m:
            return json.loads(m.group(0))
        raise


def ask_json(prompt: str, cfg: dict, system: str = "") -> dict | list:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise LLMError("GEMINI_API_KEY 환경변수가 없습니다.")
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": cfg["llm"].get("temperature", 0.8),
            "responseMimeType": "application/json",
        },
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}

    errors = []
    for cycle in range(2):                      # 전체 모델을 2바퀴까지 시도 (일시 과부하 대비)
        if cycle:
            print("[llm] 모든 모델 실패 → 90초 후 한 번 더 시도")
            time.sleep(90)
        for model in cfg["llm"]["models"]:
            for attempt in range(3):
                try:
                    r = requests.post(API.format(model=model), json=body, timeout=180,
                                      headers={"x-goog-api-key": key})
                    if r.status_code in (429, 404):     # 무료 한도 초과 / 모델 없음 → 다음 모델
                        errors.append(f"{model}: {r.status_code}")
                        print(f"[llm] {model} {r.status_code} → 다음 모델")
                        break
                    if r.status_code >= 500:            # 구글 서버 과부하(503) → 잠시 후 재시도
                        errors.append(f"{model}: {r.status_code}")
                        print(f"[llm] {model} {r.status_code} 재시도 {attempt + 1}/3")
                        time.sleep(15 * (attempt + 1))
                        continue
                    r.raise_for_status()
                    data = r.json()
                    text = "".join(p.get("text", "") for p in
                                   data["candidates"][0]["content"]["parts"])
                    print(f"[llm] {model} OK")
                    return _extract_json(text)
                except (requests.RequestException, KeyError, IndexError, json.JSONDecodeError) as e:
                    errors.append(f"{model}: {str(e)[:120]}")
                    time.sleep(5)
    raise LLMError("모든 모델 실패 — " + " | ".join(errors[-6:]))
