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

    last = None
    for model in cfg["llm"]["models"]:
        for attempt in range(3):
            try:
                r = requests.post(API.format(model=model), json=body, timeout=120,
                                  headers={"x-goog-api-key": key})
                if r.status_code == 429:           # 무료 한도 초과 → 다음 모델
                    last = f"{model}: 429 quota"
                    break
                if r.status_code >= 500:
                    last = f"{model}: {r.status_code}"
                    time.sleep(5 * (attempt + 1))
                    continue
                r.raise_for_status()
                data = r.json()
                text = "".join(p.get("text", "") for p in
                               data["candidates"][0]["content"]["parts"])
                print(f"[llm] {model} OK")
                return _extract_json(text)
            except (requests.RequestException, KeyError, json.JSONDecodeError) as e:
                last = f"{model}: {e}"
                time.sleep(3)
    raise LLMError(f"모든 모델 실패 — {last}")
