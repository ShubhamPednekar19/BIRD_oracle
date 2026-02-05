#!/usr/bin/env python3
"""
Oracle Hybrid Search Evaluation Script

This script automates the evaluation of Oracle's hybrid vector search against
the BIRD benchmark dataset. For each database in oracle_ddl:

1. Creates an Oracle user with the database name
2. Executes DDL scripts to create tables
3. Runs the index_creation.sql package for hybrid search setup
4. Executes discovery queries from dev_with_metadata.json
5. Compares discovered objects/columns with expected results
6. Stores metrics in CSV format
7. Cleans up by dropping the user

Usage:
    python run_hybrid_search_evaluation.py --connection-string "user/password@host:port/service"

Requirements:
    - python-oracledb
    - Oracle Database with necessary privileges
    - ONNX model file in ONNX_IMPORT directory
"""

import argparse
import csv
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple
from datetime import datetime

try:
    import oracledb
except ImportError:
    print("Error: python-oracledb is required. Install with: pip install oracledb")
    sys.exit(1)


# ============================================================================
# Configuration
# ============================================================================

ORACLE_DDL_DIR = "oracle_ddl"
DEV_METADATA_FILE = "dev_with_metadata.json"
INDEX_CREATION_SCRIPT = "index_creation.sql"
OUTPUT_CSV = "hybrid_search_evaluation_results.csv"
SUMMARY_CSV = "hybrid_search_evaluation_summary.csv"

# Default privileges for created users
USER_GRANTS = [
    "CREATE SESSION",
    "RESOURCE",
    "UNLIMITED TABLESPACE",
    "CREATE TRIGGER",
    "CREATE SEQUENCE",
    "CREATE JOB",
]

# Additional grants that require specific objects
ADDITIONAL_GRANTS = [
    "EXECUTE ON CTX_DDL",
    "READ, WRITE ON DIRECTORY ONNX_IMPORT",
    "CREATE MINING MODEL",
]


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class DiscoveredObject:
    """Represents an object discovered by hybrid search."""
    object_name: str
    object_type: str
    schema: str
    score: float
    columns: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class ExpectedObject:
    """Represents expected tables/columns from dev_with_metadata.json."""
    table_name: str
    columns: List[str] = field(default_factory=list)


@dataclass
class EvaluationResult:
    """Stores evaluation metrics for a single query."""
    question_id: int
    db_id: str
    question: str
    execution_time_ms: float

    # Expected from dev_with_metadata.json
    expected_tables: List[str] = field(default_factory=list)
    expected_columns: List[str] = field(default_factory=list)

    # Discovered by hybrid search
    discovered_tables: List[str] = field(default_factory=list)
    discovered_columns: List[str] = field(default_factory=list)

    # Metrics
    table_precision: float = 0.0
    table_recall: float = 0.0
    table_f1: float = 0.0
    column_precision: float = 0.0
    column_recall: float = 0.0
    column_f1: float = 0.0

    # Top-k metrics
    table_hit_at_1: bool = False
    table_hit_at_3: bool = False
    table_hit_at_5: bool = False

    error: Optional[str] = None


@dataclass
class DatabaseSummary:
    """Summary metrics for a database."""
    db_id: str
    total_questions: int = 0
    successful_queries: int = 0
    failed_queries: int = 0
    avg_execution_time_ms: float = 0.0

    # Aggregate metrics
    avg_table_precision: float = 0.0
    avg_table_recall: float = 0.0
    avg_table_f1: float = 0.0
    avg_column_precision: float = 0.0
    avg_column_recall: float = 0.0
    avg_column_f1: float = 0.0

    # Hit rates
    table_hit_at_1_rate: float = 0.0
    table_hit_at_3_rate: float = 0.0
    table_hit_at_5_rate: float = 0.0


# ============================================================================
# Oracle Database Operations
# ============================================================================

