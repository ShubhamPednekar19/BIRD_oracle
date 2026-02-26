# Oracle Hybrid Search Evaluation Framework

This framework evaluates Oracle's Hybrid Vector Search capability against the BIRD benchmark dataset. It automates the process of creating database schemas, running discovery queries, and measuring search accuracy.

## Overview

The evaluation pipeline:

1. **Creates Oracle users** for each database schema (user name = folder name)
2. **Executes DDL scripts** to create tables and metadata
3. **Sets up hybrid vector search** using the `developer` package
4. **Runs natural language queries** from `dev_with_metadata.json`
5. **Compares discovered objects** with expected tables/columns
6. **Generates metrics** and exports to CSV or browser dashboard, plus an HTML report file
7. **Cleans up** by dropping users after processing

You can also run in a **single-user mode** where all selected schemas are loaded into one Oracle user and all queries are evaluated in that shared schema.

## Prerequisites

### Python Dependencies

```bash
pip install oracledb
```

Or use the requirements file:

```bash
pip install -r requirements.txt
```

### Oracle Database Requirements

- Oracle Database 23ai (or 21c+ with vector search capability)
- SYSDBA access for user creation/deletion
- ONNX model file (`MiniLM.onnx`) in `ONNX_IMPORT` directory
- `CTX_DDL` package available

### Required Files

| File | Description |
|------|-------------|
| `oracle_ddl/` | Directory containing database DDL folders |
| `dev_with_metadata.json` | BIRD benchmark questions with expected tables/columns |
| `index_creation.sql` | PL/SQL package for hybrid search (to be provided) |

## Usage

### Basic Usage

```bash
python run_hybrid_search_evaluation.py \
  --connection-string "sys/password@localhost:1521/FREEPDB1"
```

### Test Mode (Quick Pipeline Verification)

```bash
python run_hybrid_search_evaluation.py \
  --connection-string "sys/password@localhost:1521/FREEPDB1" \
  --test
```

Test mode automatically:
- Limits to 2 databases
- Limits to 5 questions per database
- Prefixes output files with `test_`

### Single User Mode

Use a shared Oracle user for all selected schemas:

```bash
python run_hybrid_search_evaluation.py \
  --connection-string "sys/password@localhost:1521/FREEPDB1" \
  --single-user-mode
```

Use a custom shared username (password is the same as username):

```bash
python run_hybrid_search_evaluation.py \
  --connection-string "sys/password@localhost:1521/FREEPDB1" \
  --single-user-mode \
  --single-user-name BIRD_ALL
```

### Custom Limits

```bash
python run_hybrid_search_evaluation.py \
  --connection-string "sys/password@localhost:1521/FREEPDB1" \
  --max-databases 3 \
  --max-questions 10
```

### Specific Databases

```bash
python run_hybrid_search_evaluation.py \
  --connection-string "sys/password@localhost:1521/FREEPDB1" \
  --databases california_schools financial
```

### HTML Report Output


### YAML-Driven Experiment Matrix Runner

To run all requested combinations (mode/search-type/scorer/dataset-form) with separate output folders, use:

```bash
python run_experiment_matrix.py --config experiment_matrix.yaml
```

Dry run (print commands only):

```bash
python run_experiment_matrix.py --config experiment_matrix.yaml --dry-run
```

Config tips for beginners:
- `experiment_matrix.yaml` supports **comment-only** lines that start with `#`.
- To run multiple values for a field, put them in a list. Example:
  - `"modes": ["unified", "parallel"]`
  - `"search_types": ["vector", "hybrid"]`
  - `"dataset_forms": ["single-user", "multiple"]`
- To pass extra arguments to every run, use `passthrough_args`, e.g.
  `"passthrough_args": ["--max-questions", "100"]`.
- `scorer_overrides` now supports list values for sweep runs. Example:
  - `"RSF": {"discover_vector_score_weight": [10], "discover_text_score_weight": [2,4,6]}`
  - This creates 3 RSF variants automatically.

Folder layout produced under `results/`:

```text
results/
  unified/
    hybrid/
      rsf/
        set1__discover_vector_score_weight-10__discover_text_score_weight-2/
          multiple/
          single-user/
        set2__discover_vector_score_weight-10__discover_text_score_weight-4/
          ...
      rrf/
        multiple/
        single-user/
    vector/
      multiple/
      single-user/
  parallel/
    ... (same pattern)
```

