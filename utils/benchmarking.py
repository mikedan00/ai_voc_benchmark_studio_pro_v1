"""Competitive benchmarking, public VOC search, spec comparison, and markdown report helpers.

This module intentionally avoids Streamlit-specific code so it can be tested from VS Code
and reused by the Streamlit Cloud app.
"""
from __future__ import annotations

import html
import json
import re
import time
from collections import Counter
from datetime import datetime
from io import BytesIO
from typing import Callable, Iterable, Any
from urllib.parse import parse_qsl, quote_plus, urlencode, urlparse, urlunparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

try:  # Optional but used when installed.
    from duckduckgo_search import DDGS
except Exception:  # pragma: no cover
    DDGS = None  # type: ignore

try:
    import PyPDF2
except Exception:  # pragma: no cover
    PyPDF2 = None  # type: ignore

try:
    from docx import Document as DocxDocument
except Exception:  # pragma: no cover
    DocxDocument = None  # type: ignore

LLMFn = Callable[[str, str, int, float], str]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.6",
}

DEFAULT_GUIDE = {
    "title": "벤치마킹 보고서 표준 작성 가이드 v2.0",
    "summary": "경쟁사 비교 분석을 위한 데이터 기반 벤치마킹 보고서 작성 기준",
    "main_sections": [
        {"id": "1", "name": "경영진 요약", "items": ["핵심 발견사항", "전략적 시사점", "액션 아이템"], "criteria": ["명확성", "실행가능성", "비즈니스 임팩트"]},
        {"id": "2", "name": "분석 범위 및 방법론", "items": ["분석 목적", "대상 제품", "수집 소스", "분석 기간"], "criteria": ["객관성", "데이터 신뢰성"]},
        {"id": "3", "name": "제품/시장 포지셔닝 비교", "items": ["제품 포트폴리오", "가격 전략", "타깃 고객", "브랜드 포지션"], "criteria": ["시장성", "차별성"]},
        {"id": "4", "name": "고객 VOC 분석", "items": ["만족도", "불만", "개선 요청", "칭찬 포인트"], "criteria": ["감성", "빈도", "심각도"]},
        {"id": "5", "name": "사양 및 기능 비교", "items": ["기능 매트릭스", "성능", "가격 대비 가치", "생태계"], "criteria": ["기능 완성도", "혁신성", "사용자 가치"]},
        {"id": "6", "name": "갭 분석 및 전략", "items": ["차별화 강점", "기능 갭", "위협", "기회"], "criteria": ["모방 난이도", "전략 우선순위"]},
        {"id": "7", "name": "로드맵 및 권고사항", "items": ["단기", "중기", "장기", "KPI"], "criteria": ["ROI", "난이도", "리스크"]},
    ],
    "scoring_dimensions": ["기능성", "성능", "가격경쟁력", "고객만족도", "혁신성", "지원/서비스"],
    "scoring_scale": "1~10점 척도. 10점은 압도적 우위, 5점은 시장 평균, 1점은 중대한 열위.",
    "data_sources": ["웹 리뷰", "뉴스", "커뮤니티", "공식 스펙", "사용자 업로드 문서"],
    "analysis_methods": ["VOC 감성 분석", "사양 매트릭스", "SWOT", "갭 분석", "우선순위 매트릭스"],
}

