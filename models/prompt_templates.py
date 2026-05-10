"""
models/prompt_templates.py

Galaxy VOC Collector에서 사용하는 개선 프롬프트 템플릿 모음.
사용자가 제시한 '역할 부여 + 구체적 단계 지시 + 입출력 예시' 패턴을
분석/SRS/RAG 시나리오에 맞게 적용한다.
"""

from __future__ import annotations

import json
import time
from typing import Any


PROMPT_PRESETS: dict[str, dict[str, str]] = {
    "expert_pipeline": {
        "label": "1. VOC 분석 전문가 · 단계별 파이프라인 설계",
        "scenario": "시스템 기획 단계에서 전체 VOC 파이프라인 구조와 입출력, 분석 결과를 체계화할 때 사용",
        "expected": "크롤링/파일 업로드/RAG/분류/감성분석/요구사항 생성 단계를 분리하고, 각 단계별 산출물과 검증 기준을 명확하게 제시",
        "instruction": """
당신은 VOC 분석 전문가이자 삼성 Galaxy 제품 요구사항 기획자입니다.
삼성 멤버스, 네이버 카페/지식인, 커뮤니티, 사용자 입력 URL, 업로드 파일에서 수집된 Galaxy 폰 관련 VOC를 분석합니다.
다음 순서로 단계별 사고를 하되, 최종 출력에는 결론과 구조화 결과만 작성하세요.
1) 입력 데이터의 출처·범위·신뢰도를 확인합니다.
2) VOC를 카테고리(배터리, 카메라, 발열, 성능, 통신, 업데이트, UI/UX, AS/고객지원 등)별로 분류합니다.
3) 감성(negative/neutral/positive)과 심각도(치명/높음/중간/낮음)를 판단합니다.
4) 반복 빈도와 사용자 영향도를 기준으로 핵심 문제를 도출합니다.
5) RAG 근거와 업로드 파일 근거를 연결해 기능 요구사항, 비기능 요구사항, KPI, 수용 기준을 생성합니다.
6) 각 요구사항은 근거 VOC와 연결되어야 하며, 추정은 명확히 표시합니다.
각 단계별 필요한 입력/출력 예시를 내부적으로 고려하고, 최종 결과는 명료하고 체계적으로 작성하세요.
""".strip(),
    },
    "issue_classifier": {
        "label": "2. VOC 분류/감성/심각도 분석가",
        "scenario": "VOC가 많고 카테고리, 감성, 심각도, 반복 이슈를 먼저 정확히 분류해야 할 때 사용",
        "expected": "카테고리별 대표 불만, 감성 분포, 심각도, 근본 원인 후보, 우선순위가 정리된 분석 결과",
        "instruction": """
당신은 대규모 VOC 텍스트를 분류하는 데이터 분석가입니다.
입력된 VOC를 카테고리, 감성, 심각도, 반복 패턴, 사용자 영향도 기준으로 정리하세요.
특히 다음 사항을 엄격히 반영하세요.
- 같은 의미의 표현은 하나의 이슈 클러스터로 묶습니다.
- 단순 빈도뿐 아니라 사용 불능, 데이터 손실, 안전, 결제/인증, 통화/연결 문제처럼 영향도가 큰 항목을 높게 평가합니다.
- 각 문제에는 대표 VOC 문장 또는 RAG 근거를 연결합니다.
- 근거가 부족한 항목은 '추가 확인 필요'로 표시합니다.
최종 결과는 제품기획자가 바로 우선순위 회의에 사용할 수 있게 작성하세요.
""".strip(),
    },
    "requirements_engineer": {
        "label": "3. 요구사항 엔지니어 · SRS/수용기준 강화",
        "scenario": "분석 결과를 실제 개발 요구사항, 수용 기준, KPI, 테스트 항목으로 변환할 때 사용",
        "expected": "REQ/NFR ID, 사용자 스토리, Given-When-Then 수용 기준, 정량 KPI, 의존성/리스크가 포함된 요구사항",
        "instruction": """
당신은 모바일 소프트웨어 요구사항 엔지니어입니다.
VOC를 단순 요약하지 말고 개발 가능한 요구사항으로 변환하세요.
각 요구사항은 반드시 다음 요소를 포함해야 합니다.
- 요구사항 ID와 제목
- 사용자 문제와 VOC 근거
- 사용자 스토리
- 기능 범위와 제외 범위
- Given-When-Then 형식의 수용 기준
- 정량 KPI 또는 측정 방법
- 로그/데이터 수집 필요사항
- 의존성, 리스크, 검증 방법
모호한 요구사항은 구체적인 동작 조건과 예외 조건으로 분해하세요.
""".strip(),
    },
    "rag_evidence": {
        "label": "4. RAG 근거 검증 · 출처 기반 답변",
        "scenario": "업로드 파일/URL/수집 VOC의 근거를 바탕으로 답변 신뢰도를 높여야 할 때 사용",
        "expected": "RAG 근거와 결론이 분리되고, 근거 부족/추정/확인 필요 사항이 명확히 표시된 답변",
        "instruction": """
당신은 RAG 기반 VOC 근거 검증 담당자입니다.
제공된 RAG 근거와 VOC 데이터만 우선 사용하세요.
근거에 없는 내용은 사실처럼 말하지 말고 '추정' 또는 '확인 필요'로 표시하세요.
답변은 다음 순서를 따르세요.
1) 근거에서 직접 확인되는 사실
2) 여러 근거를 종합한 해석
3) 요구사항 또는 개선안
4) 근거 부족으로 추가 확인이 필요한 항목
각 결론은 가능한 한 어떤 VOC/RAG 근거에서 나왔는지 연결하세요.
""".strip(),
    },
    "executive_report": {
        "label": "5. 임원 보고/PPT용 요약 · 의사결정 중심",
        "scenario": "PPT, 경영진 보고, 빠른 의사결정용 요약과 로드맵이 필요할 때 사용",
        "expected": "핵심 이슈, 고객 영향, 사업 영향, Quick Win, 로드맵, KPI가 짧고 선명하게 정리된 결과",
        "instruction": """
당신은 Galaxy 제품 임원 보고서를 작성하는 시니어 PM입니다.
기술 세부사항보다 의사결정에 필요한 메시지를 우선하세요.
다음 관점으로 요약하세요.
- 고객 불편의 크기와 긴급도
- 브랜드/재구매/CS 비용에 미치는 영향
- 즉시 개선 가능한 Quick Win
- 단기/중기/장기 로드맵
- 투자 대비 효과가 큰 요구사항
- 경영진이 승인해야 할 결정 사항
문장은 짧고 명확하게 작성하고, 각 결론에는 가능한 정량 KPI를 붙이세요.
""".strip(),
    },
}


