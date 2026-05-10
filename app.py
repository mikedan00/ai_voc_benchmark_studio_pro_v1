"""AI VOC & Benchmark Studio Pro

통합 기능
1. Galaxy VOC 수집: 삼성 Members, 네이버 지식인/카페, DC인사이드, 클리앙, 사용자 URL
2. 공개 웹 VOC 수집: DuckDuckGo Web/News, Google News RSS
3. 업로드 파일 수집: CSV/XLSX/TXT/DOCX → VOC/RAG 청크
4. 경량 RAG 검색/질의응답
5. HF Router 기반 LLM 분석, SRS, VOC 인사이트 리포트
6. 경쟁사 벤치마킹: 가이드 추출, 자사/경쟁사 VOC 비교, 스펙 비교, 전략 보고서
7. Markdown/JSON/CSV/DOCX/PPTX/ZIP 산출물

실행:
  streamlit run app.py
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import time
import zipfile
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env", override=True)

from models.config import DEFAULT_ROUTER_CANDIDATES, SUPPORTED_MODELS, clean_value, load_config
from models.hf_api_engine import api_engine, analyze_voc_api, build_srs_prompt
from models.prompt_templates import (
    DEFAULT_PROMPT_PRESET,
    build_rag_answer_prompt,
    build_voc_insight_report_prompt,
    describe_prompt_preset,
    get_prompt_preset_options,
)
from utils.file_ingestor import parse_uploaded_file
from utils.rag_engine import SimpleRAGIndex, build_context, chunks_from_voc
from utils.voc_collector import collect_all, collect_custom_urls, get_demo_voc
from utils.voc_report import build_voc_report_payload, fallback_voc_report_markdown, payload_as_json
from utils.doc_generator import generate_docx, generate_markdown_docx
from utils.ppt_generator import generate_pptx
from utils.benchmarking import (
    DEFAULT_GUIDE,
    analyze_voc as analyze_benchmark_voc,
    build_guide_from_texts,
    collect_public_voc,
    collect_specs,
    compare_specs,
    extract_docx,
    extract_pdf,
    generate_benchmark_report,
    rows_to_csv_bytes,
    safe_filename,
    summarize_voc_locally,
    to_dict_any,
)
from utils.office_export import markdown_to_docx_bytes, markdown_to_pptx_bytes

st.set_page_config(
    page_title="AI VOC & Benchmark Studio Pro",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
:root { --blue:#1e40af; --sky:#0ea5e9; --violet:#7c3aed; --slate:#0f172a; --muted:#64748b; }
html, body, [class*="css"] {font-family:'Noto Sans KR','Malgun Gothic',system-ui,sans-serif;}
.main .block-container {padding-top:1rem; max-width:1500px;}
.hero-pro {background:linear-gradient(135deg,#07101f 0%,#1428A0 42%,#7C3AED 100%); color:white; padding:28px 30px; border-radius:22px; margin-bottom:18px; box-shadow:0 18px 60px rgba(20,40,160,.28);} 
.hero-pro h1 {margin:0; font-size:32px; font-weight:850; letter-spacing:-.03em;} .hero-pro p {margin:8px 0 0 0; opacity:.84; font-size:15px;}
.badge {display:inline-block; padding:5px 10px; border-radius:999px; background:#eef2ff; color:#1428A0; font-size:12px; font-weight:750; margin-right:5px; margin-bottom:5px;}
.card {border:1px solid #e5e7eb; border-radius:18px; padding:16px; background:#fff; margin-bottom:12px; box-shadow:0 8px 28px rgba(15,23,42,.04);} 
.dark-card {border:1px solid #334155; border-radius:18px; padding:16px; background:linear-gradient(135deg,#0f172a,#111827); color:white; margin-bottom:12px;}
.small {font-size:12px; color:#6b7280;} .kpi-title{font-size:12px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:.04em;} .kpi-value{font-size:28px;font-weight:850;color:#0f172a;}
.voc {border-bottom:1px solid #eef2f7; padding:10px 0;} .voc-title {font-weight:700;} .voc-meta {font-size:12px; color:#64748b; margin:2px 0 3px 0;}
hr {margin:1.2rem 0;} pre {white-space:pre-wrap;}
</style>
""",
    unsafe_allow_html=True,
)

cfg = load_config()

DEFAULTS = {
    "hf_token_val": cfg["hf_token"],
    "hf_router_model": cfg["hf_router_model"],
    "hf_model_candidates_text": "\n".join(cfg["hf_model_candidates"]),
    "max_tokens": cfg["max_tokens"],
    "temperature": cfg["temperature"],
    "engine_ready": False,
    "engine_model": "",
    "engine_label": "",
    "engine_msg": "",
    "router_attempts": [],
    "voc_list": [],
    "public_voc_list": [],
    "community_voc_list": [],
    "stats": {},
    "analysis": None,
    "srs_text": "",
    "voc_report_text": "",
    "uploaded_chunks": [],
    "upload_logs": [],
    "rag_query": "갤럭시 VOC에서 가장 중요한 불편사항과 요구사항은 무엇인가?",
    "rag_hits": [],
    "rag_context": "",
    "rag_answer": "",
    "prompt_preset": DEFAULT_PROMPT_PRESET,
    "custom_prompt_instruction": "",
    "last_docx_path": "",
    "last_pptx_path": "",
    "last_voc_report_docx_path": "",
    "benchmark_guide": DEFAULT_GUIDE.copy(),
    "bench_my_voc_raw": [],
    "bench_comp_voc_raw": [],
    "bench_my_voc_analysis": {},
    "bench_comp_voc_analysis": {},
    "spec_my_raw": "",
    "spec_comp_raw": "",
    "spec_comparison": {},
    "benchmark_report_md": "",
}
for k, v in DEFAULTS.items():
    st.session_state.setdefault(k, v)


def mask_token(token: str) -> str:
    token = clean_value(token)
    if not token:
        return "(empty)"
    return token[:6] + "..." + token[-4:] if len(token) >= 12 else "*" * len(token)


def as_dict(item: Any) -> dict:
    return to_dict_any(item)