class OracleManager:
    """Manages Oracle database connections and operations."""

    def __init__(self, connection_string: str):
        """
        Initialize with connection string.

        Args:
            connection_string: Oracle connection string (user/password@host:port/service)
        """
        self.connection_string = connection_string
        self.sys_connection = None
        self.user_connection = None
        self.current_user = None

    def connect_as_sys(self) -> bool:
        """Connect to Oracle as SYSDBA."""
        try:
            # Parse connection string
            # Expected format: user/password@host:port/service
            parts = self.connection_string.split('@')
            if len(parts) != 2:
                print(f"Error: Invalid connection string format")
                return False

            user_pass = parts[0].split('/')
            if len(user_pass) != 2:
                print(f"Error: Invalid user/password format")
                return False

            user, password = user_pass
            dsn = parts[1]

            self.sys_connection = oracledb.connect(
                user=user,
                password=password,
                dsn=dsn,
                mode=oracledb.AUTH_MODE_SYSDBA
            )
            print(f"Connected to Oracle as SYSDBA")
            return True
        except Exception as e:
            print(f"Error connecting as SYSDBA: {e}")
            return False

    def create_user(self, username: str) -> bool:
        """
        Create an Oracle user with required privileges.

        Args:
            username: Name of the user to create (also used as password)
        """
        if not self.sys_connection:
            print("Error: Not connected as SYSDBA")
            return False

        try:
            cursor = self.sys_connection.cursor()

            # Drop user if exists
            try:
                cursor.execute(f"DROP USER {username} CASCADE")
                print(f"  Dropped existing user: {username}")
            except oracledb.DatabaseError:
                pass  # User doesn't exist

            # Create user
            cursor.execute(f"CREATE USER {username} IDENTIFIED BY {username}")
            print(f"  Created user: {username}")

            # Grant basic privileges
            for grant in USER_GRANTS:
                cursor.execute(f"GRANT {grant} TO {username}")

            # Grant additional privileges
            for grant in ADDITIONAL_GRANTS:
                try:
                    cursor.execute(f"GRANT {grant} TO {username}")
                except oracledb.DatabaseError as e:
                    print(f"  Warning: Could not grant {grant}: {e}")

            self.sys_connection.commit()
            print(f"  Granted privileges to: {username}")

            self.current_user = username
            return True

        except Exception as e:
            print(f"Error creating user {username}: {e}")
            return False

    def connect_as_user(self, username: str) -> bool:
        """
        Connect as the specified user.

        Args:
            username: Username to connect as (password is same as username)
        """
        try:
            # Close existing user connection
            if self.user_connection:
                self.user_connection.close()

            # Parse DSN from sys connection string
            dsn = self.connection_string.split('@')[1]

            self.user_connection = oracledb.connect(
                user=username,
                password=username,
                dsn=dsn
            )
            print(f"  Connected as user: {username}")
            return True
        except Exception as e:
            print(f"Error connecting as user {username}: {e}")
            return False

    def execute_ddl_file(self, filepath: str) -> bool:
        """
        Execute a DDL SQL file.

        Args:
            filepath: Path to the SQL file
        """
        if not self.user_connection:
            print("Error: Not connected as user")
            return False

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                sql_content = f.read()

            cursor = self.user_connection.cursor()

            # Split by semicolon and execute each statement
            statements = self._split_sql_statements(sql_content)

            for stmt in statements:
                stmt = stmt.strip()
                if stmt and not stmt.startswith('--'):
                    try:
                        cursor.execute(stmt)
                    except oracledb.DatabaseError as e:
                        # Log but continue - some statements might fail due to dependencies
                        error_msg = str(e)
                        if 'ORA-00955' in error_msg:  # Object already exists
                            pass
                        elif 'ORA-02261' in error_msg:  # Unique constraint exists
                            pass
                        else:
                            print(f"    Warning: {error_msg[:100]}")

            self.user_connection.commit()
            print(f"    Executed DDL: {os.path.basename(filepath)}")
            return True

        except Exception as e:
            print(f"Error executing DDL file {filepath}: {e}")
            return False

    def execute_index_creation(self, script_path: str) -> bool:
        """
        Execute the index creation script (PL/SQL package).

        Args:
            script_path: Path to index_creation.sql
        """
        if not self.user_connection:
            print("Error: Not connected as user")
            return False

        if not os.path.exists(script_path):
            print(f"  Warning: Index creation script not found: {script_path}")
            print(f"  Skipping hybrid search setup - will be added later")
            return True  # Return True to continue processing

        try:
            with open(script_path, 'r', encoding='utf-8') as f:
                sql_content = f.read()

            cursor = self.user_connection.cursor()

            # Execute the entire package creation as one statement
            # PL/SQL packages need to be executed differently
            cursor.execute(sql_content)
            self.user_connection.commit()

            print(f"    Executed index creation script")
            return True

        except Exception as e:
            print(f"Error executing index creation script: {e}")
            return False

    def call_refresh_data(self) -> bool:
        """Call developer.refresh_data() to populate metadata tables."""
        if not self.user_connection:
            return False

        try:
            cursor = self.user_connection.cursor()
            cursor.callproc('developer.refresh_data')
            self.user_connection.commit()
            print(f"    Called developer.refresh_data()")
            return True
        except Exception as e:
            print(f"Error calling refresh_data: {e}")
            return False

    def call_setup_hybrid_search(self) -> bool:
        """Call developer.setup_hybrid_search() to create indexes."""
        if not self.user_connection:
            return False

        try:
            cursor = self.user_connection.cursor()
            cursor.callproc('developer.setup_hybrid_search')
            self.user_connection.commit()
            print(f"    Called developer.setup_hybrid_search()")
            return True
        except Exception as e:
            print(f"Error calling setup_hybrid_search: {e}")
            return False

    def discover_objects(self, query: str, k: int = 10, k0: int = 50,
                         cols_per_obj: int = 3) -> Tuple[Optional[List[DiscoveredObject]], float]:
        """
        Call developer.discover_objects() and return results.

        Args:
            query: Natural language query
            k: Final number of objects to return
            k0: Stage-1 candidate objects
            cols_per_obj: Max columns per object

        Returns:
            Tuple of (list of discovered objects, execution time in ms)
        """
        if not self.user_connection:
            return None, 0.0

        try:
            cursor = self.user_connection.cursor()

            # Create output variable for JSON result
            result_json = cursor.var(oracledb.DB_TYPE_JSON)

            start_time = time.perf_counter()

            # Call the procedure
            cursor.callproc('developer.discover_objects', [
                query,      # p_query
                k,          # p_k
                k0,         # p_k0
                None,       # p_n (default)
                cols_per_obj,  # p_cols_per_obj
                0.65,       # p_alpha (default)
                result_json # p_result_json (OUT)
            ])

            end_time = time.perf_counter()
            execution_time_ms = (end_time - start_time) * 1000

            # Parse the JSON result
            json_result = result_json.getvalue()

            if json_result is None:
                return [], execution_time_ms

            # Convert to Python objects
            discovered = []
            if isinstance(json_result, list):
                for item in json_result:
                    obj = DiscoveredObject(
                        object_name=item.get('objectName', ''),
                        object_type=item.get('objectType', ''),
                        schema=item.get('schema', ''),
                        score=item.get('score', 0.0),
                        columns=[
                            {'name': c.get('name', ''), 'datatype': c.get('datatype', '')}
                            for c in item.get('column', [])
                        ]
                    )
                    discovered.append(obj)

            return discovered, execution_time_ms

        except Exception as e:
            print(f"Error in discover_objects: {e}")
            return None, 0.0

    def drop_user(self, username: str) -> bool:
        """
        Drop the specified user.

        Args:
            username: Name of the user to drop
        """
        if not self.sys_connection:
            return False

        try:
            # Close user connection first
            if self.user_connection:
                self.user_connection.close()
                self.user_connection = None

            cursor = self.sys_connection.cursor()
            cursor.execute(f"DROP USER {username} CASCADE")
            self.sys_connection.commit()
            print(f"  Dropped user: {username}")
            return True
        except Exception as e:
            print(f"Error dropping user {username}: {e}")
            return False

    def close(self):
        """Close all connections."""
        if self.user_connection:
            self.user_connection.close()
        if self.sys_connection:
            self.sys_connection.close()

    def _split_sql_statements(self, sql_content: str) -> List[str]:
        """Split SQL content into individual statements."""
        # Simple split by semicolon, but handle PL/SQL blocks
        statements = []
        current = []
        in_plsql = False

        for line in sql_content.split('\n'):
            stripped = line.strip().upper()

            # Detect PL/SQL block start
            if stripped.startswith('CREATE OR REPLACE') or stripped.startswith('BEGIN') or \
               stripped.startswith('DECLARE'):
                in_plsql = True

            current.append(line)

            # Detect end of statement
            if not in_plsql and line.strip().endswith(';'):
                stmt = '\n'.join(current).strip()
                if stmt.endswith(';'):
                    stmt = stmt[:-1]
                statements.append(stmt)
                current = []
            elif in_plsql and (stripped == 'END;' or stripped.startswith('END ')):
                stmt = '\n'.join(current).strip()
                statements.append(stmt)
                current = []
                in_plsql = False

        # Add any remaining content
        if current:
            stmt = '\n'.join(current).strip()
            if stmt:
                if stmt.endswith(';'):
                    stmt = stmt[:-1]
                statements.append(stmt)

        return statements


