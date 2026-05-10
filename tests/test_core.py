from utils.benchmarking import normalize_url, infer_voc_category, infer_sentiment, summarize_voc_locally
from utils.office_export import split_sections


def test_normalize_url_removes_tracking():
    url = "https://www.example.com/a/b/?utm_source=x&fbclid=abc&q=1"
    assert normalize_url(url) == "https://example.com/a/b?q=1"


def test_infer_voc_category_and_sentiment():
    text = "배터리 발열 문제가 심하고 충전도 느립니다"
    assert infer_voc_category(text) == "배터리/발열"
    label, score = infer_sentiment(text)
    assert label in {"부정", "개선요청"}
    assert score >= 1


def test_summarize_voc_locally():
    items = [
        {"title": "배터리 문제", "category": "배터리/발열", "sentiment_hint": "부정", "source": "test"},
        {"title": "카메라 좋음", "category": "카메라/화질", "sentiment_hint": "긍정", "source": "test"},
    ]
    s = summarize_voc_locally(items)
    assert s["voc_count"] == 2
    assert s["category_distribution"]["배터리/발열"] == 1


def test_split_sections():
    sections = split_sections("# 제목\n\n## 1장\n- 항목\n## 2장\n본문")
    assert len(sections) >= 2
