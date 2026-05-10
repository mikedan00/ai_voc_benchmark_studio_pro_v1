# Pre-deploy sanity check for Streamlit Cloud-compatible dependencies
Set-Location $PSScriptRoot
py -3.11 -m venv venv
. .\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m py_compile app.py models\config.py models\hf_api_engine.py models\prompt_templates.py utils\voc_report.py utils\doc_generator.py
streamlit run app.py --server.port 8501