VOC_CATEGORY_KEYWORDS = {
    "성능/속도": ["성능", "속도", "버벅", "렉", "느림", "딜레이", "최적화", "performance", "lag", "slow"],
    "배터리/발열": ["배터리", "방전", "충전", "발열", "뜨거", "온도", "battery", "charging", "heat", "overheat"],
    "카메라/화질": ["카메라", "사진", "동영상", "줌", "화질", "야간", "camera", "photo", "video", "zoom"],
    "디스플레이/디자인": ["디스플레이", "화면", "밝기", "주사율", "무게", "디자인", "display", "screen", "design", "weight"],
    "가격/가성비": ["가격", "비싸", "가성비", "할인", "요금", "price", "expensive", "value", "cost"],
    "소프트웨어/UI": ["ui", "ux", "업데이트", "버그", "앱", "소프트웨어", "software", "update", "bug", "crash"],
    "내구성/품질": ["고장", "불량", "파손", "스크래치", "품질", "내구", "defect", "durability", "broken"],
    "A/S/고객지원": ["as", "a/s", "서비스센터", "교환", "환불", "상담", "support", "warranty", "refund"],
    "호환성/생태계": ["호환", "연동", "액세서리", "생태계", "compatibility", "ecosystem", "accessory"],
    "보안/개인정보": ["보안", "개인정보", "프라이버시", "security", "privacy"],
}
POSITIVE_WORDS = ["좋", "만족", "추천", "훌륭", "빠르", "선명", "편하", "예쁘", "강력", "개선", "최고", "good", "great", "excellent", "satisfied", "recommend", "fast", "clear", "better", "best"]
NEGATIVE_WORDS = ["불만", "문제", "별로", "나쁘", "실망", "느리", "버벅", "고장", "불량", "비싸", "아쉽", "최악", "발열", "bad", "issue", "problem", "poor", "slow", "defect", "broken", "expensive", "disappoint", "overheat", "bug"]
REQUEST_WORDS = ["개선", "요청", "바라", "필요", "해결", "추가", "지원", "원함", "should", "need", "wish", "request", "fix", "improve"]