# ============================================================================
# Evaluation Metrics
# ============================================================================

def calculate_precision_recall_f1(expected: Set[str], discovered: Set[str]) -> Tuple[float, float, float]:
    """
    Calculate precision, recall, and F1 score.

    Args:
        expected: Set of expected items (case-insensitive comparison)
        discovered: Set of discovered items

    Returns:
        Tuple of (precision, recall, f1)
    """
    # Normalize to lowercase for comparison
    expected_lower = {e.lower() for e in expected}
    discovered_lower = {d.lower() for d in discovered}

    if not discovered_lower:
        return 0.0, 0.0, 0.0

    true_positives = len(expected_lower & discovered_lower)

    precision = true_positives / len(discovered_lower) if discovered_lower else 0.0
    recall = true_positives / len(expected_lower) if expected_lower else 0.0

    if precision + recall > 0:
        f1 = 2 * (precision * recall) / (precision + recall)
    else:
        f1 = 0.0

    return precision, recall, f1


def calculate_hit_at_k(expected: Set[str], discovered: List[str], k: int) -> bool:
    """
    Check if any expected item appears in top-k discovered items.

    Args:
        expected: Set of expected items
        discovered: List of discovered items (in ranked order)
        k: Number of top items to consider

    Returns:
        True if at least one expected item is in top-k
    """
    expected_lower = {e.lower() for e in expected}
    top_k = [d.lower() for d in discovered[:k]]

    return len(expected_lower & set(top_k)) > 0