Each leaf directory contains:
- `results.csv`
- `summary.csv`
- `report.html`


An HTML report is now always generated. By default it is saved as `report.html`:

```bash
python run_hybrid_search_evaluation.py \
  --connection-string "sys/password@localhost:1521/FREEPDB1"
```

Use `--html` to customize the file name/path:

```bash
python run_hybrid_search_evaluation.py \
  --connection-string "sys/password@localhost:1521/FREEPDB1" \
  --html my_custom_report.html
```

Use `--output-source` to choose between CSV output and browser mode:

```bash
python run_hybrid_search_evaluation.py \
  --connection-string "sys/password@localhost:1521/FREEPDB1" \
  --output-source browser
```

### HTML Report with Local Server

Generate the HTML report and immediately start a local HTTP server to view it in a browser:

```bash
python run_hybrid_search_evaluation.py \
  --connection-string "sys/password@localhost:1521/FREEPDB1" \
  --html report.html \
  --serve
```

This will save the HTML file and then start a server at `http://localhost:8000/`. Use `--port` to change the port:

```bash
python run_hybrid_search_evaluation.py \
  --connection-string "sys/password@localhost:1521/FREEPDB1" \
  --html report.html \
  --serve --port 9090
```

Press `Ctrl+C` to stop the server.

### Viewing a Previously Saved HTML Report

If you already have a saved HTML report and want to serve it later without re-running the evaluation, you can start a local server manually:

```bash
python -m http.server 8000
```

Then open `http://localhost:8000/report.html` in your browser.

## Command Line Arguments

| Argument | Short | Default | Description |
|----------|-------|---------|-------------|
| `--connection-string` | `-c` | *required* | Oracle connection string |
| `--ddl-dir` | `-d` | `oracle_ddl` | Directory containing DDL folders |
| `--metadata-file` | `-m` | `dev_with_metadata.json` | Questions metadata file |
| `--index-script` | `-i` | `index_creation.sql` | Hybrid search package script |
| `--output` | `-o` | `hybrid_search_evaluation_results.csv` | Results CSV file |
| `--summary` | `-s` | `hybrid_search_evaluation_summary.csv` | Summary CSV file |
| `--databases` | `-db` | all | Specific databases to process |
| `--test` | `-t` | false | Run in test mode |
| `--max-questions` | `-q` | all | Max questions per database |
| `--max-databases` | `-n` | all | Max databases to process |
| `--output-source` | `-f` | `csv` | Primary output source: `csv` or `browser` |
| `--html` | | `report.html` | Output HTML report file path |
| `--serve` | | false | Start a local HTTP server to view the HTML report |
| `--port` | | 8000 | Port for the local HTTP server |
| `--single-user-mode` | | false | Load all selected schemas into one Oracle user and run all queries there |
| `--single-user-name` | | `BIRD_ALL` | Username for `--single-user-mode` (password is the same as username) |
| `--mode` | sequential\|parallel\|unified | sequential | Select discovery procedure (`discover_objects`, `discover_objects_parallel`, or `discover_objects_unified`) |
| `--search-type` | vector\|hybrid | vector | Request shape sent to package. `vector` keeps legacy args; `hybrid` sends vector+keyword args |

### Discovery Argument Group

You can now provide discovery procedure arguments as a grouped JSON config and/or explicit overrides.

| Argument | Default | Description |
|----------|---------|-------------|
| `--discover-config-json` | none | JSON blob for discovery args. Example: `{"k":10,"k0":50,"n":null,"m":null,"cols_per_obj":5,"alpha":0.65,"parallel_alpha":0.60}` |
| `--discover-k` | 10 | Final top-K objects returned and metric cutoff K |
| `--discover-k0` | 50 | Sequential stage-1 object topN (`p_k0`) |
| `--discover-n` | null | Sequential stage-2 column topN (`p_n`) |
| `--discover-m` | null | Parallel column topN (`p_m`) |
| `--discover-cols-per-obj` | 5 | Max columns attached per object |
| `--discover-alpha` | 0.65 | Sequential rerank blend alpha (`p_alpha`) |
| `--discover-parallel-alpha` | 0.60 | Parallel rerank blend alpha (`p_alpha`) |
| `--discover-score-threshold` | 60.0 | Unified mode score threshold (`[0,100]`) |
| `--discover-search-scorer` | RSF | Hybrid `search_scorer` |
| `--discover-search-fusion` | UNION | Hybrid `search_fusion` |
| `--discover-vector-search-mode` | DOCUMENT | Hybrid `vector.search_mode` |
| `--discover-vector-aggregator` | MAX | Hybrid `vector.aggregator` |
| `--discover-vector-score-weight` | 1 | Hybrid `vector.score_weight` |
| `--discover-vector-rank-penalty` | 5 | Hybrid `vector.rank_penalty` |
| `--discover-text-contains` | auto | Hybrid `text.contains` override |
| `--discover-text-score-weight` | 10 | Hybrid `text.score_weight` |
| `--discover-text-rank-penalty` | 1 | Hybrid `text.rank_penalty` |