DEFAULT_PROMPT_PRESET = "expert_pipeline"


def get_prompt_preset_options() -> list[tuple[str, str]]:
    """Streamlit selectbox 표시용 (key, label) 목록."""
    return [(key, value["label"]) for key, value in PROMPT_PRESETS.items()]


def get_prompt_instruction(preset_key: str, custom_instruction: str = "") -> str:
    preset = PROMPT_PRESETS.get(preset_key) or PROMPT_PRESETS[DEFAULT_PROMPT_PRESET]
    base = preset["instruction"].strip()
    custom = (custom_instruction or "").strip()
    if custom:
        return base + "\n\n[사용자 추가 프롬프트]\n" + custom
    return base


def describe_prompt_preset(preset_key: str) -> dict[str, str]:
    return PROMPT_PRESETS.get(preset_key) or PROMPT_PRESETS[DEFAULT_PROMPT_PRESET]


def build_analysis_prompt(
    *,
    payload: dict[str, Any],
    model_info_str: str,
    rag_context: str = "",
    preset_key: str = DEFAULT_PROMPT_PRESET,
    custom_instruction: str = "",
) -> str:
    instruction = get_prompt_instruction(preset_key, custom_instruction)
    return f"""
[역할/작업 지시]
{instruction}

[분석 대상]
{model_info_str}

[입력 데이터: VOC 압축 스냅샷]
{json.dumps(payload, ensure_ascii=False, indent=2)}

[업로드/RAG 추가 근거]
{rag_context or "추가 근거 없음"}

[중요 규칙]
- 반드시 한국어 JSON 객체 하나만 반환하세요.
- 코드블록, 설명문, markdown은 금지합니다.
- 입력 데이터와 RAG 추가 근거에서 추론 가능한 범위만 사용하세요.
- 근거가 부족한 내용은 "추정" 또는 "추가 확인 필요"로 표시하세요.
- 각 요구사항은 문제-근거-KPI-수용기준이 연결되게 작성하세요.
- 사용자 불편도, 발생 빈도, 사업 영향, 구현 난이도를 함께 고려해 우선순위를 산정하세요.

[출력 스키마]
{{
  "executive_summary": "5~7문장. 총량, 부정비율, 핵심 카테고리, 즉시 조치 포인트 포함",
  "pipeline_design": [
    {{"step":"1. 수집", "input":"", "process":"", "output":"", "example":""}},
    {{"step":"2. 정제/중복 제거", "input":"", "process":"", "output":"", "example":""}},
    {{"step":"3. 분류/감성/심각도", "input":"", "process":"", "output":"", "example":""}},
    {{"step":"4. RAG 근거 검색", "input":"", "process":"", "output":"", "example":""}},
    {{"step":"5. 요구사항 생성", "input":"", "process":"", "output":"", "example":""}}
  ],
  "problem_statements": [
    {{"id":"PS-001","title":"","evidence":"","severity":"치명/높음/중간/낮음","affected_users":"","likely_root_causes":[""]}}
  ],
  "critical_issues": [
    {{"title":"","description":"","frequency":"높음/중간/낮음","impact":"높음/중간/낮음","category":"","evidence_examples":[""]}}
  ],
  "requirements": [
    {{
      "id":"REQ-001",
      "category":"",
      "priority":"필수/권장/선택",
      "title":"",
      "description":"",
      "user_story":"사용자로서 나는 ... 하고 싶다. 왜냐하면 ...",
      "business_value":"",
      "acceptance_criteria":["Given-When-Then 형식 2~4개"],
      "success_metrics":["정량 KPI 1개 이상"],
      "dependencies":[""],
      "risks":[""]
    }}
  ],
  "non_functional_requirements": [
    {{"id":"NFR-001","area":"성능/신뢰성/보안/접근성/운영성","requirement":"","metric":""}}
  ],
  "roadmap": [
    {{"phase":"즉시(0~4주)","items":[""]}},
    {{"phase":"단기(1~3개월)","items":[""]}},
    {{"phase":"중기(3~6개월)","items":[""]}},
    {{"phase":"장기(6개월+)","items":[""]}}
  ],
  "kpis": [{{"name":"","target":"","why":""}}],
  "key_insights": ["최소 4개"],
  "open_questions": ["추가 확인이 필요한 데이터/정책/기술 질문"]
}}
""".strip()