def evaluate_result(expected_tables: List[ExpectedObject],
                   discovered: List[DiscoveredObject]) -> Dict:
    """
    Evaluate discovered objects against expected.

    Args:
        expected_tables: List of expected table objects
        discovered: List of discovered objects

    Returns:
        Dictionary with evaluation metrics
    """
    # Extract expected table names and columns
    expected_table_names = {t.table_name for t in expected_tables}
    expected_column_names = set()
    for t in expected_tables:
        expected_column_names.update(t.columns)

    # Extract discovered table names and columns
    discovered_table_names = [d.object_name for d in discovered]
    discovered_column_names = set()
    for d in discovered:
        for col in d.columns:
            discovered_column_names.add(col['name'])

    # Calculate metrics
    table_p, table_r, table_f1 = calculate_precision_recall_f1(
        expected_table_names, set(discovered_table_names)
    )

    col_p, col_r, col_f1 = calculate_precision_recall_f1(
        expected_column_names, discovered_column_names
    )

    # Hit@k metrics
    hit_at_1 = calculate_hit_at_k(expected_table_names, discovered_table_names, 1)
    hit_at_3 = calculate_hit_at_k(expected_table_names, discovered_table_names, 3)
    hit_at_5 = calculate_hit_at_k(expected_table_names, discovered_table_names, 5)

    return {
        'table_precision': table_p,
        'table_recall': table_r,
        'table_f1': table_f1,
        'column_precision': col_p,
        'column_recall': col_r,
        'column_f1': col_f1,
        'hit_at_1': hit_at_1,
        'hit_at_3': hit_at_3,
        'hit_at_5': hit_at_5,
        'discovered_tables': discovered_table_names,
        'discovered_columns': list(discovered_column_names),
    }


# ============================================================================
# Data Loading
# ============================================================================