`--discover-text-contains` auto behavior: when `--search-type hybrid` is used and this
flag is omitted, the runner generates keywords from the query text in Python. It
uses NLTK (`word_tokenize` + English stopwords filtering + `isalpha` + dedupe, joined
with `OR`) when available, and falls back to built-in regex/stopword filtering when NLTK
resources are unavailable.

Override precedence: explicit CLI flags > `--discover-config-json` > built-in defaults.

## Output Files
### Results CSV (`hybrid_search_evaluation_results.csv`)

Per-query detailed results:

| Column | Description |
|--------|-------------|
| `question_id` | Unique question identifier |
| `db_id` | Database identifier |
| `question` | Natural language query |
| `execution_time_ms` | Query execution time in milliseconds |
| `num_expected_tables` | Number of expected tables |
| `num_expected_columns` | Number of expected columns |
| `expected_tables` | Expected table names (pipe-separated) |
| `expected_columns` | Expected column names (pipe-separated) |
| `discovered_tables` | Discovered table names (pipe-separated) |
| `discovered_columns` | Discovered column names (pipe-separated) |
| **Basic Metrics** | |
| `table_precision` | Precision for table discovery |
| `table_recall` | Recall for table discovery |
| `table_f1` | F1 score for table discovery |
| `column_precision` | Precision for column discovery |
| `column_recall` | Recall for column discovery |
| `column_f1` | F1 score for column discovery |
| **Hit@K (Binary)** | |
| `table_hit_at_1` | True if any expected table in top-1 |
| `table_hit_at_3` | True if any expected table in top-3 |
| `table_hit_at_5` | True if any expected table in top-5 |
| **Recall@K (Fraction)** | Better for multi-table queries |
| `table_recall_at_3` | Fraction of expected tables in top-3 |
| `table_recall_at_5` | Fraction of expected tables in top-5 |
| `table_recall_at_10` | Fraction of expected tables in top-10 |
| **Advanced Metrics** | |
| `table_mrr` | Mean Reciprocal Rank for tables |
| `table_jaccard` | Jaccard similarity for tables |
| `table_exact_match` | True if discovered = expected exactly |
| **Joint Table-Column Metrics** | |
| `joint_column_precision` | Column precision (only if table found) |
| `joint_column_recall` | Column recall (only if table found) |
| `joint_column_f1` | Column F1 (only if table found) |
| `error` | Error message if query failed |

### Summary CSV (`hybrid_search_evaluation_summary.csv`)

Per-database aggregated metrics:

| Column | Description |
|--------|-------------|
| `db_id` | Database identifier |
| `total_questions` | Total questions processed |
| `successful_queries` | Queries that completed successfully |
| `failed_queries` | Queries that failed |
| `avg_execution_time_ms` | Average execution time |
| **Basic Metrics** | |
| `avg_table_precision` | Average table precision |
| `avg_table_recall` | Average table recall |
| `avg_table_f1` | Average table F1 score |
| `avg_column_precision` | Average column precision |
| `avg_column_recall` | Average column recall |
| `avg_column_f1` | Average column F1 score |
| **Hit@K Rates (Binary)** | |
| `table_hit_at_1_rate` | Hit@1 rate for tables |
| `table_hit_at_3_rate` | Hit@3 rate for tables |
| `table_hit_at_5_rate` | Hit@5 rate for tables |
| **Recall@K Averages (Fraction)** | Better for multi-table queries |
| `avg_table_recall_at_3` | Average Recall@3 for tables |
| `avg_table_recall_at_5` | Average Recall@5 for tables |
| `avg_table_recall_at_10` | Average Recall@10 for tables |
| **Advanced Metrics** | |
| `avg_table_mrr` | Average MRR for tables |
| `avg_table_jaccard` | Average Jaccard similarity |
| `table_exact_match_rate` | Rate of exact table matches |
| **Joint Table-Column Metrics** | |
| `avg_joint_column_precision` | Average joint column precision |
| `avg_joint_column_recall` | Average joint column recall |
| `avg_joint_column_f1` | Average joint column F1 |