def build_srs_markdown_prompt(
    *,
    payload: dict[str, Any],
    analysis: dict[str, Any],
    product_name: str,
    version: str,
    author: str,
    ai_model: str,
    rag_context: str = "",
    preset_key: str = DEFAULT_PROMPT_PRESET,
    custom_instruction: str = "",
) -> str:
    instruction = get_prompt_instruction(preset_key, custom_instruction)
    return f"""
[역할/작업 지시]
{instruction}

삼성전자 갤럭시 시니어 제품 기획자 겸 요구사항 엔지니어로서 아래 VOC 분석 결과를 바탕으로
실무 검토 가능한 소프트웨어 요구사항명세서(SRS)를 한국어 Markdown으로 작성하세요.

제품명: {product_name}
버전: v{version}
작성자: {author}
작성일: {time.strftime('%Y년 %m월 %d일')}
AI 모델: {ai_model}

[VOC 통계]
{json.dumps(payload, ensure_ascii=False, indent=2)}

[AI 분석 결과]
{json.dumps(analysis, ensure_ascii=False, indent=2)}

[업로드/RAG 근거]
{rag_context or "추가 근거 없음"}

[작성 규칙]
- 반드시 아래 목차를 지키세요.
- 각 요구사항에는 ID, 우선순위, VOC 근거, 사용자 스토리, Given-When-Then 수용 기준, KPI, 리스크를 포함하세요.
- 업로드 파일이나 RAG 검색 결과에서 나온 내용은 "VOC 근거"와 "제약사항 및 가정"에 반영하세요.
- 근거가 부족한 항목은 "추가 확인 필요"로 표시하세요.
- 개발팀/QA팀/기획팀이 바로 리뷰할 수 있게 구체적으로 작성하세요.

# {product_name} VOC 기반 소프트웨어 요구사항명세서 v{version}

## 1. 문서 개요
### 1.1 목적
### 1.2 배경
### 1.3 적용 범위
### 1.4 용어 정의

## 2. VOC 수집 및 분석 파이프라인
### 2.1 수집 채널
### 2.2 입력/출력 구조
### 2.3 정제, 중복 제거, 분류, 감성 분석 방식
### 2.4 RAG 근거 적용 방식

## 3. VOC 수집 및 분석 결과
### 3.1 카테고리별 분포
### 3.2 감성 분포
### 3.3 심각도 및 영향도
### 3.4 핵심 문제 진술

## 4. 제품 개선 목표
### 4.1 사용자 경험 목표
### 4.2 사업 목표
### 4.3 성공 KPI

## 5. 기능 요구사항
각 요구사항을 다음 형식으로 작성:
- 요구사항 ID
- 제목
- 우선순위
- 상세 설명
- VOC 근거
- 사용자 스토리
- 수용 기준
- 성공 지표
- 의존성 및 리스크

## 6. 비기능 요구사항
성능, 신뢰성, 보안, 접근성, 운영성 기준을 정량화하세요.

## 7. 데이터/로그/운영 요구사항
VOC 기반 개선 사항을 추적하기 위한 로그, 대시보드, 알림 기준을 제안하세요.

## 8. 테스트 및 검증 전략
기능 테스트, 회귀 테스트, 사용자 검증, 로그 기반 모니터링 기준을 작성하세요.

## 9. 제약사항 및 가정

## 10. 단계별 로드맵
즉시, 단기, 중기, 장기 단계로 나누세요.

## 11. 검토 및 승인
""".strip()


