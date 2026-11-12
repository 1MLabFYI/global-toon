"""이슈 선정 + 유머 웹툰 대본 작성 → 2차 팩트체크(별도 호출) → 실패 시 다른 이슈로 재시도."""
from __future__ import annotations

import json

from .llm import ask_json
from .news import NewsItem

SYSTEM = """너는 인스타그램 뉴스툰 '{account}'의 작가다.
두 명의 진행자가 오늘의 뉴스를 실제 사진 배경 위에서 말풍선 대화로 쉽고 재미있게 설명한다.
- {m_name}(남, 뉴스 신문을 든 기자): {m_char}
- {f_name}(여, 마이크를 든 앵커): {f_char}
독자는 20~40대 한국인. 3초 만에 이해되어야 한다. 가벼운 소식은 두 사람의 티키타카로 웃기게, 무거운 소식은 차분하고 친절한 해설로.
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
   - 오늘 많이 보도된 주요 뉴스(정치·외교·통상·경제·사회·기술·문화 모두 가능)
   - 여러 언론사 보도로 사실관계가 분명한 것
   - 제외: 사망·사고·재난 희생, 전쟁 참상, 범죄·성범죄, 미확인 의혹, 정당 간 공방
   - 정치·외교 뉴스를 고르면 사실과 각 측 입장만 중립적으로 전달하고, 누구도 평가·조롱하지 않는다
   조건을 만족하는 후보가 없으면 "selected_index": -1.
2) 본문 {n}컷 대본을 쓴다. 각 컷 = 배경 사진 1장 + 진행자 대사 1~2개.
   흐름: 1컷 무슨 일? → 2~3컷 핵심 사실과 배경(왜 화제?) → 마지막 컷 의미·전망 + 재치 있는 마무리.
   - 사실 정보는 '후보 뉴스'에 적힌 내용만 쓴다. 숫자·날짜·이름을 새로 만들지 않는다.
   - 한 컷의 첫 대사가 뉴스 설명(정보), 두 번째 대사는 상대의 짧은 리액션·드립(선택).
   - 두 진행자가 컷마다 번갈아 설명한다.

pose 선택지: explain(설명), point(가리키기), surprised(놀람), laugh(웃음), think(생각), worried(난감), thumbsup(최고), shrug(글쎄)

JSON 형식:
{{
  "selected_index": 정수,
  "topic_title": "표지 제목, 16자 이내, 재치있게",
  "hook": "표지 부제, 25자 이내",
  "category_tag": "국내|세계|경제|테크|과학|문화|스포츠 중 하나",
  "cover_photo": ["표지 배경 사진 영어 검색어(구체적)", "더 일반적인 검색어"],
  "panels": [
    {{
      "photo": ["배경 사진 영어 검색어 2~4단어(장소·사물·풍경 위주, 인물 얼굴이 주인공인 사진 피하기)", "더 일반적인 대체 검색어"],
      "lines": [
        {{"who": "M|F", "pose": "위 선택지 중 하나", "text": "설명 대사 55자 이내"}},
        {{"who": "M|F", "pose": "위 선택지 중 하나", "text": "리액션 20자 이내"}}
      ]
    }}
  ],
  "facts": ["대본에 쓴 사실 주장 목록 — 각각 후보 뉴스의 어느 문장에 근거하는지 괄호로 표시"],
  "summary": ["3줄 요약, 각 28자 이내", "...", "..."],
  "question": "가벼운 댓글 유도 질문",
  "caption": "인스타 본문 350자 이내, 줄바꿈, 이모지 2~4개",
  "hashtags": ["#해시태그 12~16개"]
}}
panels는 정확히 {n}개, 각 컷 lines 1~2개."""

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
    ch = cfg["characters"]
    return SYSTEM.format(
        account=cfg["account"]["name"],
        m_name=ch["M"]["name"], m_char=ch["M"]["personality"],
        f_name=ch["F"]["name"], f_char=ch["F"]["personality"],
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
                               candidates=_cand_text(pool), n=n)
        data = ask_json(prompt, cfg, _system(cfg))
        if isinstance(data, list):
            data = data[0]
        idx = int(data.get("selected_index", -1))
        if not 0 <= idx < len(pool):
            raise ValueError("조건(교차검증·제외주제)을 만족하는 이슈가 없어 이번 회차는 건너뜁니다.")
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
