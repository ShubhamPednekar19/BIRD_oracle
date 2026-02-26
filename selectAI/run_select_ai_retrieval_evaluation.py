#!/usr/bin/env python3
"""Evaluate Select AI retrieval quality using DBMS_CLOUD_AI.GENERATE(showprompt).

For each item in dev_with_metadata.json:
- Build prompt = question + ' ' + evidence
- Execute DBMS_CLOUD_AI.GENERATE(... action => 'showprompt')
- Parse table names from SYSTEM messages that contain CREATE TABLE ...
- Compare with expected tables from dataset and compute P/R/F1 @3/@5/@10

Outputs:
- Per-batch HTML report every 100 questions
- Full HTML report across all questions
"""

import argparse
import html
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Set, Tuple

try:
    import oracledb
except ImportError:
    print("Error: python-oracledb is required. Install with: pip install oracledb")
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from run_hybrid_search_evaluation import calculate_precision_recall_f1_at_k


DEFAULT_INPUT = "../dev_with_metadata.json"
DEFAULT_BATCH_SIZE = 100
DEFAULT_TEST_SIZE = 3


@dataclass
class EvalRow:
    question_id: int
    db_id: str
    question: str
    expected_tables: List[str]
    discovered_tables: List[str]
    p_at_3: float = 0.0
    r_at_3: float = 0.0
    f1_at_3: float = 0.0
    p_at_5: float = 0.0
    r_at_5: float = 0.0
    f1_at_5: float = 0.0
    p_at_10: float = 0.0
    r_at_10: float = 0.0
    f1_at_10: float = 0.0
    error: str = ""


CREATE_TABLE_PATTERN = re.compile(r'CREATE\s+TABLE\s+"[^"]+"\."([^"]+)"', re.IGNORECASE)


def _normalize_json_text(raw: str) -> str:
    """Normalize wrapped output text that may include hard line breaks/spaces."""
    if raw is None:
        return ""
    return re.sub(r"\s+", " ", raw).strip()