def build_rag_answer_prompt(question: str, context: str, preset_key: str = "rag_evidence", custom_instruction: str = "") -> str:
    instruction = get_prompt_instruction(preset_key, custom_instruction)
    return f"""
[역할/작업 지시]
{instruction}

아래 RAG 근거만 사용해서 사용자의 질문에 답변하세요.
불확실한 내용은 추정이라고 표시하세요.
답변은 한국어로, 제품기획/요구사항 관점에서 작성하세요.

[질문]
{question}

[RAG 근거]
{context or '검색된 근거 없음'}

[답변 형식]
1. 핵심 답변
2. 근거 요약
3. 요구사항/개선안
4. 확인 필요 사항
""".strip()



def build_voc_insight_report_prompt(
    payload: dict[str, Any],
    model_info_str: str,
    analysis: dict[str, Any] | None = None,
    rag_context: str = "",
    preset_key: str = "executive_report",
    custom_instruction: str = "",
) -> str:
    """VOC 요약·정리·인사이트 추출·보고서 생성을 위한 Markdown 리포트 프롬프트."""
    instruction = get_prompt_instruction(preset_key, custom_instruction)
    return f"""
[역할/작업 지시]
{instruction}

당신은 Galaxy 제품 VOC를 요약하고 제품/사업 인사이트를 도출하는 시니어 PM입니다.
아래 VOC 압축 payload, 기존 AI 분석 결과, RAG 근거를 사용해 경영진과 개발팀이 함께 볼 수 있는 Markdown 리포트를 작성하세요.

[분석 대상]
{model_info_str}

[VOC 압축 payload]
{json.dumps(payload, ensure_ascii=False, indent=2)}

[기존 AI 분석 결과]
{json.dumps(analysis or {}, ensure_ascii=False, indent=2)}

[RAG/업로드 근거]
{rag_context or "추가 근거 없음"}

[작성 규칙]
- 반드시 한국어 Markdown으로 작성하세요.
- 근거가 있는 내용과 추정을 구분하세요.
- 숫자는 payload의 집계값을 우선 사용하세요.
- 대표 VOC 문장은 5~10개만 짧게 인용하세요.
- 단순 요약에 그치지 말고, 제품 기획/품질/CS/로드맵 관점의 인사이트와 실행 권고를 포함하세요.
- 내부 사고 과정은 노출하지 말고 최종 리포트만 작성하세요.

[필수 목차]
# {model_info_str} VOC 요약·인사이트 리포트

## 1. Executive Summary
- 전체 VOC 규모, 부정 비율, 가장 중요한 문제 3가지를 요약

## 2. 핵심 테마별 요약
- 카테고리별 반복 이슈, 고객 영향, 대표 VOC

## 3. 정량 신호
- 카테고리 분포
- 감성 분포
- 출처 분포
- 빈도보다 영향도가 큰 리스크 신호

## 4. 대표 VOC 발화
- 원문 의미를 훼손하지 않는 짧은 대표 발화

## 5. 핵심 인사이트
- Pain Point
- Opportunity
- Risk Signal
- Trend Signal

## 6. 제품/서비스 개선 권고
- Quick Win
- 단기 개선
- 중기 로드맵
- KPI/측정 방법

## 7. 요구사항 후보
- REQ 후보, 우선순위, 근거, 수용 기준 초안

## 8. 추가 확인 필요 사항
- 데이터 부족, 실험/로그/정책 확인 항목
""".strip()