### HTML Report

A single HTML file is always generated (default: `report.html`) that contains the same styled and interactive dashboard used by browser mode. The file can be opened directly in any browser or served via a local HTTP server using `--serve`. Use `--html <file>` to change the file name/path.

The **Run Parameters** section in the HTML report includes `index_setup_time_ms`, which is the total time spent running index/package setup for the run (in single-user mode this is the one-time shared setup time).

## Evaluation Metrics

### Precision, Recall, F1

- **Precision**: Of the objects discovered, what fraction were expected?
- **Recall**: Of the expected objects, what fraction were discovered?
- **F1 Score**: Harmonic mean of precision and recall

```
Precision = True Positives / (True Positives + False Positives)
Recall = True Positives / (True Positives + False Negatives)
F1 = 2 * (Precision * Recall) / (Precision + Recall)
```

### Hit@K (Binary)

Measures if **at least one** expected table appears in the top-K results:

- **Hit@1**: At least one correct table is the top result
- **Hit@3**: At least one correct table is in top 3 results
- **Hit@5**: At least one correct table is in top 5 results

*Note: Hit@K is binary (0 or 1) and may overestimate performance for multi-table queries.*

### Recall@K (Fraction)

Measures **what fraction** of expected tables appear in the top-K results. Better for multi-table scenarios:

- **Recall@3**: Fraction of expected tables found in top 3
- **Recall@5**: Fraction of expected tables found in top 5
- **Recall@10**: Fraction of expected tables found in top 10

*Example: If 3 tables expected and 2 found in top-5, Recall@5 = 0.67*

### Mean Reciprocal Rank (MRR)

MRR = 1/rank of first correct result. Higher is better.

- If first expected table is at rank 1: MRR = 1.0
- If first expected table is at rank 2: MRR = 0.5
- If first expected table is at rank 5: MRR = 0.2

### Jaccard Similarity

Measures overall set similarity between expected and discovered:

```
Jaccard = |expected ∩ discovered| / |expected ∪ discovered|
```

### Exact Match

True only if discovered tables exactly match expected tables (no extra, no missing).

### Joint Table-Column Metrics

A column is only considered "correct" if its parent table was also discovered. This preserves the table-column relationship:

- **Joint Precision**: Columns found correctly / Total columns discovered (in found tables)
- **Joint Recall**: Columns found correctly / Total columns expected
- **Joint F1**: Harmonic mean of joint precision and recall

*Example: If query expects Table A with columns X, Y and Table B with column Z, but only Table A is discovered with columns X, W:*
- *True Positives: 1 (column X from Table A)*
- *Joint Precision: 1/2 = 0.5 (X is correct, W is not expected)*
- *Joint Recall: 1/3 = 0.33 (only X found out of X, Y, Z)*

## Developer Package Interface

The script expects an `index_creation.sql` file that creates a `developer` package with these procedures:

### `developer.refresh_data`

Populates metadata tables for hybrid search.

```sql
PROCEDURE refresh_data(p_table_name IN VARCHAR2 DEFAULT NULL);
```

### `developer.setup_hybrid_search`

Creates hybrid vector indexes.

```sql
PROCEDURE setup_hybrid_search(
  p_model_dir   IN VARCHAR2 DEFAULT 'ONNX_IMPORT',
  p_model_file  IN VARCHAR2 DEFAULT 'MiniLM.onnx',
  p_model_name  IN VARCHAR2 DEFAULT 'ALL_MINILM_L6',
  p_vectorizer  IN VARCHAR2 DEFAULT 'VEC_MINILM_IVF'
);
```

### `developer.discover_objects`

Executes hybrid search and returns matching objects.

```sql
PROCEDURE discover_objects(
  p_query         IN  CLOB,
  p_k             IN  PLS_INTEGER DEFAULT 10,
  p_k0            IN  PLS_INTEGER DEFAULT 50,
  p_n             IN  PLS_INTEGER DEFAULT NULL,
  p_cols_per_obj  IN  PLS_INTEGER DEFAULT 3,
  p_alpha         IN  NUMBER      DEFAULT 0.65,
  p_result_json   OUT JSON
);
```

