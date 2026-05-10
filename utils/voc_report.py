"""
utils/voc_report.py

VOC를 요약하고 정리한 뒤 인사이트·권고사항 중심의 Markdown 리포트로 만드는 보조 모듈.
LLM이 연결되지 않은 상황에서도 최소한의 통계/대표 VOC 기반 리포트를 생성할 수 있도록
결정론적 fallback 리포트 함수를 제공한다.
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter, defaultdict
from typing import Any, Iterable


def _get(obj: Any, key: str, default: Any = "") -> Any:
    if hasattr(obj, "to_dict"):
        try:
            return obj.to_dict().get(key, default)
        except Exception:
            pass
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _clean(text: Any, limit: int | None = None) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if limit and len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


def _item_to_dict(item: Any) -> dict[str, str]:
    return {
        "title": _clean(_get(item, "title", ""), 180),
        "content": _clean(_get(item, "content", ""), 500),
        "source": _clean(_get(item, "source", "unknown"), 80) or "unknown",
        "category": _clean(_get(item, "category", "기타"), 80) or "기타",
        "sentiment": _clean(_get(item, "sentiment", "neutral"), 40) or "neutral",
        "url": _clean(_get(item, "url", ""), 240),
    }


def build_voc_report_payload(voc_items: Iterable[Any], max_examples: int = 100) -> dict[str, Any]:
    """LLM 리포트 프롬프트에 넣기 좋은 압축 VOC payload를 만든다."""
    rows = [_item_to_dict(v) for v in list(voc_items or [])]
    category_counts = Counter(r["category"] for r in rows)
    sentiment_counts = Counter(r["sentiment"] for r in rows)
    source_counts = Counter(r["source"] for r in rows)

    examples_by_category: dict[str, list[dict[str, str]]] = defaultdict(list)
    negative_examples: list[dict[str, str]] = []
    for r in rows:
        short = {
            "title": r["title"],
            "summary": _clean(r["content"] or r["title"], 220),
            "source": r["source"],
            "sentiment": r["sentiment"],
        }
        if len(examples_by_category[r["category"]]) < 8:
            examples_by_category[r["category"]].append(short)
        if r["sentiment"].lower() in {"negative", "neg", "부정"} and len(negative_examples) < 20:
            negative_examples.append(short)

    top_categories = [
        {"category": k, "count": v, "ratio_pct": round(v / max(len(rows), 1) * 100, 1)}
        for k, v in category_counts.most_common(12)
    ]
    top_sources = [
        {"source": k, "count": v, "ratio_pct": round(v / max(len(rows), 1) * 100, 1)}
        for k, v in source_counts.most_common(12)
    ]

    return {
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_voc": len(rows),
        "category_counts": dict(category_counts.most_common()),
        "sentiment_counts": dict(sentiment_counts.most_common()),
        "source_counts": dict(source_counts.most_common()),
        "negative_ratio_pct": round(
            sum(v for k, v in sentiment_counts.items() if str(k).lower() in {"negative", "neg", "부정"})
            / max(len(rows), 1)
            * 100,
            1,
        ),
        "top_categories": top_categories,
        "top_sources": top_sources,
        "examples_by_category": dict(examples_by_category),
        "negative_examples": negative_examples,
        "sample_rows": rows[:max_examples],
    }


def fallback_voc_report_markdown(
    voc_items: Iterable[Any],
    *,
    product_target: str = "갤럭시",
    analysis: dict[str, Any] | None = None,
    rag_context: str = "",
    model_label: str = "Rule-based fallback",
) -> str:
    """AI 연결이 없거나 실패한 경우에도 다운로드 가능한 기본 Markdown 리포트를 생성한다."""
    payload = build_voc_report_payload(voc_items)
    total = payload["total_voc"]
    cats = payload["top_categories"]
    srcs = payload["top_sources"]
    sents = payload["sentiment_counts"]
    lines: list[str] = []
    lines.append(f"# {product_target} VOC 요약·인사이트 리포트")
    lines.append("")
    lines.append(f"- 생성일: {payload['created_at']}")
    lines.append(f"- 분석 모델/방식: {model_label}")
    lines.append(f"- 전체 VOC: {total:,}건")
    lines.append(f"- 부정 VOC 비율: {payload['negative_ratio_pct']}%")
    lines.append("")
    lines.append("## 1. Executive Summary")
    if analysis and isinstance(analysis, dict) and analysis.get("executive_summary"):
        lines.append(str(analysis.get("executive_summary")))
    else:
        top = cats[0]["category"] if cats else "확인 필요"
        lines.append(f"전체 {total:,}건의 VOC를 기준으로 보면 가장 많이 반복된 카테고리는 `{top}`입니다. 부정 VOC 비율은 {payload['negative_ratio_pct']}%로 집계되었습니다. 아래 리포트는 카테고리·감성·출처 분포와 대표 발화를 기반으로 우선 점검할 이슈와 실행 권고를 정리합니다.")
    lines.append("")
    lines.append("## 2. 핵심 테마")
    if cats:
        for i, row in enumerate(cats[:8], 1):
            lines.append(f"{i}. **{row['category']}** — {row['count']}건, {row['ratio_pct']}%")
    else:
        lines.append("- 아직 분류 가능한 VOC가 없습니다.")
    lines.append("")
    lines.append("## 3. 정량 신호")
    lines.append("### 3.1 감성 분포")
    for k, v in sents.items():
        lines.append(f"- {k}: {v}건")
    lines.append("### 3.2 출처 분포")
    for row in srcs[:8]:
        lines.append(f"- {row['source']}: {row['count']}건 ({row['ratio_pct']}%)")
    lines.append("")
    lines.append("## 4. 대표 VOC")
    examples = payload["negative_examples"] or payload["sample_rows"][:12]
    for i, ex in enumerate(examples[:12], 1):
        title = ex.get("title") or ex.get("summary", "")
        summary = ex.get("summary") or ex.get("content", "")
        lines.append(f"> {i}. {title} — {summary}")
    lines.append("")
    lines.append("## 5. 인사이트")
    if analysis and isinstance(analysis, dict) and analysis.get("key_insights"):
        for x in analysis.get("key_insights", [])[:10]:
            lines.append(f"- {x}")
    else:
        lines.append("- 반복 빈도가 높은 카테고리는 제품 개선 로드맵의 1차 후보입니다.")
        lines.append("- 부정 VOC가 집중되는 카테고리는 CS 비용, 브랜드 신뢰, 재구매 의향에 직접 영향을 줄 수 있습니다.")
        lines.append("- 출처별 VOC 편차가 크면 특정 커뮤니티의 과대표집 가능성을 함께 검토해야 합니다.")
    lines.append("")
    lines.append("## 6. 실행 권고")
    lines.append("- 상위 3개 카테고리에 대해 담당 부서, 재현 조건, 로그 수집 항목을 지정합니다.")
    lines.append("- 부정 VOC 대표 발화를 기준으로 Quick Win 개선안을 2주 단위로 검증합니다.")
    lines.append("- 요구사항은 KPI, 수용 기준, 검증 데이터와 연결해 SRS로 전환합니다.")
    if rag_context:
        lines.append("")
        lines.append("## 7. RAG 근거 요약")
        lines.append("```text")
        lines.append(_clean(rag_context, 2500))
        lines.append("```")
    lines.append("")
    lines.append("## 8. 추가 확인 필요 사항")
    lines.append("- VOC 원문 중복 제거 기준")
    lines.append("- 실제 판매량/사용자 수 대비 이슈 발생률")
    lines.append("- OS/펌웨어/기기 모델별 이슈 분포")
    return "\n".join(lines).strip() + "\n"


def payload_as_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
