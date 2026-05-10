# AI VOC & Benchmark Studio Pro

세 개의 기존 소스 프로젝트를 통합·개선한 최종 Streamlit 애플리케이션입니다.

## 통합된 핵심 기능

- **VOC 자동 수집**
  - DuckDuckGo Web
  - DuckDuckGo News
  - Google News RSS
  - 삼성 Members
  - 네이버 지식인
  - 네이버 카페
  - DC인사이드
  - 클리앙
  - 사용자 직접 URL
- **VOC 정제/분류**
  - URL 정규화 및 추적 파라미터 제거
  - URL/제목/본문 기반 중복 제거
  - 카테고리 분류
  - 감성 힌트
  - 소스/채널 분류
- **파일 업로드 기반 지식화**
  - CSV/XLSX/TXT/DOCX 업로드
  - VOC 변환
  - 경량 RAG 청크 생성
- **RAG 검색 및 질의응답**
  - VOC + 업로드 문서 통합 검색
  - 근거 Context 생성
  - HF Router 기반 답변 생성
- **LLM 분석**
  - Hugging Face Router Chat Completions 사용
  - `text_generation()` fallback 제거
  - 다중 모델 후보 fallback
  - VOC 구조화 분석
  - 요구사항명세서(SRS) 생성
  - VOC 요약·인사이트 리포트 생성
- **경쟁사 벤치마킹**
  - 기존 보고서 업로드 → 작성 가이드 자동 추출
  - 자사/경쟁사 VOC 공개 웹 수집
  - 자사/경쟁사 VOC 비교 분석
  - 제품 사양 자동 검색
  - AI 사양 비교 매트릭스
  - 최종 벤치마킹 보고서 생성
- **Office Export**
  - Markdown
  - JSON
  - CSV
  - Word `.docx`
  - PowerPoint `.pptx`
  - 전체 결과 `.zip`

## VS Code 로컬 실행

```powershell
cd ai_voc_benchmark_studio_pro
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -U pip
pip install -r requirements.txt
copy .env.example .env
streamlit run app.py
```

`.env` 파일에 다음 값을 입력하세요.

```env
HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
HF_ROUTER_MODEL=google/gemma-4-26B-A4B-it:deepinfra
HF_MODEL_CANDIDATES=google/gemma-4-26B-A4B-it:deepinfra,google/gemma-4-26B-A4B-it:novita,Zyphra/ZAYA1-8B,mistralai/Mistral-7B-Instruct-v0.3
HF_MAX_TOKENS=1800
HF_TEMPERATURE=0.2
```

## Streamlit Cloud 배포

1. 이 폴더 전체를 GitHub에 업로드합니다.
2. Streamlit Cloud에서 새 앱을 만들고 `app.py`를 지정합니다.
3. App settings → Secrets에 아래 값을 넣습니다.

```toml
HF_TOKEN = "hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
HF_ROUTER_MODEL = "google/gemma-4-26B-A4B-it:deepinfra"
HF_MODEL_CANDIDATES = "google/gemma-4-26B-A4B-it:deepinfra,google/gemma-4-26B-A4B-it:novita,Zyphra/ZAYA1-8B,mistralai/Mistral-7B-Instruct-v0.3"
HF_MAX_TOKENS = "1800"
HF_TEMPERATURE = "0.2"
```

4. 배포 후 앱 사이드바에서 **LLM 연결 테스트**를 실행합니다.

## 폴더 구조

```text
ai_voc_benchmark_studio_pro/
  app.py
  models/
    config.py
    hf_api_engine.py
    local_engine.py
    prompt_templates.py
  utils/
    benchmarking.py
    doc_generator.py
    file_ingestor.py
    office_export.py
    ppt_generator.py
    rag_engine.py
    voc_collector.py
    voc_report.py
  scripts/
  tests/
  .streamlit/config.toml
  .env.example
  requirements.txt
  Dockerfile
```

## 주의 사항

- `.env`, `.streamlit/secrets.toml`, 실제 HF 토큰은 GitHub에 올리지 마세요.
- 일부 웹사이트는 크롤링을 차단할 수 있습니다. 이 경우 사용자 URL, 파일 업로드, RSS 수집을 병행하세요.
- Streamlit Cloud에서는 로컬 대형 모델 설치 대신 HF Router/API 방식만 사용하는 것을 권장합니다.
- 모델/provider 조합이 실패하면 사이드바의 fallback 후보를 바꿔 연결 테스트를 실행하세요.