**Output JSON format:**

```json
[
  {
    "objectName": "EMPLOYEES",
    "objectType": "TABLE",
    "schema": "HR",
    "score": 0.85,
    "column": [
      {"name": "EMPLOYEE_ID", "datatype": "NUMBER"},
      {"name": "FIRST_NAME", "datatype": "VARCHAR2"},
      {"name": "SALARY", "datatype": "NUMBER"}
    ]
  }
]
```

## User Creation Details

For each database folder, the script creates an Oracle user with:

```sql
-- Create user (name = password = folder name)
CREATE USER california_schools IDENTIFIED BY california_schools;

-- Grant privileges
GRANT CREATE SESSION TO california_schools;
GRANT RESOURCE TO california_schools;
GRANT UNLIMITED TABLESPACE TO california_schools;
GRANT CREATE TRIGGER, CREATE SEQUENCE, CREATE JOB TO california_schools;
GRANT EXECUTE ON CTX_DDL TO california_schools;
GRANT READ, WRITE ON DIRECTORY ONNX_IMPORT TO california_schools;
GRANT CREATE MINING MODEL TO california_schools;
```

After processing, the user is dropped:

```sql
DROP USER california_schools CASCADE;
```

## Directory Structure

```
BIRD_oracle/
├── oracle_ddl/
│   ├── california_schools/
│   │   ├── california_schools_oracle.sql    # Table DDL
│   │   └── california_schools_metadata.sql  # Comments/annotations
│   ├── financial/
│   │   ├── financial_oracle.sql
│   │   └── financial_metadata.sql
│   └── ...
├── dev_with_metadata.json      # Questions with expected tables/columns
├── index_creation.sql          # Developer package (hybrid search)
├── run_hybrid_search_evaluation.py  # Main evaluation script
├── requirements.txt            # Python dependencies
└── HYBRID_SEARCH_EVALUATION.md # This documentation
```

## Example Output

### Console Output

```
============================================================
RUNNING IN TEST MODE
============================================================
  Max databases: 2
  Max questions per db: 5
  Output file: test_hybrid_search_evaluation_results.csv
  Summary file: test_hybrid_search_evaluation_summary.csv
============================================================

Loading metadata from: dev_with_metadata.json
Found questions for 11 databases
Will process 2 databases: california_schools, card_games

============================================================
Processing database: california_schools
============================================================
  Created user: california_schools
  Granted privileges to: california_schools
  Connected as user: california_schools
    Executed DDL: california_schools_oracle.sql
    Executed DDL: california_schools_metadata.sql
    Called developer.refresh_data()
    Called developer.setup_hybrid_search()

  Processing 5 questions...
    Processed 5/5 questions...
  Dropped user: california_schools

  Database california_schools Summary:
    Total questions: 5
    Successful: 5
    Failed: 0
    Avg execution time: 45.32ms
    Avg table F1: 0.7500
    Hit@1: 60.00%

============================================================
OVERALL SUMMARY
============================================================
Total databases: 2
Total questions: 10
Successful queries: 10
Overall avg table F1: 0.7250
Overall Hit@1 rate: 55.00%
```

## Troubleshooting

### Common Issues

1. **Connection failed as SYSDBA**
   - Verify connection string format: `user/password@host:port/service`
   - Ensure user has SYSDBA privileges

2. **CTX_DDL grant failed**
   - Oracle Text must be installed
   - Run as SYS: `GRANT EXECUTE ON CTX_DDL TO PUBLIC;`

3. **ONNX_IMPORT directory not found**
   - Create directory: `CREATE DIRECTORY ONNX_IMPORT AS '/path/to/onnx';`
   - Place `MiniLM.onnx` in the directory

4. **No questions found for database**
   - Verify `db_id` in `dev_with_metadata.json` matches folder names
   - Check folder names are lowercase

## License

Part of the BIRD Oracle benchmark evaluation project.


## Additional @K Metrics (Table + Column)

The evaluator now reports these ranked-cutoff metrics in **results CSV**, **summary CSV**, and the **HTML dashboard**:

- Recall@3, Recall@5, Recall@K
- Precision@1, Precision@3, Precision@5, Precision@K
- F1@1, F1@3, F1@5, F1@K

These are emitted for both table and column signals, and database-level averages are included in summary output.