def load_dev_metadata(filepath: str) -> Dict[str, List[Dict]]:
    """
    Load dev_with_metadata.json and group by db_id.

    Args:
        filepath: Path to dev_with_metadata.json

    Returns:
        Dictionary mapping db_id to list of questions
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Group by db_id
    grouped = {}
    for item in data:
        db_id = item.get('db_id', '')
        if db_id not in grouped:
            grouped[db_id] = []
        grouped[db_id].append(item)

    return grouped


def get_expected_objects(question: Dict) -> List[ExpectedObject]:
    """
    Extract expected tables and columns from a question.

    Args:
        question: Question dict from dev_with_metadata.json

    Returns:
        List of ExpectedObject
    """
    expected = []

    tables = question.get('tables', [])
    for table in tables:
        table_name = table.get('name', '')
        columns = [col.get('name', '') for col in table.get('columns', [])]
        expected.append(ExpectedObject(table_name=table_name, columns=columns))

    return expected


# ============================================================================
# CSV Output
# ============================================================================

def write_results_csv(results: List[EvaluationResult], filepath: str):
    """Write evaluation results to CSV."""
    fieldnames = [
        'question_id', 'db_id', 'question', 'execution_time_ms',
        'expected_tables', 'expected_columns',
        'discovered_tables', 'discovered_columns',
        'table_precision', 'table_recall', 'table_f1',
        'column_precision', 'column_recall', 'column_f1',
        'table_hit_at_1', 'table_hit_at_3', 'table_hit_at_5',
        'error'
    ]

    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for result in results:
            row = {
                'question_id': result.question_id,
                'db_id': result.db_id,
                'question': result.question[:200],  # Truncate long questions
                'execution_time_ms': f"{result.execution_time_ms:.2f}",
                'expected_tables': '|'.join(result.expected_tables),
                'expected_columns': '|'.join(result.expected_columns[:10]),  # Limit
                'discovered_tables': '|'.join(result.discovered_tables),
                'discovered_columns': '|'.join(result.discovered_columns[:10]),
                'table_precision': f"{result.table_precision:.4f}",
                'table_recall': f"{result.table_recall:.4f}",
                'table_f1': f"{result.table_f1:.4f}",
                'column_precision': f"{result.column_precision:.4f}",
                'column_recall': f"{result.column_recall:.4f}",
                'column_f1': f"{result.column_f1:.4f}",
                'table_hit_at_1': result.table_hit_at_1,
                'table_hit_at_3': result.table_hit_at_3,
                'table_hit_at_5': result.table_hit_at_5,
                'error': result.error or ''
            }
            writer.writerow(row)

    print(f"Results written to: {filepath}")


def write_summary_csv(summaries: List[DatabaseSummary], filepath: str):
    """Write database summaries to CSV."""
    fieldnames = [
        'db_id', 'total_questions', 'successful_queries', 'failed_queries',
        'avg_execution_time_ms',
        'avg_table_precision', 'avg_table_recall', 'avg_table_f1',
        'avg_column_precision', 'avg_column_recall', 'avg_column_f1',
        'table_hit_at_1_rate', 'table_hit_at_3_rate', 'table_hit_at_5_rate'
    ]

    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for summary in summaries:
            row = {
                'db_id': summary.db_id,
                'total_questions': summary.total_questions,
                'successful_queries': summary.successful_queries,
                'failed_queries': summary.failed_queries,
                'avg_execution_time_ms': f"{summary.avg_execution_time_ms:.2f}",
                'avg_table_precision': f"{summary.avg_table_precision:.4f}",
                'avg_table_recall': f"{summary.avg_table_recall:.4f}",
                'avg_table_f1': f"{summary.avg_table_f1:.4f}",
                'avg_column_precision': f"{summary.avg_column_precision:.4f}",
                'avg_column_recall': f"{summary.avg_column_recall:.4f}",
                'avg_column_f1': f"{summary.avg_column_f1:.4f}",
                'table_hit_at_1_rate': f"{summary.table_hit_at_1_rate:.4f}",
                'table_hit_at_3_rate': f"{summary.table_hit_at_3_rate:.4f}",
                'table_hit_at_5_rate': f"{summary.table_hit_at_5_rate:.4f}",
            }
            writer.writerow(row)

    print(f"Summary written to: {filepath}")


def calculate_summary(db_id: str, results: List[EvaluationResult]) -> DatabaseSummary:
    """Calculate summary metrics for a database."""
    summary = DatabaseSummary(db_id=db_id)
    summary.total_questions = len(results)

    successful = [r for r in results if r.error is None]
    summary.successful_queries = len(successful)
    summary.failed_queries = len(results) - len(successful)

    if successful:
        summary.avg_execution_time_ms = sum(r.execution_time_ms for r in successful) / len(successful)
        summary.avg_table_precision = sum(r.table_precision for r in successful) / len(successful)
        summary.avg_table_recall = sum(r.table_recall for r in successful) / len(successful)
        summary.avg_table_f1 = sum(r.table_f1 for r in successful) / len(successful)
        summary.avg_column_precision = sum(r.column_precision for r in successful) / len(successful)
        summary.avg_column_recall = sum(r.column_recall for r in successful) / len(successful)
        summary.avg_column_f1 = sum(r.column_f1 for r in successful) / len(successful)
        summary.table_hit_at_1_rate = sum(1 for r in successful if r.table_hit_at_1) / len(successful)
        summary.table_hit_at_3_rate = sum(1 for r in successful if r.table_hit_at_3) / len(successful)
        summary.table_hit_at_5_rate = sum(1 for r in successful if r.table_hit_at_5) / len(successful)

    return summary


# ============================================================================
# Main Processing
# ============================================================================

def process_database(oracle_mgr: OracleManager, db_id: str,
                    ddl_folder: str, questions: List[Dict],
                    index_script: str) -> Tuple[List[EvaluationResult], DatabaseSummary]:
    """
    Process a single database: create user, run DDL, evaluate queries.

    Args:
        oracle_mgr: OracleManager instance
        db_id: Database identifier
        ddl_folder: Path to DDL folder
        questions: List of questions for this database
        index_script: Path to index_creation.sql

    Returns:
        Tuple of (list of evaluation results, database summary)
    """
    results = []

    print(f"\n{'='*60}")
    print(f"Processing database: {db_id}")
    print(f"{'='*60}")

    # Step 1: Create user
    if not oracle_mgr.create_user(db_id):
        print(f"  Failed to create user for {db_id}")
        summary = DatabaseSummary(db_id=db_id, total_questions=len(questions),
                                   failed_queries=len(questions))
        return results, summary

    # Step 2: Connect as user
    if not oracle_mgr.connect_as_user(db_id):
        print(f"  Failed to connect as {db_id}")
        oracle_mgr.drop_user(db_id)
        summary = DatabaseSummary(db_id=db_id, total_questions=len(questions),
                                   failed_queries=len(questions))
        return results, summary

    # Step 3: Execute DDL files
    ddl_file = os.path.join(ddl_folder, f"{db_id}_oracle.sql")
    metadata_file = os.path.join(ddl_folder, f"{db_id}_metadata.sql")

    if os.path.exists(ddl_file):
        oracle_mgr.execute_ddl_file(ddl_file)

    if os.path.exists(metadata_file):
        oracle_mgr.execute_ddl_file(metadata_file)

    # Step 4: Execute index creation script
    oracle_mgr.execute_index_creation(index_script)

    # Step 5: Call refresh_data and setup_hybrid_search
    oracle_mgr.call_refresh_data()
    oracle_mgr.call_setup_hybrid_search()

    # Step 6: Process questions
    print(f"\n  Processing {len(questions)} questions...")

    for i, question in enumerate(questions):
        question_id = question.get('question_id', i)
        question_text = question.get('question', '')

        # Get expected objects
        expected_objs = get_expected_objects(question)
        expected_tables = [o.table_name for o in expected_objs]
        expected_columns = []
        for o in expected_objs:
            expected_columns.extend(o.columns)

        # Create result object
        result = EvaluationResult(
            question_id=question_id,
            db_id=db_id,
            question=question_text,
            execution_time_ms=0.0,
            expected_tables=expected_tables,
            expected_columns=expected_columns
        )

        # Call discover_objects
        try:
            discovered, exec_time = oracle_mgr.discover_objects(
                query=question_text,
                k=10,
                k0=50,
                cols_per_obj=5
            )

            result.execution_time_ms = exec_time

            if discovered is not None:
                # Evaluate results
                metrics = evaluate_result(expected_objs, discovered)

                result.discovered_tables = metrics['discovered_tables']
                result.discovered_columns = metrics['discovered_columns']
                result.table_precision = metrics['table_precision']
                result.table_recall = metrics['table_recall']
                result.table_f1 = metrics['table_f1']
                result.column_precision = metrics['column_precision']
                result.column_recall = metrics['column_recall']
                result.column_f1 = metrics['column_f1']
                result.table_hit_at_1 = metrics['hit_at_1']
                result.table_hit_at_3 = metrics['hit_at_3']
                result.table_hit_at_5 = metrics['hit_at_5']
            else:
                result.error = "discover_objects returned None"

        except Exception as e:
            result.error = str(e)

        results.append(result)

        if (i + 1) % 10 == 0:
            print(f"    Processed {i + 1}/{len(questions)} questions...")

    # Step 7: Drop user
    oracle_mgr.drop_user(db_id)

    # Calculate summary
    summary = calculate_summary(db_id, results)

    print(f"\n  Database {db_id} Summary:")
    print(f"    Total questions: {summary.total_questions}")
    print(f"    Successful: {summary.successful_queries}")
    print(f"    Failed: {summary.failed_queries}")
    print(f"    Avg execution time: {summary.avg_execution_time_ms:.2f}ms")
    print(f"    Avg table F1: {summary.avg_table_f1:.4f}")
    print(f"    Hit@1: {summary.table_hit_at_1_rate:.2%}")

    return results, summary


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Evaluate Oracle Hybrid Search against BIRD benchmark'
    )
    parser.add_argument(
        '--connection-string', '-c',
        required=True,
        help='Oracle connection string (user/password@host:port/service)'
    )
    parser.add_argument(
        '--ddl-dir', '-d',
        default=ORACLE_DDL_DIR,
        help=f'Directory containing Oracle DDL folders (default: {ORACLE_DDL_DIR})'
    )
    parser.add_argument(
        '--metadata-file', '-m',
        default=DEV_METADATA_FILE,
        help=f'Path to dev_with_metadata.json (default: {DEV_METADATA_FILE})'
    )
    parser.add_argument(
        '--index-script', '-i',
        default=INDEX_CREATION_SCRIPT,
        help=f'Path to index_creation.sql (default: {INDEX_CREATION_SCRIPT})'
    )
    parser.add_argument(
        '--output', '-o',
        default=OUTPUT_CSV,
        help=f'Output CSV file (default: {OUTPUT_CSV})'
    )
    parser.add_argument(
        '--summary', '-s',
        default=SUMMARY_CSV,
        help=f'Summary CSV file (default: {SUMMARY_CSV})'
    )
    parser.add_argument(
        '--databases', '-db',
        nargs='*',
        help='Specific databases to process (default: all)'
    )

    args = parser.parse_args()

    # Validate paths
    if not os.path.isdir(args.ddl_dir):
        print(f"Error: DDL directory not found: {args.ddl_dir}")
        return 1

    if not os.path.isfile(args.metadata_file):
        print(f"Error: Metadata file not found: {args.metadata_file}")
        return 1

    # Load metadata
    print(f"Loading metadata from: {args.metadata_file}")
    questions_by_db = load_dev_metadata(args.metadata_file)
    print(f"Found questions for {len(questions_by_db)} databases")

    # Get list of databases to process
    ddl_folders = [d for d in os.listdir(args.ddl_dir)
                   if os.path.isdir(os.path.join(args.ddl_dir, d))]

    if args.databases:
        ddl_folders = [d for d in ddl_folders if d in args.databases]

    print(f"Will process {len(ddl_folders)} databases: {', '.join(ddl_folders)}")

    # Initialize Oracle manager
    oracle_mgr = OracleManager(args.connection_string)

    if not oracle_mgr.connect_as_sys():
        print("Failed to connect to Oracle as SYSDBA")
        return 1

    try:
        all_results = []
        all_summaries = []

        for db_id in sorted(ddl_folders):
            ddl_folder = os.path.join(args.ddl_dir, db_id)
            questions = questions_by_db.get(db_id, [])

            if not questions:
                print(f"\nSkipping {db_id}: No questions found")
                continue

            results, summary = process_database(
                oracle_mgr, db_id, ddl_folder, questions, args.index_script
            )

            all_results.extend(results)
            all_summaries.append(summary)

        # Write results
        if all_results:
            write_results_csv(all_results, args.output)

        if all_summaries:
            write_summary_csv(all_summaries, args.summary)

            # Print overall summary
            print(f"\n{'='*60}")
            print("OVERALL SUMMARY")
            print(f"{'='*60}")

            total_questions = sum(s.total_questions for s in all_summaries)
            total_successful = sum(s.successful_queries for s in all_summaries)

            if total_successful > 0:
                avg_f1 = sum(s.avg_table_f1 * s.successful_queries for s in all_summaries) / total_successful
                avg_hit1 = sum(s.table_hit_at_1_rate * s.successful_queries for s in all_summaries) / total_successful

                print(f"Total databases: {len(all_summaries)}")
                print(f"Total questions: {total_questions}")
                print(f"Successful queries: {total_successful}")
                print(f"Overall avg table F1: {avg_f1:.4f}")
                print(f"Overall Hit@1 rate: {avg_hit1:.2%}")

    finally:
        oracle_mgr.close()

    return 0


if __name__ == '__main__':
    sys.exit(main())