def clean_text(text: Any) -> str:
    text = html.unescape(str(text or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def safe_json(text: str) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            return None
    return None


def normalize_url(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        query = [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if not (k.lower().startswith("utm_") or k.lower() in {"fbclid", "gclid", "mc_cid", "mc_eid", "igshid"})
        ]
        netloc = parsed.netloc.lower().replace("www.", "")
        path = parsed.path.rstrip("/")
        return urlunparse((parsed.scheme or "https", netloc, path, "", urlencode(query), ""))
    except Exception:
        return url.strip()


def get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def infer_channel(domain: str, title: str = "") -> str:
    blob = f"{domain} {title}".lower()
    if any(x in blob for x in ["youtube", "youtu.be"]):
        return "동영상"
    if any(x in blob for x in ["news", "zdnet", "etnews", "chosun", "hankyung", "mk.co.kr", "yna", "theverge", "engadget"]):
        return "뉴스/미디어"
    if any(x in blob for x in ["blog", "tistory", "naver.com", "medium"]):
        return "블로그/후기"
    if any(x in blob for x in ["reddit", "quora", "dcinside", "clien", "ppomppu", "ruliweb", "fmkorea", "community", "forum"]):
        return "커뮤니티"
    if any(x in blob for x in ["coupang", "amazon", "bestbuy", "danawa", "11st", "gmarket", "shopping"]):
        return "쇼핑/리뷰"
    return "웹"


def infer_voc_category(text: str) -> str:
    t = str(text or "").lower()
    scores: dict[str, int] = {}
    for cat, kws in VOC_CATEGORY_KEYWORDS.items():
        scores[cat] = sum(t.count(k.lower()) for k in kws)
    best, score = max(scores.items(), key=lambda x: x[1])
    return best if score > 0 else "기타"


def infer_sentiment(text: str) -> tuple[str, int]:
    t = str(text or "").lower()
    pos = sum(t.count(w.lower()) for w in POSITIVE_WORDS)
    neg = sum(t.count(w.lower()) for w in NEGATIVE_WORDS)
    req = sum(t.count(w.lower()) for w in REQUEST_WORDS)
    if req and neg:
        return "개선요청", neg - pos + req
    if pos > neg:
        return "긍정", pos - neg
    if neg > pos:
        return "부정", neg - pos
    if pos and neg:
        return "혼합", 0
    return "중립", 0


def build_voc_queries(company: str, product: str, depth: str = "standard") -> list[str]:
    base = clean_text(" ".join([company, product])).strip()
    if not base:
        base = clean_text(company or product or "제품")
    q = [
        f"{base} 후기 불만 문제",
        f"{base} 장점 단점 리뷰",
        f"{base} 개선 요청 VOC",
        f"{base} 발열 배터리 카메라 성능 문제",
    ]
    if depth in {"standard", "deep"}:
        q.extend([
            f"{base} 커뮤니티 실사용 후기",
            f"{base} 뉴스 이슈 업데이트 버그",
            f"{base} reddit review problem",
        ])
    if depth == "deep":
        q.extend([
            f"{base} service center defect complaint",
            f"{base} comparison user review",
            f"{base} forum battery camera performance bug",
        ])
    seen, out = set(), []
    for item in q:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def ddg_search(query: str, n: int = 8, region: str = "kr-kr", timelimit: str | None = None) -> list[dict]:
    if DDGS is None:
        return []
    try:
        with DDGS() as ddgs:
            kwargs = {"max_results": n, "region": region, "safesearch": "moderate"}
            if timelimit:
                kwargs["timelimit"] = timelimit
            results = list(ddgs.text(query, **kwargs))
        time.sleep(0.25)
        return [dict(r) for r in results]
    except TypeError:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=n, region=region))
            time.sleep(0.25)
            return [dict(r) for r in results]
        except Exception:
            return []
    except Exception:
        return []


def ddg_news_search(query: str, n: int = 8, region: str = "kr-kr", timelimit: str | None = "m") -> list[dict]:
    if DDGS is None:
        return []
    try:
        with DDGS() as ddgs:
            results = list(ddgs.news(query, max_results=n, region=region, safesearch="moderate", timelimit=timelimit))
        time.sleep(0.25)
        return [
            {
                "title": r.get("title", ""),
                "href": r.get("url") or r.get("href", ""),
                "body": r.get("body") or r.get("excerpt", ""),
                "date": r.get("date", ""),
                "source_type": "DDG News",
            }
            for r in results
        ]
    except Exception:
        return []


def google_news_rss(query: str, n: int = 8) -> list[dict]:
    url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=ko&gl=KR&ceid=KR:ko"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "xml")
        items = []
        for it in soup.find_all("item")[:n]:
            items.append({
                "title": clean_text(it.title.text if it.title else ""),
                "href": it.link.text if it.link else "",
                "body": clean_text(it.description.text if it.description else ""),
                "date": clean_text(it.pubDate.text if it.pubDate else ""),
                "source_type": "Google News RSS",
            })
        time.sleep(0.2)
        return items
    except Exception:
        return []


def fetch_page_excerpt(url: str, max_chars: int = 1600) -> str:
    if not url or re.search(r"\.(pdf|zip|docx?|xlsx?|pptx?)(\?|$)", url, re.I):
        return ""
    try:
        res = requests.get(url, headers=HEADERS, timeout=8)
        ctype = res.headers.get("content-type", "")
        if "text/html" not in ctype and "application/xhtml" not in ctype:
            return ""
        soup = BeautifulSoup(res.text[:350_000], "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()
        article = soup.find("article") or soup.find("main") or soup.body
        paragraphs = [clean_text(p.get_text(" ")) for p in article.find_all("p")[:12]] if article else []
        text = " ".join(p for p in paragraphs if len(p) > 30)
        return text[:max_chars]
    except Exception:
        return ""


def enrich_voc_items(raw_items: list[dict], company: str, product: str, fetch_pages: bool = False) -> list[dict]:
    seen_url, seen_title, enriched = set(), set(), []
    target_terms = [x for x in [company, product] if x]
    for item in raw_items:
        href = item.get("href") or item.get("url") or ""
        norm = normalize_url(href)
        title = clean_text(item.get("title", ""))
        body = clean_text(item.get("body") or item.get("snippet") or item.get("excerpt") or "")
        title_key = re.sub(r"\W+", "", title.lower())[:80]
        if not title and not body:
            continue
        if norm and norm in seen_url:
            continue
        if title_key and title_key in seen_title:
            continue
        if norm:
            seen_url.add(norm)
        if title_key:
            seen_title.add(title_key)
        excerpt = fetch_page_excerpt(href) if fetch_pages else ""
        full_text = clean_text(" ".join([title, body, excerpt]))
        domain = get_domain(href)
        category = infer_voc_category(full_text)
        sentiment, polarity = infer_sentiment(full_text)
        relevance = sum(full_text.lower().count(t.lower()) for t in target_terms if t)
        relevance += 2 if category != "기타" else 0
        relevance += 1 if sentiment in {"부정", "개선요청", "혼합"} else 0
        relevance += min(len(full_text) // 300, 3)
        enriched.append({
            "source": item.get("source_type", "DDG Web"),
            "title": title,
            "content": full_text[:2400] or body,
            "url": href,
            "href": href,
            "normalized_url": norm,
            "source_domain": domain,
            "channel": infer_channel(domain, title),
            "source_type": item.get("source_type", "DDG Web"),
            "date": item.get("date", ""),
            "body": body,
            "excerpt": excerpt,
            "text": full_text[:2400],
            "category": category,
            "sentiment": {"긍정": "positive", "부정": "negative", "개선요청": "negative", "혼합": "mixed", "중립": "neutral"}.get(sentiment, "neutral"),
            "sentiment_hint": sentiment,
            "polarity_score": polarity,
            "relevance_score": relevance,
            "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
    enriched.sort(key=lambda x: (x["relevance_score"], len(x.get("text", ""))), reverse=True)
    return enriched


def collect_public_voc(
    company: str,
    product: str,
    n_per_query: int = 8,
    sources: list[str] | None = None,
    depth: str = "standard",
    fetch_pages: bool = False,
    region: str = "kr-kr",
    timelimit: str | None = None,
) -> list[dict]:
    sources = sources or ["web", "news", "rss"]
    queries = build_voc_queries(company, product, depth)
    raw: list[dict] = []
    for q in queries:
        if "web" in sources:
            raw.extend({**r, "source_type": "DDG Web", "query": q} for r in ddg_search(q, n_per_query, region=region, timelimit=timelimit))
        if "news" in sources:
            raw.extend({**r, "query": q} for r in ddg_news_search(q, max(3, n_per_query // 2), region=region, timelimit=timelimit or "m"))
        if "rss" in sources:
            raw.extend({**r, "query": q} for r in google_news_rss(q, max(3, n_per_query // 2)))
    return enrich_voc_items(raw, company, product, fetch_pages=fetch_pages)


def summarize_voc_locally(items: Iterable[Any]) -> dict:
    rows = [to_dict_any(x) for x in items]
    category_counter = Counter(x.get("category", "기타") or "기타" for x in rows)
    sentiment_counter = Counter(x.get("sentiment_hint") or x.get("sentiment") or "neutral" for x in rows)
    source_counter = Counter(x.get("source") or x.get("source_type") or x.get("channel") or "unknown" for x in rows)
    negative_items = [x for x in rows if (x.get("sentiment_hint") in {"부정", "혼합", "개선요청"} or x.get("sentiment") in {"negative", "mixed"})]
    positive_items = [x for x in rows if (x.get("sentiment_hint") == "긍정" or x.get("sentiment") == "positive")]
    return {
        "voc_count": len(rows),
        "category_distribution": dict(category_counter.most_common()),
        "sentiment_distribution": dict(sentiment_counter.most_common()),
        "source_distribution": dict(source_counter.most_common()),
        "top_issue_categories": [k for k, _ in category_counter.most_common(5)],
        "sample_negative_titles": [x.get("title", "") for x in negative_items[:8]],
        "sample_positive_titles": [x.get("title", "") for x in positive_items[:8]],
    }


def to_dict_any(item: Any) -> dict:
    if hasattr(item, "to_dict"):
        try:
            return item.to_dict()
        except Exception:
            return dict(item.__dict__)
    if isinstance(item, dict):
        return item
    return dict(getattr(item, "__dict__", {}))


def collect_specs(company: str, product: str, n: int = 6) -> list[dict]:
    queries = [
        f"{company} {product} 제품 사양 스펙 specification",
        f"{company} {product} 기능 비교 성능",
        f"{company} {product} official features datasheet",
    ]
    results: list[dict] = []
    for q in queries:
        results.extend(ddg_search(q, n))
    return results


def extract_pdf(data: bytes) -> str:
    if PyPDF2 is None:
        return ""
    try:
        reader = PyPDF2.PdfReader(BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages[:40])
    except Exception:
        return ""


def extract_docx(data: bytes) -> str:
    if DocxDocument is None:
        return ""
    try:
        doc = DocxDocument(BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception:
        return ""


def build_guide_from_texts(texts: list[str], llm_generate: LLMFn | None = None) -> dict:
    combined = "\n\n━━ 문서 구분 ━━\n\n".join(texts[:15])
    if len(combined) > 12000:
        combined = combined[:12000] + "\n...[토큰 제한으로 생략됨]"
    if not combined.strip() or llm_generate is None:
        return DEFAULT_GUIDE.copy()
    system = "당신은 벤치마킹 보고서 전문 컨설턴트입니다. 여러 보고서를 분석하여 표준 가이드를 JSON으로 추출합니다. 반드시 순수 JSON만 출력하세요."
    prompt = f"""아래는 여러 벤치마킹 보고서의 내용입니다. 공통 패턴을 분석해 표준 작성 가이드를 추출하세요.

[보고서 내용]
{combined}

다음 JSON 스키마로 정확히 출력하세요. 마크다운 없이 JSON만 출력하세요:
{{
  "title": "벤치마킹 보고서 표준 작성 가이드 v2.0",
  "summary": "한 문장 요약",
  "main_sections": [{{"id":"1","name":"섹션명","items":["핵심항목1"],"criteria":["평가기준1"]}}],
  "scoring_dimensions": ["차원1","차원2"],
  "scoring_scale": "평가 척도 설명",
  "data_sources": ["출처1","출처2"],
  "analysis_methods": ["방법1","방법2"]
}}"""
    raw = llm_generate(prompt, system, 3000, 0.1)
    parsed = safe_json(raw)
    if isinstance(parsed, dict) and "main_sections" in parsed:
        return parsed
    guide = DEFAULT_GUIDE.copy()
    guide["llm_notes"] = raw
    return guide


def analyze_voc(company: str, product: str, items: list[Any], llm_generate: LLMFn | None = None) -> dict:
    if not items:
        return {"error": "VOC 데이터 없음", "company": company, "product": product, "voc_count": 0}
    rows = [to_dict_any(x) for x in items]
    local_summary = summarize_voc_locally(rows)
    if llm_generate is None:
        return {
            "company": company,
            "product": product,
            "voc_count": len(rows),
            "overall_sentiment": max(local_summary["sentiment_distribution"], key=local_summary["sentiment_distribution"].get) if rows else "N/A",
            "satisfaction_score": "N/A",
            "confidence": "하",
            "category_distribution": local_summary["category_distribution"],
            "sentiment_distribution": local_summary["sentiment_distribution"],
            "source_distribution": local_summary["source_distribution"],
            "top_positives": local_summary["sample_positive_titles"],
            "top_negatives": local_summary["sample_negative_titles"],
            "improvement_requests": [],
            "trending_topics": local_summary["top_issue_categories"],
            "issue_matrix": [],
            "mode": "rule-based fallback",
        }
    snippets = "\n".join(
        f"[{i+1}] 제목: {r.get('title','')}\n"
        f"채널: {r.get('channel','') or r.get('source','')} / 분류: {r.get('category','')} / 감성: {r.get('sentiment_hint') or r.get('sentiment','')}\n"
        f"내용: {(r.get('text') or r.get('content') or r.get('body') or '')[:700]}\nURL: {r.get('href') or r.get('url','')}"
        for i, r in enumerate(rows[:45])
    )
    system = "당신은 CX, 제품기획, VOC 데이터 분석 전문가입니다. 반드시 순수 JSON으로만 답변하세요."
    prompt = f"""다음은 '{company} {product}'에 대한 웹/뉴스/커뮤니티 기반 VOC 후보 데이터입니다.
홍보성 글과 뉴스가 섞일 수 있으므로 실제 사용자 불만·칭찬·개선 요구를 우선 추출하세요.

[로컬 1차 통계]
{json.dumps(local_summary, ensure_ascii=False, indent=2)}

[VOC 후보 원문]
{snippets}

다음 JSON 스키마로 분석 결과를 출력하세요:
{{
  "company": "{company}",
  "product": "{product}",
  "voc_count": {len(rows)},
  "overall_sentiment": "긍정/부정/보통/혼합",
  "satisfaction_score": 7.5,
  "confidence": "상/중/하",
  "category_distribution": {{"카테고리": 0}},
  "sentiment_distribution": {{"긍정": 0, "중립": 0, "부정": 0, "개선요청": 0}},
  "top_positives": ["강점1", "강점2", "강점3"],
  "top_negatives": ["약점1", "약점2", "약점3"],
  "key_features_praised": ["칭찬기능1"],
  "key_features_criticized": ["비판기능1"],
  "improvement_requests": ["개선요청1"],
  "trending_topics": ["이슈1"],
  "issue_matrix": [{{"issue":"이슈명", "category":"분류", "severity":"상/중/하", "frequency":"상/중/하", "business_impact":"영향", "recommended_action":"권고 액션"}}],
  "competitor_implication": "벤치마킹 관점의 시사점",
  "notable_snippets": ["핵심 근거 요약1"]
}}"""
    raw = llm_generate(prompt, system, 3000, 0.1)
    result = safe_json(raw)
    if isinstance(result, dict):
        result.setdefault("category_distribution", local_summary["category_distribution"])
        result.setdefault("sentiment_distribution", local_summary["sentiment_distribution"])
        result.setdefault("source_distribution", local_summary["source_distribution"])
        result.setdefault("voc_count", len(rows))
        return result
    fallback = summarize_voc_locally(rows)
    return {"raw": raw, **fallback, "company": company, "product": product, "confidence": "하"}


def compare_specs(my_co: str, my_prod: str, comp_co: str, comp_prod: str, my_text: str, comp_text: str, llm_generate: LLMFn | None = None) -> dict:
    if llm_generate is None:
        return {
            "overall_summary": "AI 연결 전에는 정량 비교를 수행하지 않았습니다. 입력된 사양 텍스트를 확인하세요.",
            "overall_winner": "분석 필요",
            "spec_matrix": [],
            "my_strengths": [],
            "comp_strengths": [],
            "my_unique_only": [],
            "comp_unique_only": [],
            "my_gaps": [],
            "comp_gaps": [],
            "differentiation_score": {},
            "strategic_recommendation": "HF Router 연결 후 비교 분석을 실행하세요.",
        }
    system = "당신은 IT 제품 분석 전문가입니다. 두 제품을 객관적으로 비교해 순수 JSON으로만 출력하세요."
    prompt = f"""다음 두 제품의 정보를 비교 분석해주세요.

[자사: {my_co} – {my_prod}]
{my_text[:4000] if my_text else '직접 입력된 사양 없음'}

[경쟁사: {comp_co} – {comp_prod}]
{comp_text[:4000] if comp_text else '직접 입력된 사양 없음'}

다음 JSON으로 출력하세요:
{{
  "overall_summary": "한 문장 종합 비교",
  "overall_winner": "{my_co} 우위 / {comp_co} 우위 / 동등",
  "spec_matrix": [{{"category":"카테고리","my_value":"자사 사양","comp_value":"경쟁사 사양","winner":"{my_co}/{comp_co}/동등","importance":"상/중/하","note":"비고"}}],
  "my_strengths": ["자사강점1"],
  "comp_strengths": ["경쟁사강점1"],
  "my_unique_only": ["자사고유기능1"],
  "comp_unique_only": ["경쟁사고유기능1"],
  "my_gaps": ["자사부족영역1"],
  "comp_gaps": ["경쟁사부족영역1"],
  "differentiation_score": {{"functionality":{{"my":7,"comp":8}},"performance":{{"my":8,"comp":7}},"price_value":{{"my":7,"comp":6}},"innovation":{{"my":8,"comp":9}},"customer_support":{{"my":7,"comp":7}}}},
  "strategic_recommendation": "전략적 권고사항"
}}"""
    raw = llm_generate(prompt, system, 3500, 0.1)
    result = safe_json(raw)
    return result if isinstance(result, dict) else {"raw": raw}


def generate_benchmark_report(
    guide: dict,
    my_co: str,
    my_prod: str,
    comp_co: str,
    comp_prod: str,
    my_voc: dict,
    comp_voc: dict,
    spec_comp: dict,
    llm_generate: LLMFn | None = None,
    model_id: str = "",
) -> str:
    today = datetime.now().strftime("%Y년 %m월 %d일")
    if llm_generate is None:
        return fallback_benchmark_report(guide, my_co, my_prod, comp_co, comp_prod, my_voc, comp_voc, spec_comp, model_id=model_id)
    guide_str = json.dumps(guide or DEFAULT_GUIDE, ensure_ascii=False)[:2500]
    my_voc_s = json.dumps(my_voc or {}, ensure_ascii=False)[:2500]
    comp_voc_s = json.dumps(comp_voc or {}, ensure_ascii=False)[:2500]
    spec_s = json.dumps(spec_comp or {}, ensure_ascii=False)[:3000]
    system = "당신은 McKinsey 수준의 전략 컨설턴트입니다. 데이터 기반 벤치마킹 보고서를 한국어 마크다운으로 작성합니다."
    prompt = f"""아래 데이터를 바탕으로 완전한 벤치마킹 보고서를 작성하세요.

## 메타 정보
- 자사: {my_co} ({my_prod})
- 경쟁사: {comp_co} ({comp_prod})
- 보고서 작성일: {today}

## 작성 가이드
{guide_str}

## VOC 분석 데이터
- 자사 VOC: {my_voc_s}
- 경쟁사 VOC: {comp_voc_s}

## 제품 사양 비교 데이터
{spec_s}

아래 구조로 전문 보고서를 작성하세요. 구체적 비교표, 실행 우선순위, KPI, 리스크를 포함하세요.

# 📊 벤치마킹 보고서: {my_co} vs {comp_co}
**작성일:** {today} | **대상 제품:** {my_prod} vs {comp_prod}

## 1. 경영진 요약
## 2. 분석 범위 및 방법론
## 3. 기업/제품 포지셔닝 비교
## 4. 고객 VOC 심층 분석
## 5. 제품 사양 및 성능 비교
## 6. 차별화 강점·약점·갭 분석
## 7. SWOT 분석
## 8. 전략적 권고사항
## 9. 30/90/180일 실행 로드맵
## 10. 결론

*생성 모델: {model_id}*"""
    return llm_generate(prompt, system, 4096, 0.12)


def fallback_benchmark_report(guide: dict, my_co: str, my_prod: str, comp_co: str, comp_prod: str, my_voc: dict, comp_voc: dict, spec_comp: dict, model_id: str = "rule-based") -> str:
    today = datetime.now().strftime("%Y년 %m월 %d일")
    guide = guide or DEFAULT_GUIDE
    return f"""# 📊 벤치마킹 보고서: {my_co or '자사'} vs {comp_co or '경쟁사'}

**작성일:** {today}  
**대상 제품:** {my_prod or '-'} vs {comp_prod or '-'}  
**생성 모드:** {model_id or 'rule-based fallback'}

## 1. 경영진 요약
- 현재 보고서는 AI 연결 없이 생성된 기본 보고서입니다.
- VOC 수집 결과, 사양 비교 결과, 업로드 가이드를 기반으로 1차 구조를 구성했습니다.
- HF Router 연결 후 `LLM 기반 보고서 생성`을 실행하면 전략 권고와 KPI가 더 정교해집니다.

## 2. 작성 가이드 요약
- 가이드: {guide.get('title', '-')}
- 핵심 평가 차원: {', '.join(guide.get('scoring_dimensions', []))}
- 분석 방법: {', '.join(guide.get('analysis_methods', []))}

## 3. VOC 요약
### {my_co or '자사'}
```json
{json.dumps(my_voc or {}, ensure_ascii=False, indent=2)[:2500]}
```

### {comp_co or '경쟁사'}
```json
{json.dumps(comp_voc or {}, ensure_ascii=False, indent=2)[:2500]}
```

## 4. 사양 비교 요약
```json
{json.dumps(spec_comp or {}, ensure_ascii=False, indent=2)[:3000]}
```

## 5. 권고사항
1. VOC 상위 부정 카테고리를 기준으로 개선 우선순위를 정하십시오.
2. 사양 비교 매트릭스에서 경쟁 열위 항목을 단기 개선 과제로 전환하십시오.
3. 고객 만족도 개선 KPI를 제품/서비스/AS 단위로 분리하십시오.
"""


def safe_filename(value: str, fallback: str = "benchmarking_report") -> str:
    value = clean_text(value or "")
    value = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", value).strip("._-")
    return value[:120] or fallback


def rows_to_csv_bytes(items: Iterable[Any]) -> bytes:
    rows = [to_dict_any(x) for x in items]
    if not rows:
        return b""
    return pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig")
