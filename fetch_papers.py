import json
import os
import sys
import time
from datetime import datetime, timedelta
from urllib.parse import quote_plus

import requests

# --------------------------------------------------
# ★ 設定変更エリア
# --------------------------------------------------
# JEL分類コードと検索キーワードの対応。
# Semantic Scholar は JEL分類を索引していないため、分野を表す語で検索する。
JEL_QUERIES = {
    "D57": "input-output production networks",
    "E32": "business cycles",
    "L14": "transactional relationships contracts reputation",
    "Q54": "climate natural disasters",
}

# 対象ジャーナルの絞り込み（空リスト [] で全ジャーナル対象）
TARGET_JOURNALS = [
    "Journal of Econometrics",
    "Econometrica",
    "Review of Economic Studies",
    "American Economic Review",
]

# 過去何日分の論文を対象にするか（掲載日の登録が遅れる場合があるため月より長めに取る）
LOOKBACK_DAYS = 90
LIMIT_PER_JEL = 5

# Semantic Scholar APIキーのレート制限: 全エンドポイント合計で 1リクエスト/秒。
# 余裕を持たせ、リトライを含む全リクエストの間隔をこの秒数以上に保つ。
MIN_REQUEST_INTERVAL = 1.1
_last_request_at = 0.0

MAX_RETRIES = 3
BACKOFF_SECONDS = 2
REQUEST_TIMEOUT = 30
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"

# 終了コード
EXIT_OK = 0
EXIT_ALL_FAILED = 1
EXIT_PARTIAL = 2


def build_headers():
    headers = {"User-Agent": "ClaudeCode-ResearchAssistant/1.0"}
    api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
    if api_key:
        headers["x-api-key"] = api_key
    return headers


def throttle():
    """直前のリクエストから MIN_REQUEST_INTERVAL 秒が経つまで待つ。"""
    global _last_request_at
    wait = MIN_REQUEST_INTERVAL - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


def get_with_retry(params):
    """429と5xxのみ指数バックオフで再試行する。403などの遮断はそのまま例外を送出する。"""
    for attempt in range(MAX_RETRIES + 1):
        throttle()
        response = requests.get(
            SEARCH_URL, params=params, headers=build_headers(), timeout=REQUEST_TIMEOUT
        )
        if response.status_code not in RETRYABLE_STATUS or attempt == MAX_RETRIES:
            response.raise_for_status()
            return response
        time.sleep(BACKOFF_SECONDS * 2**attempt)


def fetch_semantic_scholar_papers(jel_code, limit=LIMIT_PER_JEL):
    start_date = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    params = {
        "query": JEL_QUERIES[jel_code],
        "limit": limit,
        "publicationDateOrYear": f"{start_date}:",
        "fields": "title,authors,abstract,url,venue,publicationDate,citationCount",
    }
    # 件数制限の後ではなく、検索時点で対象誌に絞る
    if TARGET_JOURNALS:
        params["venue"] = ",".join(TARGET_JOURNALS)

    response = get_with_retry(params)
    return response.json().get("data") or []


def scholar_url(title):
    """Google Scholarの検索リンク。開いた先の「保存」でマイライブラリに登録できる。"""
    return f"https://scholar.google.com/scholar?q={quote_plus(chr(34) + title + chr(34))}"


def main():
    all_papers = {}
    failed = {}

    for jel in JEL_QUERIES:
        try:
            papers = fetch_semantic_scholar_papers(jel)
        except (requests.exceptions.RequestException, ValueError) as e:
            print(f"APIエラー (JEL: {jel}): {e}", file=sys.stderr)
            failed[jel] = str(e)
            papers = []

        for p in papers:
            paper_id = p.get("paperId")
            if paper_id and paper_id not in all_papers:
                authors = [
                    a.get("name") for a in p.get("authors") or [] if a.get("name")
                ]
                title = p.get("title") or ""
                all_papers[paper_id] = {
                    "jel_code": jel,
                    "title": title,
                    "authors": ", ".join(authors),
                    "venue": p.get("venue") or "N/A",
                    "pub_date": p.get("publicationDate") or "N/A",
                    "citations": p.get("citationCount", 0),
                    "url": p.get("url"),
                    "scholar_url": scholar_url(title),
                    "abstract": p.get("abstract") or "No abstract available.",
                }

    output = {
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "target_jel_codes": list(JEL_QUERIES),
        "lookback_days": LOOKBACK_DAYS,
        "failed_jel_codes": failed,
        "paper_count": len(all_papers),
        "papers": list(all_papers.values()),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))

    if len(failed) == len(JEL_QUERIES):
        return EXIT_ALL_FAILED
    return EXIT_PARTIAL if failed else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
