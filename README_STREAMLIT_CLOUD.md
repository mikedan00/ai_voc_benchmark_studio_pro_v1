# Streamlit Cloud 배포 가이드

1. GitHub 새 저장소를 만듭니다.
2. 이 프로젝트 폴더 전체를 push합니다.
3. Streamlit Cloud에서 `New app`을 클릭합니다.
4. Repository, branch, `app.py`를 선택합니다.
5. Secrets에 HF_TOKEN과 모델 후보를 입력합니다.

```toml
HF_TOKEN = "hf_xxx"
HF_ROUTER_MODEL = "google/gemma-4-26B-A4B-it:deepinfra"
HF_MODEL_CANDIDATES = "google/gemma-4-26B-A4B-it:deepinfra,google/gemma-4-26B-A4B-it:novita,Zyphra/ZAYA1-8B,mistralai/Mistral-7B-Instruct-v0.3"
```

배포 후 사이드바에서 `LLM 연결 테스트`를 눌러 정상 연결 여부를 확인하세요.
