# Select AI Retrieval Evaluation

This folder contains a standalone evaluator for Oracle Select AI retrieval quality using `DBMS_CLOUD_AI.GENERATE(..., action => 'showprompt')`.

## Files

- `run_select_ai_retrieval_evaluation.py`: Runs evaluation over `dev_with_metadata.json`, extracts table names from Select AI showprompt output, computes Precision/Recall/F1 at @3/@5/@10, and writes HTML reports.

## What the script does

For each item in `dev_with_metadata.json`:

1. Builds prompt: `question + " " + evidence`.
2. Calls:
   ```sql
   SELECT DBMS_CLOUD_AI.GENERATE(
       prompt       => :prompt,
       profile_name => :profile_name,
       action       => 'showprompt'
   )
   FROM dual
   ```
3. Parses returned JSON from the second object onward until role `USER`.
4. Extracts table names from `CREATE TABLE "OWNER"."TABLE"` statements in SYSTEM `TEXT` content.
5. Compares extracted tables to expected tables from metadata.
6. Computes Precision/Recall/F1 at @3, @5, and @10.
7. Writes batch HTML files (every 100 questions by default) and a full HTML report.

## Usage

Run from the repository root:

```bash
python selectAI/run_select_ai_retrieval_evaluation.py \
  --connection-string "user/password@host:port/service" \
  --profile-name GPT \
  --batch-size 100 \
  --output-dir select_ai_retrieval_eval
```


### Quick pipeline test mode

To run only a small smoke test (2-3 questions), use `--test` and optionally `--test-size`:

```bash
python selectAI/run_select_ai_retrieval_evaluation.py \
  --connection-string "user/password@host:port/service" \
  --profile-name GPT \
  --test \
  --test-size 3
```

## Output

By default reports are written to `select_ai_retrieval_eval/`:

- `select_ai_retrieval_batch_001.html`, `select_ai_retrieval_batch_002.html`, ...
- `select_ai_retrieval_full.html`
