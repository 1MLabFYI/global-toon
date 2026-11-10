"""이슈 선정 + 유머 웹툰 대본 작성 → 2차 팩트체크(별도 호출) → 실패 시 다른 이슈로 재시도."""
from __future__ import annotations

import json

from .llm import ask_json
from .news import NewsItem

SYSTEM = """너는 인스타그램 웹툰 '{account}'의 개그 웹툰 작가다.
해설 캐릭터 '{mascot}'(지구 모양 머리의 귀엽고 엉뚱한 캐릭터)가 오늘의 화제를 가볍고 웃기게 소개한다.
독자는 20~40대 한국인. 출퇴근길에 3초 만에 이해되고 피식 웃을 수 있어야 한다.
반드시 지킬 규칙:
{rules}
다음 주제는 절대 선택하지 않는다: {skips}
출력은 JSON 하나만."""

PROMPT = """[오늘 슬롯] {slot_label}
[최근 게시 주제 — 같은 사건 금지] {recent}

[후보 뉴스 — 여러 언론사가 교차 보도해 검증된 순]
{candidates}

할 일:
1) 후보 중 아래 조건을 모두 만족하는 이슈 1개를 고른다.
   - 논쟁·갈등 소지가 적은 것 (정치·젠더·종교·지역·세대 갈등, 사건사고, 소송, 전쟁 제외)
   - 여러 언론사 보도로 사실관계가 분명한 것
   - 웃기게 풀 수 있는 생활·경제·과학·기술·문화·스포츠·신기한 세계 소식
   조건을 만족하는 후보가 없으면 "selected_index": -1.
2) 본문 {n}컷 개그 웹툰 대본을 쓴다.
   흐름: 1컷 상황(무슨 일?) → 중간 컷 핵심 정보를 생활 비유로 → 마지막 컷 반전/펀치라인.
   - 사실 정보는 '후보 뉴스'에 적힌 내용만 쓴다. 숫자·날짜·이름을 새로 만들지 않는다.
   - 웃음은 과장된 표정, 생활 비유, 지구톤의 엉뚱한 반응으로 만든다. 누군가를 조롱하지 않는다.

JSON 형식:
{{
  "selected_index": 정수,
  "topic_title": "표지 제목, 16자 이내, 재치있게",
  "hook": "표지 부제, 25자 이내",
  "category_tag": "국내|세계|경제|테크|과학|문화|스포츠 중 하나",
  "panels": [
    {{
      "scene": "영어 이미지 프롬프트. 등장인물 1~2명, 동작 1개, 단순한 배경, 과장된 웃긴 표정. 실존 인물·로고·국기·글자 금지. 인물은 역할로만(e.g. 'a chubby office worker').",
      "narration": "컷 하단 해설, 60자 이내",
      "bubbles": [{{"speaker": "{mascot} 또는 등장인물 역할", "text": "말풍선 24자 이내", "side": "left|right"}}]
    }}
  ],
  "facts": ["대본에 쓴 사실 주장 목록 — 각각 후보 뉴스의 어느 문장에 근거하는지 괄호로 표시"],
  "summary": ["3줄 요약, 각 28자 이내", "...", "..."],
  "question": "가벼운 댓글 유도 질문",
  "caption": "인스타 본문 350자 이내, 줄바꿈, 이모지 2~4개",
  "hashtags": ["#해시태그 12~16개"]
}}
panels는 정확히 {n}개, 각 컷 bubbles 0~2개."""

VERIFY = """너는 깐깐한 팩트체커이자 리스크 검토자다. 아래 [근거]만을 사실로 인정한다.

[근거 — 여러 언론사 보도 제목]
{evidence}

[웹툰 대본]
{script}

검토 항목:
1. 대본의 사실 주장(숫자, 날짜, 주체, 결과)이 근거에 없거나 다르면 문제.
2. 논쟁·갈등 소지(정치 편향, 특정 집단 비하, 피해자 희화화, 확인 안 된 의혹)가 있으면 문제.
3. 실존 인물을 특정하거나 조롱하면 문제.
문제가 경미하면 해당 문장을 고쳐 fixed_panels/fixed_summary/fixed_caption에 넣는다(수정 없으면 null).

JSON: {{"verdict": "pass|fix|reject", "issues": ["..."],
 "fixed_panels": null 또는 panels 배열 전체, "fixed_summary": null 또는 배열, "fixed_caption": null 또는 문자열}}"""


def _system(cfg):
    return SYSTEM.format(
        account=cfg["account"]["name"], mascot=cfg["account"]["mascot_name"],
        rules="\n".join("- " + r for r in cfg["safety"]["rules"]),
        skips=", ".join(cfg["safety"]["skip_topics"]))


def _cand_text(cands: list[NewsItem]) -> str:
    return "\n".join(
        f"[{i}] ({c.category}, {c.n_sources}개 언론사 보도: {', '.join(sorted(c.sources)[:5])}) {c.title}"
        + (f"\n     관련 보도: {' / '.join(c.related_titles[:4])}" if c.related_titles else "")
        + (f"\n     요약: {c.summary[:200]}" if c.summary else "")
        for i, c in enumerate(cands))


def verify(script: dict, src: NewsItem, cfg: dict) -> dict | None:
    evidence = "\n".join(f"- {t}" for t in [src.title, *src.related_titles[:8]] if t)
    if src.summary:
        evidence += f"\n- {src.summary[:300]}"
    body = {k: script.get(k) for k in ("topic_title", "hook", "panels", "summary", "caption")}
    res = ask_json(VERIFY.format(evidence=evidence, script=json.dumps(body, ensure_ascii=False)),
                   cfg, "출력은 JSON 하나만.")
    if isinstance(res, list):
        res = res[0]
    v = res.get("verdict", "reject")
    print(f"[verify] {v} {res.get('issues')}")
    if v == "reject":
        return None
    if v == "fix":
        if res.get("fixed_panels"):
            script["panels"] = res["fixed_panels"]
        if res.get("fixed_summary"):
            script["summary"] = res["fixed_summary"]
        if res.get("fixed_caption"):
            script["caption"] = res["fixed_caption"]
    script["verify"] = {"verdict": v, "issues": res.get("issues", [])}
    return script


def build_script(cfg: dict, slot: str, items: list[NewsItem], recent: list[str]) -> dict:
    s = cfg["slots"][slot]
    n = cfg["comic"]["panels"]
    pool = items[:15]
    for attempt in range(cfg["safety"].get("max_attempts", 2)):
        if not pool:
            break
        prompt = PROMPT.format(slot_label=s["label"], recent=json.dumps(recent[-20:], ensure_ascii=False),
                               candidates=_cand_text(pool), n=n, mascot=cfg["account"]["mascot_name"])
        data = ask_json(prompt, cfg, _system(cfg))
        if isinstance(data, list):
            data = data[0]
        idx = int(data.get("selected_index", -1))
        if not 0 <= idx < len(pool):
            raise ValueError("조건(검증·비논쟁)을 만족하는 이슈가 없어 이번 회차는 건너뜁니다.")
        src = pool[idx]
        data["panels"] = (data.get("panels") or [])[:n]
        if len(data["panels"]) < 3:
            pool.pop(idx); continue
        checked = verify(data, src, cfg)
        if checked:
            checked["panels"] = checked["panels"][:n]
            checked["source"] = src.brief()
            return checked
        print(f"[script] 팩트체크 탈락 → 다른 이슈로 재시도: {src.title}")
        pool.pop(idx)
    raise ValueError("팩트체크를 통과한 대본이 없어 이번 회차는 건너뜁니다.")
