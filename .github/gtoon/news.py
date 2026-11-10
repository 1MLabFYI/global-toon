"""무료 RSS에서 뉴스를 모으고 ①교차보도 검증 ②민감주제 필터 ③화제성 점수를 매긴다."""
from __future__ import annotations

import html
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

UA = {"User-Agent": "Mozilla/5.0 (GlobalToonBot)"}


@dataclass
class NewsItem:
    title: str
    source: str
    link: str
    category: str
    published: datetime | None
    summary: str = ""
    related_titles: list[str] = field(default_factory=list)
    sources: set[str] = field(default_factory=set)   # 같은 이슈를 보도한 서로 다른 언론사
    score: float = 0.0

    @property
    def n_sources(self) -> int:
        return len(self.sources)

    def brief(self) -> dict:
        return {
            "title": self.title, "source": self.source, "link": self.link,
            "category": self.category, "n_sources": self.n_sources,
            "sources": sorted(self.sources)[:8],
            "summary": self.summary[:300], "related_titles": self.related_titles[:6],
        }


def _strip(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def _parse_feed(xml_text: str, category: str, limit: int) -> list[NewsItem]:
    items: list[NewsItem] = []
    root = ET.fromstring(xml_text)
    for it in root.iter("item"):
        title = _strip(it.findtext("title", ""))
        link = (it.findtext("link") or "").strip()
        src_el = it.find("source")
        source = _strip(src_el.text) if src_el is not None and src_el.text else ""
        desc_raw = html.unescape(it.findtext("description", "") or "")
        if not source and " - " in title:
            title, source = title.rsplit(" - ", 1)
        elif source and title.endswith(" - " + source):
            title = title[: -len(" - " + source)]
        if not source:
            source = "BBC" if "bbc" in link else "unknown"
        # Google News 설명: <li><a>제목</a>&nbsp;<font>언론사</font></li> 목록 = 같은 이슈의 타 매체 보도
        related_titles, sources = [], {source}
        for li in re.findall(r"<li>(.*?)</li>", desc_raw, re.S):
            a = re.search(r"<a[^>]*>(.*?)</a>", li, re.S)
            f = re.search(r"<font[^>]*>(.*?)</font>", li, re.S)
            if a:
                related_titles.append(_strip(a.group(1)))
            if f:
                sources.add(_strip(f.group(1)))
        pub = None
        try:
            pub = parsedate_to_datetime(it.findtext("pubDate", ""))
        except Exception:
            pass
        items.append(NewsItem(
            title=title.strip(), source=source, link=link, category=category, published=pub,
            summary=_strip(desc_raw) if not related_titles else "",
            related_titles=related_titles, sources=sources))
        if len(items) >= limit:
            break
    return items


def _tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[가-힣]{2,}|[A-Za-z]{3,}", s.lower())}


def is_sensitive(item: NewsItem, keywords: list[str]) -> str | None:
    text = (item.title + " " + " ".join(item.related_titles)).lower()
    for k in keywords:
        k = k.lower()
        if k.isascii():                       # 영어는 단어 단위(war ≠ award)
            if re.search(rf"\b{re.escape(k)}\b", text):
                return k
        elif k in text:
            return k
    return None


def fetch_news(cfg: dict, categories: list[str]) -> list[NewsItem]:
    ncfg = cfg["news"]
    out: list[NewsItem] = []
    for cat in categories:
        for url in ncfg["feeds"].get(cat, []):
            try:
                r = requests.get(url, headers=UA, timeout=20)
                r.raise_for_status()
                out += _parse_feed(r.text, cat, ncfg["max_items_per_feed"])
            except Exception as e:
                print(f"[news] feed fail {url}: {e}")
            time.sleep(0.5)
    return rank(out, cfg)


def rank(items: list[NewsItem], cfg: dict) -> list[NewsItem]:
    ncfg, scfg = cfg["news"], cfg["safety"]
    now = datetime.now(timezone.utc)
    fresh = [i for i in items if not i.published or
             (now - i.published).total_seconds() <= ncfg.get("lookback_hours", 30) * 3600]

    # 다른 피드에 실린 같은 이슈(키워드 2개 이상 겹침)의 언론사도 교차보도로 합산
    toks = [_tokens(i.title + " " + " ".join(i.related_titles)) for i in fresh]
    for a, ia in enumerate(fresh):
        for b, ib in enumerate(fresh):
            if a != b and len(toks[a] & toks[b]) >= 3:
                ia.sources |= {ib.source}

    kept = []
    for it in fresh:
        hit = is_sensitive(it, scfg.get("avoid_keywords", []))
        if hit:
            print(f"[news] 민감주제 제외({hit}): {it.title}")
            continue
        if it.n_sources < ncfg.get("min_sources", 3):
            continue                                     # 교차보도 부족 → 검증 불충분
        age_h = ((now - it.published).total_seconds() / 3600) if it.published else 12
        it.score = it.n_sources * 2 + max(0, 24 - age_h) / 6
        kept.append(it)
    kept.sort(key=lambda x: x.score, reverse=True)

    seen, uniq = [], []
    for it in kept:
        t = _tokens(it.title)
        if any(len(t & s) >= max(2, len(t) // 2) for s in seen):
            continue
        seen.append(t)
        uniq.append(it)
    print(f"[news] 수집 {len(items)} → 검증·필터 통과 {len(uniq)}")
    return uniq
