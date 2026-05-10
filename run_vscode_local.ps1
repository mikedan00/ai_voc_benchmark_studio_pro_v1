# VS Code / Windows PowerShell local launcher
Set-Location $PSScriptRoot
if (!(Test-Path ".\venv")) {
  py -3.11 -m venv venv
}
. .\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
if (!(Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host "Created .env from .env.example. Edit HF_TOKEN before production use."
}
python scripts/check_env.py
streamlit run app.py --server.port 8501
