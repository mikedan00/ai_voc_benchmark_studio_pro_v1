"""
models/hf_api_engine.py
Hugging Face Router 기반 API 엔진

기존 api-inference.huggingface.co/models/{model} 방식 대신
https://router.huggingface.co/v1/chat/completions 를 사용한다.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Iterator, Optional

import requests

from models.config import MODEL_MAP, ModelInfo, clean_value, get_router_candidates, load_config
from models.prompt_templates import (
    DEFAULT_PROMPT_PRESET,
    build_analysis_prompt,
    build_srs_markdown_prompt,
)

LOGGER = logging.getLogger(__name__)
HF_ROUTER_URL = "https://router.huggingface.co/v1/chat/completions"

SYSTEM_KO = (
    "당신은 삼성전자 갤럭시 스마트폰 시니어 제품 기획 전문가입니다. "
    "항상 한국어로 답변하고, VOC 근거·우선순위·정량 KPI·수용 기준을 명확히 작성하세요."
)


@dataclass(slots=True)
class AttemptLog:
    model: str
    ok: bool = False
    status_code: int | None = None
    error_type: str = ""
    message: str = ""
    elapsed_sec: float = 0.0


@dataclass(slots=True)
class SetupResult:
    ok: bool
    model_id: str = ""
    label: str = ""
    message: str = ""
    attempts: list[AttemptLog] = field(default_factory=list)


def _attempt_to_dict(attempt: AttemptLog) -> dict:
    """slots=True dataclass도 Streamlit 상태/JSON에 안전하게 넣을 수 있도록 dict로 변환한다."""
    return asdict(attempt)


class HFApiEngine:
    """HF Router Chat Completion 싱글톤 엔진."""

    _inst: Optional["HFApiEngine"] = None

    def __new__(cls) -> "HFApiEngine":
        if cls._inst is None:
            cls._inst = super().__new__(cls)
            cls._inst._token = ""
            cls._inst._model_id = ""
            cls._inst._model_info = None
            cls._inst._ready = False
            cls._inst._max_tokens = 1400
            cls._inst._temperature = 0.2
            cls._inst._timeout = (10, 120)
            cls._inst._max_retries = 3
            cls._inst._attempts = []
        return cls._inst

    def setup(
        self,
        hf_token: str,
        model_id: str = "",
        max_tokens: int = 1400,
        temperature: float = 0.2,
        auto_fallback: bool = True,
        candidates: list[str] | None = None,
    ) -> dict:
        cfg = load_config()
        token = clean_value(hf_token) or cfg["hf_token"]
        if not token:
            return {
                "ok": False,
                "model_id": "",
                "label": "",
                "message": "HF_TOKEN이 없습니다. .env 또는 Streamlit secrets를 확인하세요.",
                "attempts": [],
            }

        self._token = token
        self._max_tokens = int(max_tokens or cfg["max_tokens"])
        self._temperature = float(temperature if temperature is not None else cfg["temperature"])
        self._timeout = (int(cfg["timeout_connect"]), int(cfg["timeout_read"]))
        self._max_retries = int(cfg["max_retries"])

        preferred = clean_value(model_id) or cfg["hf_router_model"]
        ordered = []
        if preferred:
            ordered.append(preferred)
        if auto_fallback:
            for item in candidates or get_router_candidates():
                if item not in ordered:
                    ordered.append(item)

        attempts: list[AttemptLog] = []
        for candidate in ordered:
            attempt = self._probe(candidate)
            attempts.append(attempt)
            if attempt.ok:
                self._activate(candidate)
                label = self.model_label
                self._attempts = attempts
                return {
                    "ok": True,
                    "model_id": candidate,
                    "label": label,
                    "message": f"✅ HF Router 연결 성공: {candidate}",
                    "attempts": [_attempt_to_dict(a) for a in attempts],
                }

        self._ready = False
        self._attempts = attempts
        tried = ", ".join(a.model for a in attempts)
        details = "\n".join(
            f"- {a.model}: {a.status_code or a.error_type or 'ERR'} · {a.message}" for a in attempts
        )
        return {
            "ok": False,
            "model_id": "",
            "label": "",
            "message": f"❌ 모든 모델 접근 실패\n시도한 모델: {tried}\n\n{details}",
            "attempts": [_attempt_to_dict(a) for a in attempts],
        }

    def _probe(self, model_id: str) -> AttemptLog:
        started = time.perf_counter()
        try:
            response = requests.post(
                HF_ROUTER_URL,
                headers=self._headers(),
                json={
                    "model": model_id,
                    "messages": [
                        {"role": "system", "content": "You are a concise assistant."},
                        {"role": "user", "content": "ping"},
                    ],
                    "max_tokens": 8,
                    "temperature": 0,
                    "stream": False,
                },
                timeout=self._timeout,
            )
            elapsed = time.perf_counter() - started
            if response.status_code == 200:
                return AttemptLog(model=model_id, ok=True, status_code=200, message="ok", elapsed_sec=elapsed)
            return AttemptLog(
                model=model_id,
                ok=False,
                status_code=response.status_code,
                message=_classify_error(response.status_code, _safe_body(response)),
                elapsed_sec=elapsed,
            )
        except requests.Timeout as exc:
            return AttemptLog(model=model_id, error_type="timeout", message=str(exc), elapsed_sec=time.perf_counter() - started)
        except requests.RequestException as exc:
            return AttemptLog(model=model_id, error_type="request", message=str(exc), elapsed_sec=time.perf_counter() - started)
        except Exception as exc:
            return AttemptLog(model=model_id, error_type=type(exc).__name__, message=str(exc), elapsed_sec=time.perf_counter() - started)

    def _activate(self, model_id: str) -> None:
        self._model_id = model_id
        self._model_info = MODEL_MAP.get(model_id, ModelInfo(model_id, model_id, "", "custom"))
        self._ready = True

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def model_label(self) -> str:
        return self._model_info.label if self._model_info else self._model_id

    @property
    def attempts(self) -> list[dict]:
        return [_attempt_to_dict(a) for a in self._attempts]

    def generate(
        self,
        prompt: str,
        system: str = SYSTEM_KO,
        max_tokens: int | None = None,
        temperature: float | None = None,
        retries: int | None = None,
    ) -> str:
        if not self._ready:
            raise RuntimeError("HF Router 엔진이 초기화되지 않았습니다. API 연결 확인을 먼저 실행하세요.")

        payload = {
            "model": self._model_id,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": min(int(max_tokens or self._max_tokens), 4096),
            "temperature": float(self._temperature if temperature is None else temperature),
            "stream": False,
        }
        return self._request_with_retry(payload, int(retries or self._max_retries))

    def generate_stream(
        self,
        prompt: str,
        system: str = SYSTEM_KO,
        max_tokens: int | None = None,
        temperature: float | None = None,
        retries: int | None = None,
    ) -> Iterator[str]:
        """Router streaming. 실패 시 non-stream 재시도 후 chunk yield."""
        if not self._ready:
            raise RuntimeError("HF Router 엔진이 초기화되지 않았습니다. API 연결 확인을 먼저 실행하세요.")

        payload = {
            "model": self._model_id,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": min(int(max_tokens or self._max_tokens), 4096),
            "temperature": float(self._temperature if temperature is None else temperature),
            "stream": True,
        }
        max_attempts = int(retries or 2)
        last_error = ""
        for attempt in range(max_attempts):
            try:
                with requests.post(
                    HF_ROUTER_URL,
                    headers=self._headers(),
                    json=payload,
                    timeout=self._timeout,
                    stream=True,
                ) as response:
                    if response.status_code != 200:
                        last_error = _classify_error(response.status_code, _safe_body(response))
                        if _should_retry(response.status_code) and attempt < max_attempts - 1:
                            _sleep_backoff(attempt)
                            continue
                        raise RuntimeError(last_error)

                    for raw_line in response.iter_lines(decode_unicode=True):
                        if not raw_line:
                            continue
                        line = raw_line.strip()
                        if line == "data: [DONE]":
                            return
                        if not line.startswith("data: "):
                            continue
                        data = json.loads(line[6:])
                        delta = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if delta:
                            yield delta
                    return
            except Exception as exc:
                last_error = str(exc)
                if attempt < max_attempts - 1:
                    _sleep_backoff(attempt)
                    continue
                # fallback: non-streaming으로 한 번 더 받되 UI에는 chunk로 표시
                full = self.generate(prompt, system=system, max_tokens=max_tokens, temperature=temperature, retries=1)
                for i in range(0, len(full), 80):
                    yield full[i : i + 80]
                return
        raise RuntimeError(last_error or "HF Router streaming failed")

    def _request_with_retry(self, payload: dict, retries: int) -> str:
        errors: list[str] = []
        for attempt in range(retries):
            try:
                response = requests.post(
                    HF_ROUTER_URL,
                    headers=self._headers(),
                    json=payload,
                    timeout=self._timeout,
                )
                if response.status_code == 200:
                    data = response.json()
                    return data["choices"][0]["message"]["content"].strip()

                err = _classify_error(response.status_code, _safe_body(response))
                errors.append(err)
                if _should_retry(response.status_code) and attempt < retries - 1:
                    _sleep_backoff(attempt)
                    continue
                raise RuntimeError(err)
            except requests.Timeout:
                errors.append("timeout")
                if attempt < retries - 1:
                    _sleep_backoff(attempt)
                    continue
                raise RuntimeError("HF Router 요청 타임아웃")
            except requests.RequestException as exc:
                errors.append(str(exc))
                if attempt < retries - 1:
                    _sleep_backoff(attempt)
                    continue
                raise RuntimeError(f"HF Router 요청 실패: {exc}")
        raise RuntimeError(" / ".join(errors))


api_engine = HFApiEngine()


def _safe_body(response: requests.Response) -> dict | str:
    try:
        return response.json()
    except Exception:
        return response.text[:800]


def _classify_error(status_code: int, body: dict | str) -> str:
    text = json.dumps(body, ensure_ascii=False) if isinstance(body, dict) else str(body)
    low = text.lower()
    if status_code == 401:
        return "401 unauthorized: HF_TOKEN이 없거나 잘못되었습니다."
    if status_code == 402:
        return "402 payment required: Inference Providers 결제/크레딧 설정을 확인하세요."
    if status_code == 403:
        if any(x in low for x in ["gated", "license", "permission", "forbidden"]):
            return "403 forbidden: 모델 라이선스, gated access, 또는 fine-grained token 권한을 확인하세요."
        return "403 forbidden: provider/model 접근 권한이 없습니다."
    if status_code == 404:
        return "404 not found: 모델 ID 또는 provider suffix가 잘못되었거나 지원되지 않습니다."
    if status_code == 422:
        return "422 unprocessable entity: chat completion payload 또는 모델-태스크 조합이 맞지 않습니다."
    if status_code == 429:
        return "429 rate limit: 호출 한도 초과입니다. 잠시 후 재시도하세요."
    if status_code in (500, 502, 503, 504):
        return f"{status_code} server error: provider 일시 장애 또는 모델 로딩 상태입니다."
    return f"HTTP {status_code}: {text[:400]}"


def _should_retry(status_code: int) -> bool:
    return status_code in {408, 409, 425, 429, 500, 502, 503, 504}


def _sleep_backoff(attempt: int) -> None:
    time.sleep(min(2 ** attempt, 8) + random.random())


def _get(obj, attr: str, default=""):
    return getattr(obj, attr) if hasattr(obj, attr) else (obj.get(attr, default) if isinstance(obj, dict) else default)


def _build_voc_payload(voc_list: list) -> dict:
    from collections import Counter, defaultdict

    cats = Counter(_get(v, "category", "기타") or "기타" for v in voc_list)
    srcs = Counter(_get(v, "source", "unknown") or "unknown" for v in voc_list)
    snts = Counter(_get(v, "sentiment", "neutral") or "neutral" for v in voc_list)

    examples: dict[str, list[str]] = defaultdict(list)
    for item in voc_list:
        cat = _get(item, "category", "기타") or "기타"
        title = clean_value(_get(item, "title", ""))
        content = clean_value(_get(item, "content", ""))
        text = title if title else content
        if text and len(examples[cat]) < 10:
            examples[cat].append(text[:220])

    return {
        "total_voc": len(voc_list),
        "category_counts": dict(cats.most_common()),
        "source_counts": dict(srcs.most_common()),
        "sentiment_counts": dict(snts.most_common()),
        "negative_ratio_pct": round(snts.get("negative", 0) / max(len(voc_list), 1) * 100, 1),
        "examples_by_category": dict(examples),
    }


def analyze_voc_api(
    voc_list: list,
    model_info_str: str = "갤럭시 스마트폰",
    rag_context: str = "",
    prompt_preset: str = DEFAULT_PROMPT_PRESET,
    custom_prompt: str = "",
) -> dict:
    """VOC → 구조화 분석 JSON.

    개선 프롬프트 프리셋을 적용해 역할 부여, 단계별 지시, 입출력 예시,
    RAG 근거 반영, 요구사항 스키마를 함께 강제한다.
    """
    payload = _build_voc_payload(voc_list)
    prompt = build_analysis_prompt(
        payload=payload,
        model_info_str=model_info_str,
        rag_context=rag_context,
        preset_key=prompt_preset,
        custom_instruction=custom_prompt,
    )
    raw = api_engine.generate(prompt, max_tokens=3000, temperature=0.1)
    try:
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                parsed.setdefault("prompt_preset", prompt_preset)
                return parsed
    except Exception:
        LOGGER.exception("Failed to parse analysis JSON")
    return {
        "executive_summary": raw[:1000] if raw else "분석 결과를 파싱하지 못했습니다.",
        "pipeline_design": [],
        "problem_statements": [],
        "critical_issues": [],
        "requirements": [],
        "non_functional_requirements": [],
        "roadmap": [],
        "kpis": [],
        "key_insights": [],
        "open_questions": [],
        "prompt_preset": prompt_preset,
    }

def build_srs_prompt(
    voc_list: list,
    analysis: dict,
    product_name: str,
    version: str,
    author: str,
    rag_context: str = "",
    prompt_preset: str = DEFAULT_PROMPT_PRESET,
    custom_prompt: str = "",
) -> str:
    payload = _build_voc_payload(voc_list)
    return build_srs_markdown_prompt(
        payload=payload,
        analysis=analysis,
        product_name=product_name,
        version=version,
        author=author,
        ai_model=api_engine.model_id,
        rag_context=rag_context,
        preset_key=prompt_preset,
        custom_instruction=custom_prompt,
    )
