"""
models/config.py
Galaxy VOC Collector 설정 및 모델 레지스트리

핵심 원칙
- API 모드는 Hugging Face Router Chat Completions endpoint를 사용한다.
- provider는 HF_MODEL_CANDIDATES의 모델 suffix로 명시한다.
- .env와 Streamlit secrets를 모두 지원하되, 값은 strip 정규화한다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=True)


@dataclass(frozen=True)
class ModelInfo:
    model_id: str
    label: str
    description: str
    tier: str = "standard"
    max_tokens: int = 1400
    temperature: float = 0.2


DEFAULT_ROUTER_CANDIDATES: list[str] = [
    # Zyphra ZAYA 계열: 사용자가 UI에서 직접 선택할 수 있도록 기본 후보에 포함합니다.
    # HF Router에서 provider가 자동 매칭되지 않는 경우에는 Streamlit UI의 연결 시도 로그를 확인하고
    # 사용 가능한 provider suffix를 직접 붙여 입력할 수 있습니다. 예: Zyphra/ZAYA1-8B:<provider>
    "Zyphra/ZAYA1-8B",
    "Zyphra/ZAYA1-74B-preview",
    "google/gemma-4-26B-A4B-it:deepinfra",
    "google/gemma-4-26B-A4B-it:novita",
    "google/gemma-4-31B-it:deepinfra",
    "google/gemma-4-31B-it:together",
    "Qwen/Qwen3.5-9B:together",
    "Qwen/Qwen2.5-7B-Instruct:together",
]

SUPPORTED_MODELS: list[ModelInfo] = [
    ModelInfo(
        "Zyphra/ZAYA1-8B",
        "ZAYA1-8B · Zyphra",
        "Zyphra 소형 MoE reasoning 모델. 로컬/경량 실험과 VOC 요약·분석용 선택 옵션",
        "zaya",
        max_tokens=2200,
        temperature=0.15,
    ),
    ModelInfo(
        "Zyphra/ZAYA1-74B-preview",
        "ZAYA1-74B-preview · Zyphra",
        "Zyphra 대형 MoE preview 모델. 멀티 GPU/서버 연구용 선택 옵션",
        "zaya-preview",
        max_tokens=2200,
        temperature=0.15,
    ),
    ModelInfo(
        "google/gemma-4-26B-A4B-it:deepinfra",
        "Gemma 4 26B-A4B-it · DeepInfra",
        "HF Router provider-pinned 권장 기본값",
        "flagship",
    ),
    ModelInfo(
        "google/gemma-4-26B-A4B-it:novita",
        "Gemma 4 26B-A4B-it · Novita",
        "동일 모델 대체 provider",
        "flagship",
    ),
    ModelInfo(
        "google/gemma-4-31B-it:deepinfra",
        "Gemma 4 31B-it · DeepInfra",
        "상위 Gemma 계열 fallback",
        "flagship",
    ),
    ModelInfo(
        "google/gemma-4-31B-it:together",
        "Gemma 4 31B-it · Together",
        "Gemma 계열 대체 provider fallback",
        "flagship",
    ),
    ModelInfo(
        "Qwen/Qwen3.5-9B:together",
        "Qwen 3.5 9B · Together",
        "장문 구조화 분석용 안정 fallback",
        "standard",
    ),
    ModelInfo(
        "Qwen/Qwen2.5-7B-Instruct:together",
        "Qwen 2.5 7B Instruct · Together",
        "마지막 텍스트 생성 fallback",
        "lite",
    ),
]

MODEL_MAP: dict[str, ModelInfo] = {m.model_id: m for m in SUPPORTED_MODELS}
FALLBACK_ORDER: list[str] = DEFAULT_ROUTER_CANDIDATES.copy()


def clean_value(value: object | None) -> str:
    if value is None:
        return ""
    return str(value).strip().strip('"').strip("'")


def _streamlit_secret(key: str) -> str:
    try:
        import streamlit as st

        if hasattr(st, "secrets") and key in st.secrets:
            return clean_value(st.secrets[key])
    except Exception:
        pass
    return ""


def get_env(key: str, default: str = "") -> str:
    """os.environ → st.secrets → default 순서로 읽고 정규화한다."""
    val = clean_value(os.getenv(key))
    if val:
        return val
    val = _streamlit_secret(key)
    if val:
        return val
    return clean_value(default)


def get_int(key: str, default: int) -> int:
    try:
        return int(get_env(key, str(default)))
    except Exception:
        return default


def get_float(key: str, default: float) -> float:
    try:
        return float(get_env(key, str(default)))
    except Exception:
        return default


def split_csv(value: str, default: Iterable[str] | None = None) -> list[str]:
    raw = clean_value(value)
    if not raw:
        return list(default or [])
    return [x.strip() for x in raw.replace("\n", ",").split(",") if x.strip()]


def get_router_candidates() -> list[str]:
    candidates = split_csv(get_env("HF_MODEL_CANDIDATES"), DEFAULT_ROUTER_CANDIDATES)
    # Backward compatibility: old HF_MODEL_ID or HF_ROUTER_MODEL may exist.
    preferred = get_env("HF_ROUTER_MODEL") or get_env("HF_MODEL_ID")
    ordered: list[str] = []
    if preferred:
        ordered.append(preferred)
    for item in candidates:
        if item not in ordered:
            ordered.append(item)
    return ordered


def load_config() -> dict:
    return {
        "llm_engine": get_env("LLM_ENGINE", "hf_api"),
        "hf_token": get_env("HF_TOKEN", ""),
        "hf_router_model": get_env("HF_ROUTER_MODEL", get_env("HF_MODEL_ID", DEFAULT_ROUTER_CANDIDATES[0])),
        "hf_model_candidates": get_router_candidates(),
        "max_tokens": get_int("HF_MAX_TOKENS", 1400),
        "temperature": get_float("HF_TEMPERATURE", 0.2),
        "timeout_connect": get_int("HF_TIMEOUT_CONNECT", 10),
        "timeout_read": get_int("HF_TIMEOUT_READ", 120),
        "max_retries": get_int("HF_MAX_RETRIES", 3),
        "use_4bit": get_env("USE_4BIT", "true").lower() == "true",
        "use_gpu": get_env("USE_GPU", "true").lower() == "true",
        "port": get_int("PORT", 8501),
    }