def get_text(item: Any, key: str, default: str = "") -> str:
    d = as_dict(item)
    return str(d.get(key, default) or default)


def merge_items(*lists: list[Any]) -> list[Any]:
    seen: set[str] = set()
    out: list[Any] = []
    for items in lists:
        for item in items or []:
            d = as_dict(item)
            raw = (d.get("url") or d.get("href") or "").strip().lower()
            if not raw:
                raw = re.sub(r"\W+", "", (d.get("title", "") + d.get("content", "") + d.get("text", "")).lower())[:160]
            if not raw or raw in seen:
                continue
            seen.add(raw)
            out.append(item)
    return out


def build_stats_any(items: list[Any]) -> dict:
    rows = [as_dict(x) for x in items]
    total = len(rows)
    cat = {}
    src = {}
    snt = {}
    for d in rows:
        c = d.get("category") or "기타"
        source = d.get("source") or d.get("source_type") or d.get("channel") or "unknown"
        sentiment = d.get("sentiment_hint") or d.get("sentiment") or "neutral"
        cat[c] = cat.get(c, 0) + 1
        src[source] = src.get(source, 0) + 1
        snt[sentiment] = snt.get(sentiment, 0) + 1
    neg = sum(v for k, v in snt.items() if str(k).lower() in {"negative", "부정", "개선요청", "mixed", "혼합"})
    pos = sum(v for k, v in snt.items() if str(k).lower() in {"positive", "긍정"})
    return {
        "total": total,
        "by_category": dict(sorted(cat.items(), key=lambda x: x[1], reverse=True)),
        "by_source": dict(sorted(src.items(), key=lambda x: x[1], reverse=True)),
        "by_sentiment": dict(sorted(snt.items(), key=lambda x: x[1], reverse=True)),
        "neg_pct": round(neg / total * 100) if total else 0,
        "pos_pct": round(pos / total * 100) if total else 0,
    }


def parse_keywords(raw: str, max_keywords: int = 30) -> list[str]:
    parts: list[str] = []
    for line in (raw or "").splitlines():
        for part in re.split(r"[,;]+", line):
            q = re.sub(r"\s+", " ", part).strip()
            if q:
                parts.append(q[:120])
    seen, out = set(), []
    for q in parts:
        key = q.lower()
        if key not in seen:
            seen.add(key)
            out.append(q)
            if len(out) >= max_keywords:
                break
    return out


def build_all_chunks() -> list[Any]:
    voc_chunks = chunks_from_voc(st.session_state.get("voc_list", []))
    uploaded = st.session_state.get("uploaded_chunks", []) or []
    return voc_chunks + uploaded


def run_rag_search(query: str, top_k: int = 8) -> tuple[list[dict], str]:
    chunks = build_all_chunks()
    if not chunks:
        return [], ""
    index = SimpleRAGIndex(chunks)
    hits = index.search(query, top_k=top_k)
    hit_dicts = [h.to_dict() for h in hits]
    context = build_context(hits, max_chars=5000)
    return hit_dicts, context


def llm_generate(prompt: str, system: str = "", max_tokens: int = 2048, temperature: float = 0.2) -> str:
    if not st.session_state.get("engine_ready"):
        raise RuntimeError("HF Router가 연결되지 않았습니다. 사이드바에서 연결 확인을 먼저 실행하세요.")
    return api_engine.generate(prompt, system=system or "당신은 한국어 비즈니스 분석 전문가입니다.", max_tokens=max_tokens, temperature=temperature)


def render_stats(stats: dict) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("총 VOC", stats.get("total", 0))
    c2.metric("부정/개선", f"{stats.get('neg_pct', 0)}%")
    c3.metric("긍정", f"{stats.get('pos_pct', 0)}%")
    c4.metric("소스 수", len(stats.get("by_source", {})))
    left, mid, right = st.columns(3)
    with left:
        st.markdown("#### 카테고리")
        data = pd.DataFrame(list(stats.get("by_category", {}).items()), columns=["category", "count"])
        if not data.empty:
            st.bar_chart(data.set_index("category"))
        else:
            st.info("데이터 없음")
    with mid:
        st.markdown("#### 감성")
        data = pd.DataFrame(list(stats.get("by_sentiment", {}).items()), columns=["sentiment", "count"])
        if not data.empty:
            st.bar_chart(data.set_index("sentiment"))
        else:
            st.info("데이터 없음")
    with right:
        st.markdown("#### 소스")
        data = pd.DataFrame(list(stats.get("by_source", {}).items()), columns=["source", "count"])
        if not data.empty:
            st.dataframe(data, use_container_width=True, hide_index=True)
        else:
            st.info("데이터 없음")


def render_voc_table(items: list[Any], *, height: int = 360) -> None:
    rows = [as_dict(x) for x in items]
    if not rows:
        st.info("표시할 VOC가 없습니다.")
        return
    df = pd.DataFrame(rows)
    cols = [c for c in ["title", "source", "source_type", "channel", "category", "sentiment", "sentiment_hint", "relevance_score", "url", "href", "collected_at"] if c in df.columns]
    st.dataframe(df[cols], use_container_width=True, height=height)


def render_voc_cards(items: list[Any], limit: int = 60) -> None:
    if not items:
        st.info("VOC가 없습니다.")
        return
    for item in items[:limit]:
        d = as_dict(item)
        title = escape(str(d.get("title") or "제목 없음"))
        source = escape(str(d.get("source") or d.get("source_type") or d.get("channel") or "source"))
        cat = escape(str(d.get("category") or "기타"))
        snt = escape(str(d.get("sentiment_hint") or d.get("sentiment") or "neutral"))
        body = escape(str(d.get("content") or d.get("text") or d.get("body") or "")[:280])
        st.markdown(f"""
<div class="voc">
  <div class="voc-title">{title}</div>
  <div class="voc-meta">{source} · {cat} · {snt}</div>
  <div class="small">{body}</div>
</div>
""", unsafe_allow_html=True)
    if len(items) > limit:
        st.caption(f"처음 {limit}건만 표시했습니다. 전체 {len(items)}건")