def _format_hms(total_seconds: float) -> str:
    secs = max(0, int(total_seconds))
    h, rem = divmod(secs, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def _print_progress(done: int, total: int, started_at: float) -> None:
    if total <= 0:
        return
    elapsed = time.time() - started_at
    rate = done / elapsed if elapsed > 0 else 0.0
    eta_seconds = (total - done) / rate if rate > 0 else 0.0
    percent = (done / total) * 100

    bar_width = 30
    filled = int((done / total) * bar_width)
    bar = "#" * filled + "-" * (bar_width - filled)

    msg = (
        f"\rProgress [{bar}] {done}/{total} ({percent:5.1f}%) "
        f"Elapsed: {_format_hms(elapsed)} ETA: {_format_hms(eta_seconds)}"
    )
    print(msg, end="", flush=True)


def _payload_to_text(payload) -> str:
    """Convert DB payload to JSON string, handling CLOB/LOB values."""
    if payload is None:
        return ""
    if isinstance(payload, (str, bytes, bytearray)):
        if isinstance(payload, (bytes, bytearray)):
            return payload.decode("utf-8", errors="replace")
        return payload
    if hasattr(payload, "read"):
        data = payload.read()
        if isinstance(data, (bytes, bytearray)):
            return data.decode("utf-8", errors="replace")
        return str(data)
    return str(payload)

def extract_tables_from_showprompt(showprompt_payload: str) -> List[str]:
    """Extract table names from SYSTEM blocks up to the USER block."""
    data = json.loads(showprompt_payload)
    tables: List[str] = []
    for item in data[1:]:  # per requirement: parse from second object onward
        role = str(item.get("role", "")).upper()
        if role == "USER":
            break
        if role != "SYSTEM":
            continue

        for content in item.get("content", []) or []:
            if str(content.get("type", "")).upper() != "TEXT":
                continue
            text = _normalize_json_text(content.get("text", ""))
            match = CREATE_TABLE_PATTERN.search(text)
            if match:
                tables.append(match.group(1))

    deduped = []
    seen = set()
    for table in tables:
        key = table.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(table)
    return deduped


def expected_tables_from_item(item: dict) -> List[str]:
    names = []
    for t in item.get("tables", []) or []:
        name = t.get("name")
        if name:
            names.append(str(name))
    return names


def build_prompt(item: dict) -> str:
    q = (item.get("question") or "").strip()
    ev = (item.get("evidence") or "").strip()
    return f"{q} {ev}".strip()


def evaluate_item(cursor, item: dict, profile_name: str) -> EvalRow:
    row = EvalRow(
        question_id=int(item.get("question_id", -1)),
        db_id=str(item.get("db_id", "")),
        question=str(item.get("question", "")),
        expected_tables=expected_tables_from_item(item),
        discovered_tables=[],
    )

    prompt = build_prompt(item)
    sql = """
        SELECT DBMS_CLOUD_AI.GENERATE(
            prompt       => :prompt,
            profile_name => :profile_name,
            action       => 'showprompt'
        )
        FROM dual
    """

    try:
        cursor.execute(sql, prompt=prompt, profile_name=profile_name)
        payload = cursor.fetchone()[0]
        payload_text = _payload_to_text(payload)
        row.discovered_tables = extract_tables_from_showprompt(payload_text)

        expected_set: Set[str] = set(row.expected_tables)
        discovered_ranked: List[str] = row.discovered_tables

        row.p_at_3, row.r_at_3, row.f1_at_3 = calculate_precision_recall_f1_at_k(expected_set, discovered_ranked, 3)
        row.p_at_5, row.r_at_5, row.f1_at_5 = calculate_precision_recall_f1_at_k(expected_set, discovered_ranked, 5)
        row.p_at_10, row.r_at_10, row.f1_at_10 = calculate_precision_recall_f1_at_k(expected_set, discovered_ranked, 10)
    except Exception as exc:
        row.error = str(exc)

    return row


def averages(rows: Sequence[EvalRow]) -> Tuple[float, float, float, float, float, float, float, float, float]:
    ok = [r for r in rows if not r.error]
    if not ok:
        return (0.0,) * 9
    n = len(ok)
    return (
        sum(r.p_at_3 for r in ok) / n,
        sum(r.r_at_3 for r in ok) / n,
        sum(r.f1_at_3 for r in ok) / n,
        sum(r.p_at_5 for r in ok) / n,
        sum(r.r_at_5 for r in ok) / n,
        sum(r.f1_at_5 for r in ok) / n,
        sum(r.p_at_10 for r in ok) / n,
        sum(r.r_at_10 for r in ok) / n,
        sum(r.f1_at_10 for r in ok) / n,
    )


def write_html(rows: Sequence[EvalRow], output_path: Path, title: str) -> None:
    p3, r3, f3, p5, r5, f5, p10, r10, f10 = averages(rows)
    success = sum(1 for r in rows if not r.error)
    failures = len(rows) - success

    detail_rows = []
    for r in rows:
        detail_rows.append(
            "<tr>"
            f"<td>{r.question_id}</td>"
            f"<td>{html.escape(r.db_id)}</td>"
            f"<td>{html.escape(r.question)}</td>"
            f"<td>{html.escape(', '.join(r.expected_tables))}</td>"
            f"<td>{html.escape(', '.join(r.discovered_tables))}</td>"
            f"<td>{r.p_at_3:.4f}</td><td>{r.r_at_3:.4f}</td><td>{r.f1_at_3:.4f}</td>"
            f"<td>{r.p_at_5:.4f}</td><td>{r.r_at_5:.4f}</td><td>{r.f1_at_5:.4f}</td>"
            f"<td>{r.p_at_10:.4f}</td><td>{r.r_at_10:.4f}</td><td>{r.f1_at_10:.4f}</td>"
            f"<td>{html.escape(r.error)}</td>"
            "</tr>"
        )

    html_doc = f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
<meta charset=\"UTF-8\" />
<title>{html.escape(title)}</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 20px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 12px; }}
th, td {{ border: 1px solid #ddd; padding: 6px; vertical-align: top; }}
th {{ background: #f5f5f5; position: sticky; top: 0; }}
.summary td {{ font-weight: bold; }}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<p>Total: {len(rows)} | Success: {success} | Failures: {failures}</p>
<table class=\"summary\">
<tr><th>Metric</th><th>@3</th><th>@5</th><th>@10</th></tr>
<tr><td>Precision</td><td>{p3:.4f}</td><td>{p5:.4f}</td><td>{p10:.4f}</td></tr>
<tr><td>Recall</td><td>{r3:.4f}</td><td>{r5:.4f}</td><td>{r10:.4f}</td></tr>
<tr><td>F1</td><td>{f3:.4f}</td><td>{f5:.4f}</td><td>{f10:.4f}</td></tr>
</table>

<h2>Per-question details</h2>
<table>
<tr>
<th>question_id</th><th>db_id</th><th>question</th><th>expected_tables</th><th>discovered_tables</th>
<th>P@3</th><th>R@3</th><th>F1@3</th>
<th>P@5</th><th>R@5</th><th>F1@5</th>
<th>P@10</th><th>R@10</th><th>F1@10</th>
<th>error</th>
</tr>
{''.join(detail_rows)}
</table>
</body>
</html>"""

    output_path.write_text(html_doc, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Select AI retrieval over dev_with_metadata.json")
    parser.add_argument("--connection-string", help="Oracle connection string user/password@host:port/service")
    parser.add_argument("--username", help="Oracle username (recommended with --password and --dsn)")
    parser.add_argument("--password", help="Oracle password (recommended with --username and --dsn)")
    parser.add_argument("--dsn", help="Oracle DSN, e.g. host:port/service_name")
    parser.add_argument("--profile-name", default="GPT", help="DBMS_CLOUD_AI profile name (default: GPT)")
    parser.add_argument("--input", default=DEFAULT_INPUT, help=f"Input metadata JSON file (default: {DEFAULT_INPUT})")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Batch size for partial HTML outputs")
    parser.add_argument("--output-dir", default="select_ai_retrieval_eval", help="Output directory for HTML reports")
    parser.add_argument("--test", action="store_true", help="Run pipeline smoke test on a small sample instead of full dataset")
    parser.add_argument("--test-size", type=int, default=DEFAULT_TEST_SIZE, help=f"Number of questions to run in --test mode (default: {DEFAULT_TEST_SIZE})")
    args = parser.parse_args()

    items = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if args.test:
        test_size = max(1, args.test_size)
        items = items[:test_size]
        print(f"Running in test mode with {len(items)} question(s)")
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_rows: List[EvalRow] = []

    if args.username or args.password or args.dsn:
        if not (args.username and args.password and args.dsn):
            parser.error("When using split credentials, provide --username, --password, and --dsn together")

    if args.connection_string:
        conn = oracledb.connect(args.connection_string)
    elif args.username and args.password and args.dsn:
        conn = oracledb.connect(user=args.username, password=args.password, dsn=args.dsn)
    else:
        parser.error("Provide either --connection-string OR --username/--password/--dsn")

    cur = conn.cursor()

    start = time.time()
    total_items = len(items)
    try:
        for idx, item in enumerate(items, start=1):
            row = evaluate_item(cur, item, args.profile_name)
            all_rows.append(row)
            _print_progress(idx, total_items, start)

            if idx % args.batch_size == 0:
                batch_id = idx // args.batch_size
                batch_rows = all_rows[idx - args.batch_size:idx]
                batch_path = out_dir / f"select_ai_retrieval_batch_{batch_id:03d}.html"
                write_html(batch_rows, batch_path, f"Select AI Retrieval Evaluation - Batch {batch_id}")
                print()
                print(f"Wrote {batch_path}")

        if len(all_rows) % args.batch_size:
            batch_id = (len(all_rows) // args.batch_size) + 1
            start_idx = (batch_id - 1) * args.batch_size
            batch_rows = all_rows[start_idx:]
            batch_path = out_dir / f"select_ai_retrieval_batch_{batch_id:03d}.html"
            write_html(batch_rows, batch_path, f"Select AI Retrieval Evaluation - Batch {batch_id}")
            print()
            print(f"Wrote {batch_path}")

        full_title = "Select AI Retrieval Evaluation - Full"
        if args.test:
            full_title = f"Select AI Retrieval Evaluation - Test ({len(all_rows)} questions)"
        full_path = out_dir / "select_ai_retrieval_full.html"
        write_html(all_rows, full_path, full_title)
        print()
        print(f"Wrote {full_path}")
        print(f"Done in {time.time() - start:.2f}s")
    finally:
        cur.close()
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
