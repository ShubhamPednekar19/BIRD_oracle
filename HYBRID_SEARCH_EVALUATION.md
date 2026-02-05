# Oracle Hybrid Search Evaluation Framework

This framework evaluates Oracle's Hybrid Vector Search capability against the BIRD benchmark dataset. It automates the process of creating database schemas, running discovery queries, and measuring search accuracy.

## Overview

The evaluation pipeline:

1. **Creates Oracle users** for each database schema (user name = folder name)
2. **Executes DDL scripts** to create tables and metadata
3. **Sets up hybrid vector search** using the `developer` package
4. **Runs natural language queries** from `dev_with_metadata.json`
5. **Compares discovered objects** with expected tables/columns
6. **Generates metrics** and exports to CSV
7. **Cleans up** by dropping users after processing

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

## Output Files

### Results CSV (`hybrid_search_evaluation_results.csv`)

Per-query detailed results:

| Column | Description |
|--------|-------------|
| `question_id` | Unique question identifier |
| `db_id` | Database identifier |
| `question` | Natural language query |
| `execution_time_ms` | Query execution time in milliseconds |
| `expected_tables` | Expected table names (pipe-separated) |
| `expected_columns` | Expected column names (pipe-separated) |
| `discovered_tables` | Discovered table names (pipe-separated) |
| `discovered_columns` | Discovered column names (pipe-separated) |
| `table_precision` | Precision for table discovery |
| `table_recall` | Recall for table discovery |
| `table_f1` | F1 score for table discovery |
| `column_precision` | Precision for column discovery |
| `column_recall` | Recall for column discovery |
| `column_f1` | F1 score for column discovery |
| `table_hit_at_1` | True if correct table in top-1 |
| `table_hit_at_3` | True if correct table in top-3 |
| `table_hit_at_5` | True if correct table in top-5 |
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
| `avg_table_precision` | Average table precision |
| `avg_table_recall` | Average table recall |
| `avg_table_f1` | Average table F1 score |
| `avg_column_precision` | Average column precision |
| `avg_column_recall` | Average column recall |
| `avg_column_f1` | Average column F1 score |
| `table_hit_at_1_rate` | Hit@1 rate for tables |
| `table_hit_at_3_rate` | Hit@3 rate for tables |
| `table_hit_at_5_rate` | Hit@5 rate for tables |

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

### Hit@K

Measures if at least one expected table appears in the top-K results:

- **Hit@1**: Correct table is the top result
- **Hit@3**: Correct table is in top 3 results
- **Hit@5**: Correct table is in top 5 results

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
