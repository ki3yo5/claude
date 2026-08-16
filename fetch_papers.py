import json
import sys
import time
from datetime import datetime
import requests

# --------------------------------------------------
# ★ 設定変更エリア（JEL分類コードを指定）
# --------------------------------------------------
# 例: C21 (Causal Inference / Cross-Sectional Models)
#     C13 (Estimation)
#     Q18 (Agricultural Policy)
JEL_CODES = ["D57", "E32", "L14","Q54"]

# 対象ジャーナルの絞り込み（空リスト [] で全ジャーナル対象）
TARGET_JOURNALS = [
    "Journal of Econometrics",
    "Econometrica",
    "Review of Economic Studies",
    "American Economic Review",
]

YEAR_START = datetime.now().year - 1
LIMIT_PER_JEL = 5


def fetch_semantic_scholar_papers(jel_code: str, limit: int = 5):
    url = "https://api.semanticscholar.org/graph/v1/paper/search"

    # JELコードを明示的に検索クエリに指定 ("JEL C21" または "JEL: C21")
    query = f"JEL {jel_code}"

    params = {
        "query": query,
        "limit": limit,
        "year": f"{YEAR_START}-",
        "fields": "title,authors,abstract,url,venue,publicationDate,citationCount",
    }
    headers = {"User-Agent": "ClaudeCode-ResearchAssistant/1.0"}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        papers = response.json().get("data", [])

        # ジャーナル絞り込み
        if TARGET_JOURNALS:
            filtered = []
            for p in papers:
                venue = p.get("venue", "") or ""
                if any(
                    tj.lower() in venue.lower() for tj in TARGET_JOURNALS
                ):
                    filtered.append(p)
            return filtered

        return papers
    except requests.exceptions.RequestException as e:
        print(f"APIエラー (JEL: {jel_code}): {e}", file=sys.stderr)
        return []


def main():
    all_papers = {}

    for jel in JEL_CODES:
        papers = fetch_semantic_scholar_papers(jel, limit=LIMIT_PER_JEL)
        for p in papers:
            paper_id = p.get("paperId")
            if paper_id and paper_id not in all_papers:
                authors = [
                    a.get("name") for a in p.get("authors", []) if a.get("name")
                ]
                all_papers[paper_id] = {
                    "jel_code": jel,
                    "title": p.get("title"),
                    "authors": ", ".join(authors),
                    "venue": p.get("venue") or "N/A",
                    "pub_date": p.get("publicationDate") or "N/A",
                    "citations": p.get("citationCount", 0),
                    "url": p.get("url"),
                    "abstract": p.get("abstract") or "No abstract available.",
                }
        # APIレート制限対策（1.5秒待機）
        time.sleep(1.5)

    output = {
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "target_jel_codes": JEL_CODES,
        "paper_count": len(all_papers),
        "papers": list(all_papers.values()),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()