def build_zip_bundle() -> bytes:
    data = {
        "metadata": {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "engine_model": st.session_state.get("engine_model"),
            "total_voc": len(st.session_state.get("voc_list", [])),
        },
        "voc_list": [as_dict(x) for x in st.session_state.get("voc_list", [])],
        "stats": build_stats_any(st.session_state.get("voc_list", [])),
        "analysis": st.session_state.get("analysis"),
        "srs_text": st.session_state.get("srs_text", ""),
        "voc_report_text": st.session_state.get("voc_report_text", ""),
        "rag": {
            "query": st.session_state.get("rag_query", ""),
            "hits": st.session_state.get("rag_hits", []),
            "context": st.session_state.get("rag_context", ""),
            "answer": st.session_state.get("rag_answer", ""),
        },
        "benchmark": {
            "guide": st.session_state.get("benchmark_guide"),
            "my_voc_analysis": st.session_state.get("bench_my_voc_analysis"),
            "comp_voc_analysis": st.session_state.get("bench_comp_voc_analysis"),
            "spec_comparison": st.session_state.get("spec_comparison"),
            "benchmark_report_md": st.session_state.get("benchmark_report_md", ""),
        },
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("analysis_full.json", json.dumps(data, ensure_ascii=False, indent=2))
        zf.writestr("voc_items.csv", rows_to_csv_bytes(st.session_state.get("voc_list", [])).decode("utf-8-sig", errors="ignore"))
        zf.writestr("srs.md", st.session_state.get("srs_text", ""))
        zf.writestr("voc_insight_report.md", st.session_state.get("voc_report_text", ""))
        zf.writestr("benchmark_report.md", st.session_state.get("benchmark_report_md", ""))
        for key in ["last_docx_path", "last_pptx_path", "last_voc_report_docx_path"]:
            path = st.session_state.get(key) or ""
            if path and Path(path).exists():
                zf.write(path, arcname=Path(path).name)
        if st.session_state.get("benchmark_report_md"):
            meta = {"title": "AI 벤치마킹 보고서", "subtitle": "VOC/스펙/전략 통합 보고서"}
            try:
                zf.writestr("benchmark_report.docx", markdown_to_docx_bytes(st.session_state["benchmark_report_md"], meta))
                zf.writestr("benchmark_report.pptx", markdown_to_pptx_bytes(st.session_state["benchmark_report_md"], meta))
            except Exception as exc:
                zf.writestr("office_export_error.txt", str(exc))
    buf.seek(0)
    return buf.getvalue()


# ──────────────────────────────────────────────────────────────────────────────
# Sidebar
# ──────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🔑 AI Router")
    st.caption("HF Router Chat Completions 기반. text-generation fallback을 쓰지 않습니다.")
    token = st.text_input("HF_TOKEN", value=st.session_state["hf_token_val"], type="password", placeholder="hf_...")
    st.session_state["hf_token_val"] = clean_value(token)

    model_options = [m.model_id for m in SUPPORTED_MODELS]
    current_model = st.session_state["hf_router_model"] or DEFAULT_ROUTER_CANDIDATES[0]
    if current_model not in model_options:
        model_options = [current_model] + model_options
    st.session_state["hf_router_model"] = st.selectbox("기본 모델", model_options, index=model_options.index(current_model))

    with st.expander("Fallback/생성 설정", expanded=False):
        st.session_state["hf_model_candidates_text"] = st.text_area("Fallback 후보", st.session_state["hf_model_candidates_text"], height=150)
        st.session_state["max_tokens"] = st.slider("Max Tokens", 500, 4096, int(st.session_state["max_tokens"]), 100)
        st.session_state["temperature"] = st.slider("Temperature", 0.0, 1.0, float(st.session_state["temperature"]), 0.05)

    if st.button("🔌 LLM 연결 테스트", type="primary", use_container_width=True):
        candidates = [x.strip() for x in st.session_state["hf_model_candidates_text"].splitlines() if x.strip()]
        with st.spinner("HF Router 연결 확인 중..."):
            result = api_engine.setup(
                hf_token=st.session_state["hf_token_val"],
                model_id=st.session_state["hf_router_model"],
                max_tokens=int(st.session_state["max_tokens"]),
                temperature=float(st.session_state["temperature"]),
                auto_fallback=True,
                candidates=candidates,
            )
        st.session_state["engine_ready"] = bool(result.get("ok"))
        st.session_state["engine_model"] = result.get("model_id", "")
        st.session_state["engine_label"] = result.get("label", "")
        st.session_state["engine_msg"] = result.get("message", "")
        st.session_state["router_attempts"] = result.get("attempts", [])
        st.success(result["message"]) if result.get("ok") else st.error(result.get("message", "연결 실패"))

    if st.session_state["engine_ready"]:
        st.success(f"연결됨: {st.session_state['engine_model']}")
    else:
        st.warning("AI 미연결: 규칙 기반 기능은 사용 가능")
    if st.session_state.get("router_attempts"):
        with st.expander("연결 로그", expanded=not st.session_state["engine_ready"]):
            st.dataframe(pd.DataFrame(st.session_state["router_attempts"]), use_container_width=True)

    st.divider()
    st.markdown("## 🧠 프롬프트 전략")
    preset_options = get_prompt_preset_options()
    keys = [k for k, _ in preset_options]
    labels = {k: label for k, label in preset_options}
    if st.session_state["prompt_preset"] not in keys:
        st.session_state["prompt_preset"] = DEFAULT_PROMPT_PRESET
    st.session_state["prompt_preset"] = st.selectbox("프롬프트 프리셋", keys, index=keys.index(st.session_state["prompt_preset"]), format_func=lambda k: labels.get(k, k))
    desc = describe_prompt_preset(st.session_state["prompt_preset"])
    st.caption(desc.get("scenario", ""))
    st.session_state["custom_prompt_instruction"] = st.text_area("추가 지시", st.session_state["custom_prompt_instruction"], height=90)

    st.divider()
    if st.button("🧹 전체 작업 초기화", use_container_width=True):
        keep = {"hf_token_val", "hf_router_model", "hf_model_candidates_text", "max_tokens", "temperature", "engine_ready", "engine_model", "router_attempts"}
        for k, v in DEFAULTS.items():
            if k not in keep:
                st.session_state[k] = v
        st.rerun()

st.markdown(
    f"""
<div class="hero-pro">
  <h1>🚀 AI VOC & Benchmark Studio Pro</h1>
  <p>VOC 자동 수집 · RAG 근거 검색 · 경쟁사 벤치마킹 · 사양 비교 · SRS · Word/PPT 보고서까지 하나로 통합한 최종 버전</p>
</div>
<div class="card">
  <span class="badge">TOKEN {mask_token(st.session_state.get('hf_token_val',''))}</span>
  <span class="badge">MODEL {escape(st.session_state.get('engine_model') or st.session_state.get('hf_router_model',''))}</span>
  <span class="badge">VOC {len(st.session_state.get('voc_list', []))}건</span>
  <span class="badge">RAG CHUNKS {len(build_all_chunks())}개</span>
  <span class="badge">BENCHMARK {'READY' if st.session_state.get('benchmark_report_md') else 'DRAFT'}</span>
</div>
""",
    unsafe_allow_html=True,
)

overview_tab, voc_tab, upload_tab, rag_tab, analysis_tab, benchmark_tab, report_tab, export_tab, help_tab = st.tabs([
    "🏠 Overview", "📥 VOC 수집", "📎 업로드", "🔎 RAG", "🤖 VOC 분석", "📊 벤치마킹", "📑 리포트/SRS", "📦 내보내기", "🛠 실행/배포"
])

with overview_tab:
    st.markdown("### 통합 워크플로우")
    a, b, c, d = st.columns(4)
    a.metric("VOC", len(st.session_state.get("voc_list", [])))
    b.metric("업로드 청크", len(st.session_state.get("uploaded_chunks", []) or []))
    c.metric("분석 상태", "완료" if st.session_state.get("analysis") else "대기")
    d.metric("벤치마킹", "완료" if st.session_state.get("benchmark_report_md") else "대기")
    st.markdown(
        """
1. **VOC 수집** 탭에서 공개 웹/뉴스/RSS와 Galaxy 커뮤니티 소스를 함께 수집합니다.  
2. **업로드** 탭에서 기존 VOC CSV, 회의록, 요구사항 문서, 보고서를 넣어 RAG 근거로 확장합니다.  
3. **RAG/VOC 분석** 탭에서 이슈, 요구사항, KPI, 로드맵을 생성합니다.  
4. **벤치마킹** 탭에서 자사와 경쟁사의 VOC·사양·전략 비교 보고서를 만듭니다.  
5. **리포트/SRS/내보내기** 탭에서 Markdown, JSON, CSV, DOCX, PPTX, ZIP을 다운로드합니다.
"""
    )
    st.info("AI 연결 없이도 데모 VOC, 크롤링, 규칙 기반 요약, 기본 리포트 생성은 가능합니다. LLM 연결 후에는 고급 분석과 전략 보고서 품질이 크게 좋아집니다.")

with voc_tab:
    st.markdown("## 📥 VOC 자동 수집")
    c_top1, c_top2, c_top3 = st.columns([1.2, 1.2, 1])
    with c_top1:
        company = st.text_input("회사/브랜드", value="삼성전자")
        product = st.text_input("제품/서비스", value="Galaxy S25 Ultra")
    with c_top2:
        keyword_text = st.text_area("추가 검색어", value="갤럭시 배터리\n갤럭시 카메라\n갤럭시 발열\nOne UI 업데이트", height=100)
        keywords = parse_keywords(keyword_text, 30)
    with c_top3:
        max_per_source = st.slider("소스당 최대 건수", 5, 80, 20)
        n_per_query = st.slider("공개검색 쿼리당 건수", 3, 25, 8)

    st.markdown("### 수집 소스")
    p1, p2 = st.columns(2)
    with p1:
        public_sources = st.multiselect("공개 웹/뉴스", ["web", "news", "rss"], default=["web", "news", "rss"], format_func=lambda x: {"web":"DuckDuckGo Web", "news":"DuckDuckGo News", "rss":"Google News RSS"}.get(x, x))
        depth = st.selectbox("공개검색 깊이", ["basic", "standard", "deep"], index=1)
        timelimit_label = st.selectbox("기간", ["전체", "최근 1일", "최근 1주", "최근 1개월", "최근 1년"], index=3)
        timemap = {"전체": None, "최근 1일": "d", "최근 1주": "w", "최근 1개월": "m", "최근 1년": "y"}
        region = st.selectbox("지역", ["kr-kr", "us-en", "wt-wt"], index=0)
        fetch_pages = st.checkbox("본문 일부 보강", value=False, help="느릴 수 있지만 snippet을 보강합니다.")
    with p2:
        community_sources = st.multiselect(
            "Galaxy/커뮤니티",
            ["samsung", "naver_kin", "naver_cafe", "dcinside", "clien"],
            default=["samsung", "naver_kin", "naver_cafe", "dcinside", "clien"],
            format_func=lambda x: {"samsung":"삼성 Members", "naver_kin":"네이버 지식인", "naver_cafe":"네이버 카페", "dcinside":"DC인사이드", "clien":"클리앙"}.get(x, x),
        )
        custom_urls = st.text_area("사용자 URL 추가", value="", height=137, placeholder="https://example.com/review-page")

    btn1, btn2, btn3, btn4 = st.columns(4)
    with btn1:
        if st.button("🧪 데모 VOC", use_container_width=True):
            demo = get_demo_voc()
            st.session_state["voc_list"] = demo
            st.session_state["stats"] = build_stats_any(demo)
            st.success(f"데모 VOC {len(demo)}건 로드")
            st.rerun()
    with btn2:
        if st.button("🌐 공개 웹 수집", type="primary", disabled=not public_sources, use_container_width=True):
            with st.spinner("공개 웹/뉴스/RSS 수집 중..."):
                public_items = collect_public_voc(company, product, n_per_query=n_per_query, sources=public_sources, depth=depth, fetch_pages=fetch_pages, region=region, timelimit=timemap[timelimit_label])
            st.session_state["public_voc_list"] = public_items
            st.session_state["voc_list"] = merge_items(st.session_state.get("voc_list", []), public_items)
            st.session_state["stats"] = build_stats_any(st.session_state["voc_list"])
            st.success(f"공개 VOC {len(public_items)}건 수집")
            st.rerun()
    with btn3:
        if st.button("💬 커뮤니티 수집", disabled=not community_sources, use_container_width=True):
            q = keywords or [product, company]
            pb = st.progress(0, text="수집 준비")
            def on_progress(step, total, name, status):
                pb.progress(step / max(total, 1), text=f"[{step}/{total}] {name}: {status}")
            urls = [u.strip() for u in custom_urls.splitlines() if u.strip()]
            with st.spinner("커뮤니티/사용자 URL 수집 중..."):
                items = collect_all(q, community_sources, max_per_source=max_per_source, on_progress=on_progress, custom_urls=urls)
            st.session_state["community_voc_list"] = items
            st.session_state["voc_list"] = merge_items(st.session_state.get("voc_list", []), items)
            st.session_state["stats"] = build_stats_any(st.session_state["voc_list"])
            st.success(f"커뮤니티 VOC {len(items)}건 수집")
            st.rerun()
    with btn4:
        if st.button("🧹 VOC만 초기화", use_container_width=True):
            st.session_state["voc_list"] = []
            st.session_state["public_voc_list"] = []
            st.session_state["community_voc_list"] = []
            st.session_state["stats"] = {}
            st.rerun()

    st.markdown("---")
    stats = st.session_state.get("stats") or build_stats_any(st.session_state.get("voc_list", []))
    render_stats(stats)
    st.markdown("### VOC 상세")
    table_mode = st.toggle("테이블 보기", value=True)
    render_voc_table(st.session_state.get("voc_list", [])) if table_mode else render_voc_cards(st.session_state.get("voc_list", []))
    if st.session_state.get("voc_list"):
        st.download_button("⬇️ VOC CSV", rows_to_csv_bytes(st.session_state["voc_list"]), "voc_items.csv", "text/csv", key="download_voc_csv_collect_tab")

with upload_tab:
    st.markdown("## 📎 파일 업로드 → VOC/RAG 지식화")
    uploaded_files = st.file_uploader("CSV/XLSX/TXT/DOCX 파일", type=["csv", "xlsx", "xlsm", "txt", "docx"], accept_multiple_files=True)
    max_rows = st.slider("표 파일 최대 행", 50, 5000, 500, 50)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("📎 업로드 처리", type="primary", disabled=not uploaded_files, use_container_width=True):
            logs, added_items, added_chunks = [], [], []
            with st.spinner("파일 파싱/청킹 중..."):
                for uf in uploaded_files:
                    try:
                        items, chunks, msg = parse_uploaded_file(uf, max_rows=max_rows)
                        added_items.extend(items); added_chunks.extend(chunks)
                        logs.append({"file": uf.name, "status": "ok", "message": msg, "voc_items": len(items), "chunks": len(chunks)})
                    except Exception as exc:
                        logs.append({"file": uf.name, "status": "error", "message": str(exc), "voc_items": 0, "chunks": 0})
            st.session_state["voc_list"] = merge_items(st.session_state.get("voc_list", []), added_items)
            st.session_state["uploaded_chunks"] = (st.session_state.get("uploaded_chunks", []) or []) + added_chunks
            st.session_state["upload_logs"] = logs
            st.session_state["stats"] = build_stats_any(st.session_state["voc_list"])
            st.success(f"VOC {len(added_items)}건, RAG 청크 {len(added_chunks)}개 추가")
            st.rerun()
    with c2:
        if st.button("🧽 업로드 청크 초기화", use_container_width=True):
            st.session_state["uploaded_chunks"] = []
            st.session_state["upload_logs"] = []
            st.rerun()
    if st.session_state.get("upload_logs"):
        st.dataframe(pd.DataFrame(st.session_state["upload_logs"]), use_container_width=True, hide_index=True)
    if st.session_state.get("uploaded_chunks"):
        rows = [to_dict_any(x) for x in st.session_state["uploaded_chunks"][:200]]
        st.dataframe(pd.DataFrame(rows), use_container_width=True)

with rag_tab:
    st.markdown("## 🔎 RAG 근거 검색/질의응답")
    chunks = build_all_chunks()
    m1, m2, m3 = st.columns(3)
    m1.metric("전체 청크", len(chunks)); m2.metric("VOC 청크", len(st.session_state.get("voc_list", []))); m3.metric("업로드 청크", len(st.session_state.get("uploaded_chunks", []) or []))
    st.session_state["rag_query"] = st.text_area("질문", value=st.session_state["rag_query"], height=90)
    top_k = st.slider("Top-K", 3, 25, 8)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔎 근거 검색", type="primary", disabled=not chunks, use_container_width=True):
            hits, context = run_rag_search(st.session_state["rag_query"], top_k)
            st.session_state["rag_hits"] = hits; st.session_state["rag_context"] = context
            st.success(f"근거 {len(hits)}건 검색")
            st.rerun()
    with c2:
        if st.button("💬 RAG 답변 생성", disabled=not (chunks and st.session_state["engine_ready"]), use_container_width=True):
            hits, context = run_rag_search(st.session_state["rag_query"], top_k)
            prompt = build_rag_answer_prompt(
                question=st.session_state["rag_query"],
                context=context,
                preset_key="rag_evidence",
                custom_instruction=st.session_state.get("custom_prompt_instruction", ""),
            )
            with st.spinner("답변 생성 중..."):
                answer = api_engine.generate(prompt, max_tokens=1800, temperature=0.15)
            st.session_state["rag_hits"] = hits; st.session_state["rag_context"] = context; st.session_state["rag_answer"] = answer
            st.success("답변 완료")
            st.rerun()
    if st.session_state.get("rag_hits"):
        st.dataframe(pd.DataFrame(st.session_state["rag_hits"]), use_container_width=True)
        with st.expander("RAG Context"):
            st.text_area("Context", st.session_state.get("rag_context", ""), height=280)
    if st.session_state.get("rag_answer"):
        st.markdown("### 답변")
        st.markdown(st.session_state["rag_answer"])

with analysis_tab:
    st.markdown("## 🤖 VOC AI 분석")
    target = st.text_input("분석 대상", value="Galaxy S 시리즈")
    include_rag = st.checkbox("RAG 근거 포함", value=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("🤖 VOC 구조화 분석", type="primary", disabled=not (st.session_state.get("voc_list") and st.session_state["engine_ready"]), use_container_width=True):
            rag_context = ""
            if include_rag:
                _, rag_context = run_rag_search(f"{target} 주요 불편 요구사항 KPI 리스크", 12)
                st.session_state["rag_context"] = rag_context
            with st.spinner("VOC 분석 중..."):
                st.session_state["analysis"] = analyze_voc_api(st.session_state["voc_list"], target, rag_context=rag_context, prompt_preset=st.session_state["prompt_preset"], custom_prompt=st.session_state["custom_prompt_instruction"])
            st.success("분석 완료"); st.rerun()
    with c2:
        if st.button("📑 VOC 인사이트 리포트", type="primary", disabled=not st.session_state.get("voc_list"), use_container_width=True):
            rag_context = st.session_state.get("rag_context", "")
            if st.session_state["engine_ready"]:
                payload = build_voc_report_payload(st.session_state["voc_list"])
                prompt = build_voc_insight_report_prompt(
                    payload=payload,
                    model_info_str=target,
                    analysis=st.session_state.get("analysis") or {},
                    rag_context=rag_context,
                    preset_key="executive_report",
                    custom_instruction=st.session_state.get("custom_prompt_instruction", ""),
                )
                with st.spinner("리포트 생성 중..."):
                    try:
                        st.session_state["voc_report_text"] = api_engine.generate(prompt, max_tokens=3600, temperature=0.12)
                    except Exception as exc:
                        st.session_state["voc_report_text"] = fallback_voc_report_markdown(st.session_state["voc_list"], target, st.session_state.get("analysis") or {}, rag_context, model_label=f"fallback: {exc}")
            else:
                st.session_state["voc_report_text"] = fallback_voc_report_markdown(st.session_state["voc_list"], target, st.session_state.get("analysis") or {}, rag_context, model_label="rule-based")
            st.success("리포트 생성 완료"); st.rerun()
    with c3:
        if st.button("📋 SRS Markdown 생성", type="primary", disabled=not (st.session_state.get("analysis") and st.session_state["engine_ready"]), use_container_width=True):
            prompt = build_srs_prompt(st.session_state["voc_list"], st.session_state["analysis"], target, "1.0", "제품기획팀", rag_context=st.session_state.get("rag_context", ""), prompt_preset=st.session_state["prompt_preset"], custom_prompt=st.session_state["custom_prompt_instruction"])
            with st.spinner("SRS 생성 중..."):
                st.session_state["srs_text"] = api_engine.generate(prompt, max_tokens=3800, temperature=0.15)
            st.success("SRS 생성 완료"); st.rerun()
    if st.session_state.get("analysis"):
        st.markdown("### 분석 결과")
        analysis = st.session_state["analysis"]
        if analysis.get("executive_summary"):
            st.info(analysis["executive_summary"])
        for title, key in [("핵심 이슈", "critical_issues"), ("요구사항", "requirements"), ("비기능 요구사항", "non_functional_requirements"), ("KPI", "kpis"), ("로드맵", "roadmap")]:
            if analysis.get(key):
                st.markdown(f"#### {title}")
                st.dataframe(pd.DataFrame(analysis[key]), use_container_width=True)

with benchmark_tab:
    st.markdown("## 📊 경쟁사 벤치마킹 통합")
    b1, b2 = st.columns(2)
    with b1:
        my_co = st.text_input("자사명", value="삼성전자", key="bench_my_co")
        my_prod = st.text_input("자사 제품", value="Galaxy S25 Ultra", key="bench_my_prod")
    with b2:
        comp_co = st.text_input("경쟁사명", value="Apple", key="bench_comp_co")
        comp_prod = st.text_input("경쟁사 제품", value="iPhone 16 Pro Max", key="bench_comp_prod")

    st.markdown("### 1) 벤치마킹 가이드")
    guide_files = st.file_uploader("기존 보고서 PDF/DOCX 업로드 시 작성 가이드 자동 추출", type=["pdf", "docx", "txt", "md"], accept_multiple_files=True, key="guide_files")
    g1, g2 = st.columns(2)
    with g1:
        if st.button("📋 업로드 문서에서 가이드 추출", disabled=not guide_files, use_container_width=True):
            texts = []
            for f in guide_files:
                data = f.read()
                if f.name.lower().endswith(".pdf"):
                    txt = extract_pdf(data)
                elif f.name.lower().endswith(".docx"):
                    txt = extract_docx(data)
                else:
                    txt = data.decode("utf-8", errors="ignore")
                if txt.strip():
                    texts.append(f"[파일: {f.name}]\n{txt}")
            st.session_state["benchmark_guide"] = build_guide_from_texts(texts, llm_generate if st.session_state["engine_ready"] else None)
            st.success("가이드 추출 완료")
            st.rerun()
    with g2:
        if st.button("📝 기본 표준 가이드 사용", use_container_width=True):
            st.session_state["benchmark_guide"] = DEFAULT_GUIDE.copy(); st.success("기본 가이드 적용"); st.rerun()
    with st.expander("현재 가이드", expanded=False):
        st.json(st.session_state.get("benchmark_guide") or DEFAULT_GUIDE)

    st.markdown("### 2) 자사/경쟁사 VOC 비교")
    v1, v2, v3 = st.columns(3)
    with v1:
        bench_n = st.slider("쿼리당 수집", 3, 25, 8, key="bench_n")
    with v2:
        bench_depth = st.selectbox("깊이", ["basic", "standard", "deep"], index=1, key="bench_depth")
    with v3:
        bench_sources = st.multiselect("소스", ["web", "news", "rss"], default=["web", "news", "rss"], key="bench_sources")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔍 자사/경쟁사 공개 VOC 수집", type="primary", disabled=not bench_sources, use_container_width=True):
            with st.spinner("자사 VOC 수집 중..."):
                my_items = collect_public_voc(my_co, my_prod, bench_n, bench_sources, bench_depth)
            with st.spinner("경쟁사 VOC 수집 중..."):
                comp_items = collect_public_voc(comp_co, comp_prod, bench_n, bench_sources, bench_depth)
            st.session_state["bench_my_voc_raw"] = my_items; st.session_state["bench_comp_voc_raw"] = comp_items
            st.success(f"수집 완료: 자사 {len(my_items)}건 / 경쟁사 {len(comp_items)}건")
            st.rerun()
    with c2:
        if st.button("🤖 벤치마킹 VOC 분석", disabled=not (st.session_state.get("bench_my_voc_raw") or st.session_state.get("bench_comp_voc_raw")), use_container_width=True):
            with st.spinner("자사 VOC 분석 중..."):
                st.session_state["bench_my_voc_analysis"] = analyze_benchmark_voc(my_co, my_prod, st.session_state.get("bench_my_voc_raw", []), llm_generate if st.session_state["engine_ready"] else None)
            with st.spinner("경쟁사 VOC 분석 중..."):
                st.session_state["bench_comp_voc_analysis"] = analyze_benchmark_voc(comp_co, comp_prod, st.session_state.get("bench_comp_voc_raw", []), llm_generate if st.session_state["engine_ready"] else None)
            st.success("VOC 비교 분석 완료"); st.rerun()
    d1, d2 = st.columns(2)
    with d1:
        st.markdown(f"#### {my_co} VOC")
        render_voc_table(st.session_state.get("bench_my_voc_raw", []), height=260)
        if st.session_state.get("bench_my_voc_analysis"):
            st.json(st.session_state["bench_my_voc_analysis"])
    with d2:
        st.markdown(f"#### {comp_co} VOC")
        render_voc_table(st.session_state.get("bench_comp_voc_raw", []), height=260)
        if st.session_state.get("bench_comp_voc_analysis"):
            st.json(st.session_state["bench_comp_voc_analysis"])

    st.markdown("### 3) 제품 사양 비교")
    s1, s2 = st.columns(2)
    with s1:
        st.session_state["spec_my_raw"] = st.text_area("자사 사양/특징", value=st.session_state["spec_my_raw"], height=220, placeholder="- AP:\n- 배터리:\n- 카메라:")
    with s2:
        st.session_state["spec_comp_raw"] = st.text_area("경쟁사 사양/특징", value=st.session_state["spec_comp_raw"], height=220)
    sc1, sc2 = st.columns(2)
    with sc1:
        if st.button("🌐 웹에서 사양 자동 수집", use_container_width=True):
            with st.spinner("사양 검색 중..."):
                my_res = collect_specs(my_co, my_prod)
                comp_res = collect_specs(comp_co, comp_prod)
            st.session_state["spec_my_raw"] = "\n".join(f"[{r.get('title','')}] {r.get('body') or r.get('snippet','')}" for r in my_res[:8])[:5000]
            st.session_state["spec_comp_raw"] = "\n".join(f"[{r.get('title','')}] {r.get('body') or r.get('snippet','')}" for r in comp_res[:8])[:5000]
            st.success("사양 수집 완료"); st.rerun()
    with sc2:
        if st.button("⚖️ AI 사양 비교", type="primary", use_container_width=True):
            with st.spinner("사양 비교 중..."):
                st.session_state["spec_comparison"] = compare_specs(my_co, my_prod, comp_co, comp_prod, st.session_state["spec_my_raw"], st.session_state["spec_comp_raw"], llm_generate if st.session_state["engine_ready"] else None)
            st.success("사양 비교 완료"); st.rerun()
    if st.session_state.get("spec_comparison"):
        st.markdown("#### 사양 비교 결과")
        comp = st.session_state["spec_comparison"]
        if comp.get("overall_summary"):
            st.info(comp.get("overall_summary"))
        if comp.get("spec_matrix"):
            st.dataframe(pd.DataFrame(comp["spec_matrix"]), use_container_width=True)
        else:
            st.json(comp)

    st.markdown("### 4) 최종 벤치마킹 보고서")
    if st.button("🚀 최종 벤치마킹 보고서 생성", type="primary", use_container_width=True):
        with st.spinner("보고서 생성 중..."):
            st.session_state["benchmark_report_md"] = generate_benchmark_report(
                st.session_state.get("benchmark_guide") or DEFAULT_GUIDE,
                my_co, my_prod, comp_co, comp_prod,
                st.session_state.get("bench_my_voc_analysis", {}),
                st.session_state.get("bench_comp_voc_analysis", {}),
                st.session_state.get("spec_comparison", {}),
                llm_generate if st.session_state["engine_ready"] else None,
                model_id=st.session_state.get("engine_model") or "rule-based",
            )
        st.success("벤치마킹 보고서 생성 완료"); st.rerun()
    if st.session_state.get("benchmark_report_md"):
        st.markdown(st.session_state["benchmark_report_md"])

with report_tab:
    st.markdown("## 📑 리포트/SRS 생성 및 미리보기")
    product_name = st.text_input("문서 제품명", value="Galaxy VOC 분석")
    r1, r2, r3 = st.columns(3)
    with r1:
        if st.button("📄 VOC/SRS DOCX 생성", disabled=not st.session_state.get("voc_list"), use_container_width=True):
            path = generate_docx(st.session_state["voc_list"], st.session_state.get("analysis") or {}, st.session_state.get("srs_text", ""), product_name=product_name, output_dir=str(ROOT / "output"), model_label=st.session_state.get("engine_model", "HF Router"))
            st.session_state["last_docx_path"] = path; st.success(Path(path).name)
    with r2:
        if st.button("📊 VOC/SRS PPTX 생성", disabled=not st.session_state.get("voc_list"), use_container_width=True):
            rag_data = {"query": st.session_state.get("rag_query", ""), "hits": st.session_state.get("rag_hits", []), "context": st.session_state.get("rag_context", ""), "answer": st.session_state.get("rag_answer", ""), "uploaded_chunks_count": len(st.session_state.get("uploaded_chunks", []) or [])}
            path = generate_pptx(st.session_state["voc_list"], st.session_state.get("analysis") or {}, st.session_state.get("srs_text", ""), stats=build_stats_any(st.session_state["voc_list"]), rag_data=rag_data, product_name=product_name, output_dir=str(ROOT / "output"), model_label=st.session_state.get("engine_model", "HF Router"))
            st.session_state["last_pptx_path"] = path; st.success(Path(path).name)
    with r3:
        if st.button("📄 VOC 리포트 DOCX 생성", disabled=not st.session_state.get("voc_report_text"), use_container_width=True):
            path = generate_markdown_docx(st.session_state["voc_report_text"], title="VOC 요약·인사이트 리포트", output_dir=str(ROOT / "output"), file_prefix="VOC_Insight_Report")
            st.session_state["last_voc_report_docx_path"] = path; st.success(Path(path).name)

    rpt1, rpt2, rpt3 = st.tabs(["VOC 리포트", "SRS", "벤치마킹 보고서"])
    with rpt1:
        if st.session_state.get("voc_report_text"):
            st.download_button("⬇️ Markdown", st.session_state["voc_report_text"].encode("utf-8"), "voc_insight_report.md", "text/markdown", key="download_voc_report_md")
            st.markdown(st.session_state["voc_report_text"])
        else:
            st.info("VOC 분석 탭에서 리포트를 생성하세요.")
    with rpt2:
        if st.session_state.get("srs_text"):
            st.download_button("⬇️ SRS Markdown", st.session_state["srs_text"].encode("utf-8"), "srs.md", "text/markdown", key="download_srs_md")
            st.markdown(st.session_state["srs_text"])
        else:
            st.info("VOC 분석 탭에서 SRS를 생성하세요.")
    with rpt3:
        md = st.session_state.get("benchmark_report_md", "")
        if md:
            fname = safe_filename("benchmark_report")
            meta = {"title": "벤치마킹 보고서", "subtitle": "VOC/스펙/전략 통합 분석", "author": "AI VOC Benchmark Studio Pro"}
            cdl1, cdl2, cdl3 = st.columns(3)
            cdl1.download_button("⬇️ Markdown", md.encode("utf-8"), f"{fname}.md", "text/markdown", use_container_width=True, key="download_benchmark_md")
            try:
                cdl2.download_button("⬇️ Word DOCX", markdown_to_docx_bytes(md, meta), f"{fname}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", use_container_width=True, key="download_benchmark_docx")
                cdl3.download_button("⬇️ PowerPoint PPTX", markdown_to_pptx_bytes(md, meta), f"{fname}.pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation", use_container_width=True, key="download_benchmark_pptx")
            except Exception as exc:
                st.error(f"Office 변환 오류: {exc}")
            st.markdown(md)
        else:
            st.info("벤치마킹 탭에서 최종 보고서를 생성하세요.")

with export_tab:
    st.markdown("## 📦 전체 산출물 내보내기")
    data = {
        "voc_list": [as_dict(x) for x in st.session_state.get("voc_list", [])],
        "stats": build_stats_any(st.session_state.get("voc_list", [])),
        "analysis": st.session_state.get("analysis"),
        "srs_text": st.session_state.get("srs_text", ""),
        "voc_report_text": st.session_state.get("voc_report_text", ""),
        "benchmark_report_md": st.session_state.get("benchmark_report_md", ""),
        "spec_comparison": st.session_state.get("spec_comparison", {}),
        "rag_hits": st.session_state.get("rag_hits", []),
    }
    st.download_button("⬇️ 전체 JSON", json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"), "studio_full_export.json", "application/json", key="download_full_json")
    if st.session_state.get("voc_list"):
        st.download_button("⬇️ VOC CSV", rows_to_csv_bytes(st.session_state["voc_list"]), "voc_items.csv", "text/csv", key="download_voc_csv_export_tab")
    for label, key, mime in [
        ("VOC/SRS DOCX", "last_docx_path", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("VOC/SRS PPTX", "last_pptx_path", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        ("VOC 리포트 DOCX", "last_voc_report_docx_path", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ]:
        path = st.session_state.get(key) or ""
        if path and Path(path).exists():
            st.download_button(f"⬇️ {label}", Path(path).read_bytes(), Path(path).name, mime, key=f"download_generated_{key}")
    bundle = build_zip_bundle()
    st.download_button("⬇️ 전체 결과 ZIP", bundle, f"ai_voc_benchmark_export_{datetime.now():%Y%m%d_%H%M%S}.zip", "application/zip", type="primary", key="download_full_zip")

with help_tab:
    st.markdown("## 🛠 VS Code 실행 / Streamlit 배포")
    st.markdown(
        """
### 로컬 VS Code 실행
```powershell
cd ai_voc_benchmark_studio_pro
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -U pip
pip install -r requirements.txt
copy .env.example .env
# .env에 HF_TOKEN 입력
streamlit run app.py
```

### Streamlit Cloud 배포
1. 이 폴더 전체를 GitHub 저장소에 업로드합니다.
2. Streamlit Cloud에서 `app.py`를 entrypoint로 선택합니다.
3. App settings → Secrets에 아래 값을 넣습니다.
```toml
HF_TOKEN = "hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
HF_ROUTER_MODEL = "google/gemma-4-26B-A4B-it"
HF_MODEL_CANDIDATES = "google/gemma-4-26B-A4B-it,Zyphra/ZAYA1-8B,mistralai/Mistral-7B-Instruct-v0.3"
```
4. 배포 후 사이드바에서 `LLM 연결 테스트`를 실행합니다.

### 오류 대응
- `text-generation not supported`: 이 앱은 Router Chat Completions만 사용하므로, 이전 앱의 fallback 오류를 제거했습니다.
- `401/403`: HF 토큰, 모델 라이선스 동의, fine-grained token 권한을 확인하세요.
- 크롤링 0건: 기간을 전체/최근 1년으로 바꾸고 소스를 web+news+rss로 켜세요.
"""
    )
