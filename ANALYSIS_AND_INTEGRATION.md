# 3개 소스 상세 분석 및 최종 통합 내역

## 1. 분석 대상

### A. benchmarking_app 원본
- 주요 목적: 경쟁사 벤치마킹 보고서 자동 생성
- 핵심 기능: Hugging Face LLM 호출, DuckDuckGo 검색, VOC 수집, 스펙 수집, AI 보고서 생성
- 강점: 경쟁사 비교 흐름이 명확함. 보고서 구조가 단계형이라 사용자가 따라가기 쉬움.
- 한계: 초기 버전에서 `text_generation` 호출 문제 가능. RAG, 파일 기반 지식화, 고급 UI가 부족함.

### B. benchmarking_app_office_export
- 주요 목적: A 버전에 Word/PPTX 내보내기 추가
- 핵심 기능: DOCX/PPTX 생성, Markdown 섹션 분리, 한글 폰트 대응, VOC 멀티소스 수집 강화
- 강점: 산출물 기능이 우수함. 실무 보고서 다운로드 흐름이 좋음.
- 한계: 앱이 단일 `app.py` 중심이라 확장성과 테스트성이 낮음.

### C. galaxy_voc_zaya1_vscode_streamlit_full_source
- 주요 목적: Galaxy VOC 수집, RAG, HF Router/ZAYA/Gemma 연동, SRS 생성
- 핵심 기능: 커뮤니티 수집, URL 수집, 파일 업로드, RAG 검색, HF Router fallback, SRS/DOCX/PPTX/ZIP
- 강점: 가장 모듈화가 잘 되어 있고 VS Code/Streamlit Cloud 배포 구조가 좋음.
- 한계: 경쟁사 벤치마킹, 스펙 비교, 공개 웹/뉴스/RSS VOC 수집이 별도 벤치마킹 앱보다 약함.

## 2. 통합 전략

Galaxy VOC 프로젝트를 베이스로 사용했습니다. 이유는 다음과 같습니다.

1. `models/`, `utils/`, `scripts/` 구조가 이미 모듈화되어 있음
2. HF Router Chat Completions 방식이 기존 `text_generation` 오류를 피하기에 적합함
3. 파일 업로드/RAG/SRS/ZIP 산출물 구조가 가장 확장 가능함
4. VS Code와 Streamlit Cloud 배포 자료가 이미 포함되어 있음

그 위에 벤치마킹 앱의 다음 기능을 통합했습니다.

- 벤치마킹 가이드 추출
- 공개 웹/뉴스/RSS VOC 수집
- 자사/경쟁사 VOC 비교 분석
- 제품 사양 자동 검색
- AI 사양 비교 분석
- 최종 벤치마킹 보고서 생성
- Word/PPTX 보고서 내보내기

## 3. 새로 개선한 부분

### UI/UX
- 홈, VOC 수집, 업로드, RAG, VOC 분석, 벤치마킹, 리포트/SRS, 내보내기, 실행/배포 탭으로 재구성
- Hero header, KPI 카드, 상태 badge, 통계 차트, 테이블/카드 전환 UI 추가
- AI 미연결 상태에서도 규칙 기반 기능을 사용할 수 있도록 구성

### 아키텍처
- `utils/benchmarking.py` 추가
- `utils/office_export.py` 추가
- 기존 `models/hf_api_engine.py` 유지
- 기존 `utils/voc_collector.py`, `file_ingestor.py`, `rag_engine.py`, `doc_generator.py`, `ppt_generator.py`, `voc_report.py` 유지

### LLM 호출 안정성
- HF Router Chat Completions 방식만 사용
- `text_generation` fallback 제거
- 모델 후보 fallback 유지
- 연결 로그를 UI에서 확인 가능

### VOC 수집 확장
- DuckDuckGo Web
- DuckDuckGo News
- Google News RSS
- 삼성 Members
- 네이버 지식인
- 네이버 카페
- DC인사이드
- 클리앙
- 사용자 URL
- CSV/XLSX/TXT/DOCX 업로드

### 분석 기능
- 규칙 기반 카테고리/감성 힌트
- LLM 기반 구조화 VOC 분석
- VOC 인사이트 리포트
- SRS Markdown 생성
- RAG 기반 질의응답
- 자사/경쟁사 VOC 비교
- 사양 비교 매트릭스
- 전략 보고서 생성

### 산출물
- Markdown
- JSON
- CSV
- DOCX
- PPTX
- 전체 ZIP

## 4. 검증

아래 검증을 완료했습니다.

```bash
python -m py_compile app.py models/*.py utils/*.py
pytest -q
```

결과: 4개 테스트 통과.
