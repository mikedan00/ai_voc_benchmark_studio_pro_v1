# VS Code 실행 가이드

```powershell
cd ai_voc_benchmark_studio_pro
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -U pip
pip install -r requirements.txt
copy .env.example .env
streamlit run app.py
```

PowerShell 실행 정책 오류가 나면 관리자 권한이 아닌 일반 PowerShell에서 아래를 1회 실행합니다.

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

VS Code 디버깅은 `.vscode/launch.json`의 `Streamlit: app.py` 구성을 사용하세요.
