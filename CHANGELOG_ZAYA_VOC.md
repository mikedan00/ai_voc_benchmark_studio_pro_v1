# 변경 내역

## 2026-05-09

### 모델 선택
- `models/config.py`에 `Zyphra/ZAYA1-8B` 추가
- `models/config.py`에 `Zyphra/ZAYA1-74B-preview` 추가
- `.env.example`, Streamlit secrets 예시에 ZAYA 후보 추가

### VOC 요약·인사이트 리포트
- `utils/voc_report.py` 추가
- `models/prompt_templates.py`에 `build_voc_insight_report_prompt()` 추가
- `app.py`에 `📑 VOC 요약·인사이트 리포트 생성` 버튼 추가
- `app.py`에 `⚙️ AI 없이 기본 VOC 리포트 생성` 버튼 추가
- `📑 리포트` 탭 추가
- Markdown/DOCX/ZIP 내보내기 추가

### 안정화
- 기존 `with main_tab` 중복 구문 수정
- `python -m py_compile` 통과 확인
