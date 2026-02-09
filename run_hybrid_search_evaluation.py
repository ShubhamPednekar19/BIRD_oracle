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
import html
import json
import os
import re
import signal
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from http.server import HTTPServer, SimpleHTTPRequestHandler
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
    num_expected_tables: int = 0
    num_expected_columns: int = 0

    # Discovered by hybrid search
    discovered_tables: List[str] = field(default_factory=list)
    discovered_columns: List[str] = field(default_factory=list)

    # Basic Metrics (Precision, Recall, F1)
    table_precision: float = 0.0
    table_recall: float = 0.0
    table_f1: float = 0.0
    column_precision: float = 0.0
    column_recall: float = 0.0
    column_f1: float = 0.0

    # Top-k metrics (binary: any expected in top-k?)
    table_hit_at_1: bool = False
    table_hit_at_3: bool = False
    table_hit_at_5: bool = False

    # Advanced Metrics for multi-table scenarios
    table_recall_at_3: float = 0.0   # Fraction of expected tables in top-3
    table_recall_at_5: float = 0.0   # Fraction of expected tables in top-5
    table_recall_at_10: float = 0.0  # Fraction of expected tables in top-10
    table_mrr: float = 0.0           # Mean Reciprocal Rank
    table_exact_match: bool = False  # All expected tables found (no more, no less)
    table_jaccard: float = 0.0       # Jaccard similarity

    # Table-Column Joint Metrics (column correct only if table also found)
    joint_column_precision: float = 0.0
    joint_column_recall: float = 0.0
    joint_column_f1: float = 0.0

    # Top-N Accuracy (positional: check top-N slots where N = num expected)
    topn_table_accuracy: float = 0.0
    topn_column_accuracy: float = 0.0

    # Structured JSON for detailed inspection
    expected_json: str = ""
    discovered_json: str = ""

    error: Optional[str] = None


@dataclass
class DatabaseSummary:
    """Summary metrics for a database."""
    db_id: str
    total_questions: int = 0
    successful_queries: int = 0
    failed_queries: int = 0
    avg_execution_time_ms: float = 0.0

    # Basic aggregate metrics
    avg_table_precision: float = 0.0
    avg_table_recall: float = 0.0
    avg_table_f1: float = 0.0
    avg_column_precision: float = 0.0
    avg_column_recall: float = 0.0
    avg_column_f1: float = 0.0

    # Advanced aggregate metrics
    avg_table_recall_at_3: float = 0.0
    avg_table_recall_at_5: float = 0.0
    avg_table_recall_at_10: float = 0.0
    avg_table_mrr: float = 0.0
    table_exact_match_rate: float = 0.0
    avg_table_jaccard: float = 0.0

    # Joint metrics
    avg_joint_column_precision: float = 0.0
    avg_joint_column_recall: float = 0.0
    avg_joint_column_f1: float = 0.0

    # Top-N Accuracy
    avg_topn_table_accuracy: float = 0.0
    avg_topn_column_accuracy: float = 0.0

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
        self.pdb_name = None  # Will be set after parsing connection string

    def _parse_pdb_service(self, dsn: str) -> Optional[str]:
        """
        Extract PDB/service name from DSN.

        Args:
            dsn: DSN string like 'host:port/service' or 'host:port/service_name'

        Returns:
            PDB/service name or None if not found
        """
        # DSN format: host:port/service or just service_name
        if '/' in dsn:
            # Format: host:port/service
            service = dsn.split('/')[-1]
            # Remove any connection parameters after the service name
            if '?' in service:
                service = service.split('?')[0]
            return service.upper()
        return None

    def _switch_to_pdb(self) -> bool:
        """
        Switch the SYSDBA session to the PDB specified in the connection string.

        In Oracle CDB architecture, SYSDBA connections go to the root container
        by default. Users created there won't be accessible from PDB connections.
        This method switches the session to the correct PDB.

        Returns:
            True if successfully switched (or already in PDB), False on error
        """
        if not self.sys_connection or not self.pdb_name:
            return True  # Nothing to switch

        try:
            cursor = self.sys_connection.cursor()

            # Check current container
            cursor.execute("SELECT SYS_CONTEXT('USERENV', 'CON_NAME') FROM DUAL")
            current_container = cursor.fetchone()[0]

            if current_container.upper() == self.pdb_name.upper():
                print(f"  Already in PDB: {self.pdb_name}")
                return True

            # Check if we're in CDB$ROOT and need to switch
            if current_container.upper() == 'CDB$ROOT':
                # Try to switch to the PDB
                try:
                    cursor.execute(f"ALTER SESSION SET CONTAINER = {self.pdb_name}")
                    print(f"  Switched to PDB: {self.pdb_name}")
                    return True
                except oracledb.DatabaseError as e:
                    # PDB might not exist or name might be wrong
                    # Try without the switch - maybe it's a non-CDB database
                    error_str = str(e)
                    if 'ORA-65011' in error_str or 'ORA-01109' in error_str:
                        print(f"  Warning: Could not switch to PDB {self.pdb_name}: {e}")
                        print(f"  Continuing in current container: {current_container}")
                        return True
                    raise
            else:
                # Already in a PDB (not CDB$ROOT)
                print(f"  Connected to container: {current_container}")
                return True

        except oracledb.DatabaseError as e:
            # If we get an error checking container, it might be a non-CDB database
            error_str = str(e)
            if 'ORA-02003' in error_str:  # Container not found - might be non-CDB
                print(f"  Running in non-CDB mode")
                return True
            print(f"Error switching to PDB: {e}")
            return False

    def connect_as_sys(self) -> bool:
        """Connect to Oracle as SYSDBA."""
        try:
            # Parse connection string
            user = 'sys'
            password = 'knl_test7'
            dsn = self.connection_string

            # Extract PDB name from DSN for later use
            self.pdb_name = self._parse_pdb_service(dsn)

            self.sys_connection = oracledb.connect(
                user=user,
                password=password,
                dsn=dsn,
                mode=oracledb.AUTH_MODE_SYSDBA
            )
            print(f"Connected to Oracle as SYSDBA")

            # Switch to PDB if we're in a CDB environment
            if not self._switch_to_pdb():
                print("Warning: Could not switch to PDB, user creation may fail")

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
                    error_str = str(e)
                    if 'ONNX_IMPORT' in grant and 'ORA-22930' in error_str:
                        print(f"  Warning: ONNX_IMPORT directory does not exist in this PDB")
                        print(f"  To create it, run as SYSDBA in your PDB:")
                        print(f"    CREATE OR REPLACE DIRECTORY ONNX_IMPORT AS '/path/to/onnx/models';")
                        print(f"    GRANT READ, WRITE ON DIRECTORY ONNX_IMPORT TO {username};")
                    else:
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
            dsn = self.connection_string

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
        Execute a SQL/DDL file sequentially using split_oracle_script().
        - Supports SQL statements terminated by ';'
        - Supports PL/SQL / CREATE OR REPLACE terminated by '/' on its own line
        - Runs in order; commits at end
        """
        if not self.user_connection:
            print("Error: Not connected as user")
            return False

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                sql_content = f.read()

            statements = self.split_oracle_script(sql_content)
            print(f"Split SQL file into {len(statements)} statements")

            filename = os.path.basename(filepath)

            with self.user_connection.cursor() as cursor:
                for i, stmt in enumerate(statements, start=1):
                    stmt = self._strip_leading_comments(stmt)
                    stmt = stmt.strip()
                    if not stmt:
                        continue

                    # Skip pure comment "statements"
                    if stmt.startswith("--"):
                        continue

                    try:
                        cursor.execute(stmt)
                    except oracledb.DatabaseError as e:
                        # Give a helpful error pointing to the statement number
                        preview = stmt[:800].replace("\n", "\\n")
                        print(f"Error executing {filename} at statement #{i}: {e}")
                        print(f"Statement preview: {preview}")
                        # rollback to keep session clean (optional but recommended)
                        self.user_connection.rollback()
                        return False

            self.user_connection.commit()
            print(f"Executed DDL: {filename} ({len([s for s in statements if s.strip()])} statements)")
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

            # Check if this is a placeholder file
            if 'placeholder' in sql_content.lower() and 'CREATE OR REPLACE PACKAGE' not in sql_content.upper():
                print(f"  Warning: {script_path} appears to be a placeholder file")
                print(f"  Please replace with actual developer package implementation")
                print(f"  Skipping package creation...")
                return False

            cursor = self.user_connection.cursor()

            # Strip SQL*Plus-specific commands (not valid via oracledb)
            sql_content = re.sub(r'(?m)^\s*SET\s+SERVEROUTPUT\s+.*$', '', sql_content)
            sql_content = re.sub(r'(?m)^\s*WHENEVER\s+SQLERROR\s+.*$', '', sql_content)
            sql_content = re.sub(r'(?m)^\s*SHOW\s+ERRORS\s*$', '', sql_content)

            # Split PL/SQL content by '/' delimiter (standard for PL/SQL scripts)
            # Each block (package spec, package body) is typically separated by '/'
            blocks = sql_content.split('\n/\n')

            plsql_keywords = ['CREATE OR REPLACE PACKAGE',
                              'CREATE OR REPLACE PACKAGE BODY',
                              'CREATE OR REPLACE PROCEDURE',
                              'CREATE OR REPLACE FUNCTION',
                              'BEGIN', 'DECLARE']

            for block in blocks:
                block = block.strip()
                if not block or block.startswith('--'):
                    continue

                upper_block = block.upper()

                # Check if it's a PL/SQL block or regular SQL
                if any(kw in upper_block for kw in plsql_keywords):
                    # Find where the PL/SQL part starts (there may be
                    # standalone DDL like CREATE TABLE before it)
                    plsql_start = len(block)
                    for kw in plsql_keywords:
                        idx = upper_block.find(kw)
                        if idx != -1 and idx < plsql_start:
                            plsql_start = idx

                    # Execute any DDL statements that precede the PL/SQL block
                    pre_plsql = block[:plsql_start].strip()
                    if pre_plsql:
                        for stmt in pre_plsql.split(';'):
                            stmt = stmt.strip()
                            # Remove comments to check if there's actual SQL
                            cleaned = re.sub(r'/\*.*?\*/', '', stmt, flags=re.DOTALL)
                            cleaned = re.sub(r'--.*$', '', cleaned, flags=re.MULTILINE).strip()
                            if cleaned:
                                try:
                                    cursor.execute(stmt)
                                except oracledb.DatabaseError as e:
                                    print(f"    Warning: DDL statement failed: {e}")

                    # Execute the PL/SQL block itself
                    plsql_part = block[plsql_start:].strip()
                    if plsql_part:
                        cursor.execute(plsql_part)

                elif upper_block.lstrip().startswith('SELECT'):
                    # Skip standalone SELECT statements (likely placeholders)
                    continue
                else:
                    # Try to execute as regular SQL (strip trailing ; for DDL)
                    try:
                        sql = block.rstrip().rstrip(';').rstrip()
                        if sql:
                            cursor.execute(sql)
                    except oracledb.DatabaseError:
                        pass  # Ignore errors for non-essential statements

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
        except oracledb.DatabaseError as e:
            error_str = str(e)
            if 'PLS-00201' in error_str:
                # Package not installed - this is expected if index_creation.sql is placeholder
                return False
            else:
                print(f"    Warning: refresh_data failed: {error_str[:80]}")
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
        except oracledb.DatabaseError as e:
            error_str = str(e)
            if 'PLS-00201' in error_str:
                # Package not installed - this is expected if index_creation.sql is placeholder
                return False
            else:
                print(f"    Warning: setup_hybrid_search failed: {error_str[:80]}")
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

    def _strip_leading_comments(self, stmt: str) -> str:
        s = stmt.lstrip()

        while True:
            # strip leading -- comment lines
            s2 = re.sub(r'(?m)\A(?:\s*--[^\n]*\n)+', '', s)
            # strip leading /* ... */ block comment(s)
            s2 = re.sub(r'(?s)\A\s*/\*.*?\*/\s*', '', s2)

            if s2 == s:
                break
            s = s2

        return s.strip()

    def split_oracle_script(self, sql: str) -> List[str]:
        statements: List[str] = []
        buf: List[str] = []
        in_plsql = False

        def flush():
            nonlocal buf
            text = "\n".join(buf).strip()
            buf = []
            if text:
                # remove trailing semicolon for plain SQL
                if not in_plsql and text.endswith(";"):
                    text = text[:-1].rstrip()
                statements.append(text)

        for raw_line in sql.splitlines():
            line = raw_line.rstrip("\n")
            stripped = line.strip()
            upper = stripped.upper()

            # Start of a PL/SQL or DDL unit that usually needs "/" terminator
            if upper.startswith("CREATE OR REPLACE") or upper == "BEGIN" or upper.startswith("DECLARE"):
                in_plsql = True

            # SQL*Plus terminator for PL/SQL / CREATE OR REPLACE blocks
            if in_plsql and stripped == "/":
                flush()
                in_plsql = False
                continue

            buf.append(line)

            # End of a normal SQL statement
            if (not in_plsql) and stripped.endswith(";"):
                flush()

        # remainder
        if buf:
            # treat remainder as a statement too
            in_plsql = False
            flush()

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


def calculate_recall_at_k(expected: Set[str], discovered: List[str], k: int) -> float:
    """
    Calculate what fraction of expected items appear in top-k discovered items.

    This is more informative than Hit@K for multi-table scenarios.
    E.g., if 3 tables expected and 2 found in top-5, recall@5 = 0.67

    Args:
        expected: Set of expected items
        discovered: List of discovered items (in ranked order)
        k: Number of top items to consider

    Returns:
        Fraction of expected items found in top-k (0.0 to 1.0)
    """
    if not expected:
        return 1.0  # No expected items means perfect recall

    expected_lower = {e.lower() for e in expected}
    top_k_lower = {d.lower() for d in discovered[:k]}

    found = len(expected_lower & top_k_lower)
    return found / len(expected_lower)


def calculate_mrr(expected: Set[str], discovered: List[str]) -> float:
    """
    Calculate Mean Reciprocal Rank.

    MRR = 1/rank of first correct result. Higher is better.
    If query needs tables A, B, C and we return [X, A, Y, B, C],
    MRR = 1/2 = 0.5 (A is at rank 2)

    Args:
        expected: Set of expected items
        discovered: List of discovered items (in ranked order)

    Returns:
        Reciprocal rank (0.0 if no match found)
    """
    expected_lower = {e.lower() for e in expected}

    for rank, item in enumerate(discovered, start=1):
        if item.lower() in expected_lower:
            return 1.0 / rank

    return 0.0


def calculate_jaccard(expected: Set[str], discovered: Set[str]) -> float:
    """
    Calculate Jaccard similarity between expected and discovered sets.

    Jaccard = |intersection| / |union|
    Good for measuring overall set similarity.

    Args:
        expected: Set of expected items
        discovered: Set of discovered items

    Returns:
        Jaccard similarity (0.0 to 1.0)
    """
    expected_lower = {e.lower() for e in expected}
    discovered_lower = {d.lower() for d in discovered}

    intersection = len(expected_lower & discovered_lower)
    union = len(expected_lower | discovered_lower)

    if union == 0:
        return 1.0  # Both empty = perfect match

    return intersection / union


def calculate_exact_match(expected: Set[str], discovered: Set[str]) -> bool:
    """
    Check if discovered set exactly matches expected set.

    Args:
        expected: Set of expected items
        discovered: Set of discovered items

    Returns:
        True if sets are identical (case-insensitive)
    """
    expected_lower = {e.lower() for e in expected}
    discovered_lower = {d.lower() for d in discovered}

    return expected_lower == discovered_lower


def calculate_joint_column_metrics(
    expected_tables: List['ExpectedObject'],
    discovered: List['DiscoveredObject']
) -> Tuple[float, float, float]:
    """
    Calculate column metrics where a column is only "correct" if its
    parent table was also discovered.

    This preserves the table-column relationship and gives more meaningful
    metrics for multi-table queries.

    Args:
        expected_tables: List of expected table objects with columns
        discovered: List of discovered objects with columns

    Returns:
        Tuple of (precision, recall, f1) for joint table-column matching
    """
    # Build a map of discovered table -> columns (lowercase)
    discovered_table_cols = {}
    for d in discovered:
        table_lower = d.object_name.lower()
        cols_lower = {col['name'].lower() for col in d.columns}
        discovered_table_cols[table_lower] = cols_lower

    # Count true positives: columns where both table and column match
    true_positives = 0
    total_expected = 0
    total_discovered = 0

    for exp_table in expected_tables:
        table_lower = exp_table.table_name.lower()
        exp_cols_lower = {c.lower() for c in exp_table.columns}
        total_expected += len(exp_cols_lower)

        if table_lower in discovered_table_cols:
            disc_cols = discovered_table_cols[table_lower]
            true_positives += len(exp_cols_lower & disc_cols)

    # Total discovered columns (only from tables that were expected)
    for exp_table in expected_tables:
        table_lower = exp_table.table_name.lower()
        if table_lower in discovered_table_cols:
            total_discovered += len(discovered_table_cols[table_lower])

    # Calculate metrics
    precision = true_positives / total_discovered if total_discovered > 0 else 0.0
    recall = true_positives / total_expected if total_expected > 0 else 0.0

    if precision + recall > 0:
        f1 = 2 * (precision * recall) / (precision + recall)
    else:
        f1 = 0.0

    return precision, recall, f1


def calculate_topn_accuracy(
    expected_tables: List['ExpectedObject'],
    discovered: List['DiscoveredObject']
) -> Tuple[float, float]:
    """
    Top-N Accuracy: check only the top-N discovered slots where N equals
    the number of expected items, giving a positional accuracy measure.

    Table accuracy:
        N = number of expected tables.
        Look at the first N discovered tables.
        accuracy = |expected ∩ top-N discovered| / N

    Column accuracy (per matched table):
        For each discovered table that matches an expected table,
        M = number of expected columns for that table.
        Look at the first M discovered columns for that table.
        accuracy = |expected_cols ∩ top-M discovered_cols| / M
        Final score is the average across all expected tables that were
        discovered (0 contribution for tables not discovered).

    Returns:
        Tuple of (table_accuracy, column_accuracy)
    """
    # --- Table accuracy ---
    n = len(expected_tables)
    if n == 0:
        return 0.0, 0.0

    expected_table_names = {t.table_name.lower() for t in expected_tables}
    top_n_discovered = [d.object_name.lower() for d in discovered[:n]]
    table_hits = len(expected_table_names & set(top_n_discovered))
    table_accuracy = table_hits / n

    # --- Column accuracy (per expected table) ---
    # Build map: discovered table (lower) -> ordered list of column names
    discovered_table_cols = {}
    for d in discovered:
        discovered_table_cols[d.object_name.lower()] = [
            col['name'].lower() for col in d.columns
        ]

    col_scores = []
    for exp_table in expected_tables:
        t_lower = exp_table.table_name.lower()
        exp_cols = {c.lower() for c in exp_table.columns}
        m = len(exp_cols)
        if m == 0:
            continue
        if t_lower in discovered_table_cols:
            top_m_cols = set(discovered_table_cols[t_lower][:m])
            col_scores.append(len(exp_cols & top_m_cols) / m)
        else:
            col_scores.append(0.0)

    column_accuracy = sum(col_scores) / len(col_scores) if col_scores else 0.0

    return table_accuracy, column_accuracy


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

    # Basic metrics (Precision, Recall, F1)
    table_p, table_r, table_f1 = calculate_precision_recall_f1(
        expected_table_names, set(discovered_table_names)
    )

    col_p, col_r, col_f1 = calculate_precision_recall_f1(
        expected_column_names, discovered_column_names
    )

    # Hit@k metrics (binary: any expected in top-k?)
    hit_at_1 = calculate_hit_at_k(expected_table_names, discovered_table_names, 1)
    hit_at_3 = calculate_hit_at_k(expected_table_names, discovered_table_names, 3)
    hit_at_5 = calculate_hit_at_k(expected_table_names, discovered_table_names, 5)

    # Recall@k metrics (fraction of expected in top-k - better for multi-table)
    recall_at_3 = calculate_recall_at_k(expected_table_names, discovered_table_names, 3)
    recall_at_5 = calculate_recall_at_k(expected_table_names, discovered_table_names, 5)
    recall_at_10 = calculate_recall_at_k(expected_table_names, discovered_table_names, 10)

    # MRR (ranking quality)
    mrr = calculate_mrr(expected_table_names, discovered_table_names)

    # Jaccard similarity
    jaccard = calculate_jaccard(expected_table_names, set(discovered_table_names))

    # Exact match (strict evaluation)
    exact_match = calculate_exact_match(expected_table_names, set(discovered_table_names))

    # Joint table-column metrics (column correct only if table also found)
    joint_col_p, joint_col_r, joint_col_f1 = calculate_joint_column_metrics(
        expected_tables, discovered
    )

    # Top-N Accuracy (positional)
    topn_table_acc, topn_col_acc = calculate_topn_accuracy(
        expected_tables, discovered
    )

    # Build structured JSON for expected and discovered
    expected_json_data = []
    for t in expected_tables:
        expected_json_data.append({
            'table': t.table_name,
            'columns': t.columns
        })

    discovered_json_data = []
    for d in discovered:
        discovered_json_data.append({
            'table': d.object_name,
            'score': round(float(d.score), 4),
            'columns': [col['name'] for col in d.columns]
        })

    return {
        # Basic metrics
        'table_precision': table_p,
        'table_recall': table_r,
        'table_f1': table_f1,
        'column_precision': col_p,
        'column_recall': col_r,
        'column_f1': col_f1,

        # Hit@k (binary)
        'hit_at_1': hit_at_1,
        'hit_at_3': hit_at_3,
        'hit_at_5': hit_at_5,

        # Recall@k (fraction - better for multi-table)
        'recall_at_3': recall_at_3,
        'recall_at_5': recall_at_5,
        'recall_at_10': recall_at_10,

        # Advanced metrics
        'mrr': mrr,
        'jaccard': jaccard,
        'exact_match': exact_match,

        # Joint table-column metrics
        'joint_column_precision': joint_col_p,
        'joint_column_recall': joint_col_r,
        'joint_column_f1': joint_col_f1,

        # Top-N Accuracy
        'topn_table_accuracy': topn_table_acc,
        'topn_column_accuracy': topn_col_acc,

        # Structured JSON
        'expected_json': json.dumps(expected_json_data),
        'discovered_json': json.dumps(discovered_json_data),

        # Raw data
        'discovered_tables': discovered_table_names,
        'discovered_columns': list(discovered_column_names),
        'num_expected_tables': len(expected_table_names),
        'num_expected_columns': len(expected_column_names),
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
        'num_expected_tables', 'num_expected_columns',
        'expected_tables', 'expected_columns',
        'discovered_tables', 'discovered_columns',
        # Basic metrics
        'table_precision', 'table_recall', 'table_f1',
        'column_precision', 'column_recall', 'column_f1',
        # Hit@k (binary)
        'table_hit_at_1', 'table_hit_at_3', 'table_hit_at_5',
        # Recall@k (fraction - better for multi-table)
        'table_recall_at_3', 'table_recall_at_5', 'table_recall_at_10',
        # Advanced metrics
        'table_mrr', 'table_jaccard', 'table_exact_match',
        # Joint table-column metrics
        'joint_column_precision', 'joint_column_recall', 'joint_column_f1',
        # Top-N Accuracy
        'topn_table_accuracy', 'topn_column_accuracy',
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
                'num_expected_tables': result.num_expected_tables,
                'num_expected_columns': result.num_expected_columns,
                'expected_tables': '|'.join(result.expected_tables),
                'expected_columns': '|'.join(result.expected_columns[:10]),  # Limit
                'discovered_tables': '|'.join(result.discovered_tables),
                'discovered_columns': '|'.join(result.discovered_columns[:10]),
                # Basic metrics
                'table_precision': f"{result.table_precision:.4f}",
                'table_recall': f"{result.table_recall:.4f}",
                'table_f1': f"{result.table_f1:.4f}",
                'column_precision': f"{result.column_precision:.4f}",
                'column_recall': f"{result.column_recall:.4f}",
                'column_f1': f"{result.column_f1:.4f}",
                # Hit@k (binary)
                'table_hit_at_1': result.table_hit_at_1,
                'table_hit_at_3': result.table_hit_at_3,
                'table_hit_at_5': result.table_hit_at_5,
                # Recall@k (fraction)
                'table_recall_at_3': f"{result.table_recall_at_3:.4f}",
                'table_recall_at_5': f"{result.table_recall_at_5:.4f}",
                'table_recall_at_10': f"{result.table_recall_at_10:.4f}",
                # Advanced metrics
                'table_mrr': f"{result.table_mrr:.4f}",
                'table_jaccard': f"{result.table_jaccard:.4f}",
                'table_exact_match': result.table_exact_match,
                # Joint table-column metrics
                'joint_column_precision': f"{result.joint_column_precision:.4f}",
                'joint_column_recall': f"{result.joint_column_recall:.4f}",
                'joint_column_f1': f"{result.joint_column_f1:.4f}",
                # Top-N Accuracy
                'topn_table_accuracy': f"{result.topn_table_accuracy:.4f}",
                'topn_column_accuracy': f"{result.topn_column_accuracy:.4f}",
                'error': result.error or ''
            }
            writer.writerow(row)

    print(f"Results written to: {filepath}")


def write_summary_csv(summaries: List[DatabaseSummary], filepath: str):
    """Write database summaries to CSV."""
    fieldnames = [
        'db_id', 'total_questions', 'successful_queries', 'failed_queries',
        'avg_execution_time_ms',
        # Basic metrics
        'avg_table_precision', 'avg_table_recall', 'avg_table_f1',
        'avg_column_precision', 'avg_column_recall', 'avg_column_f1',
        # Hit@k rates (binary)
        'table_hit_at_1_rate', 'table_hit_at_3_rate', 'table_hit_at_5_rate',
        # Recall@k averages (fraction - better for multi-table)
        'avg_table_recall_at_3', 'avg_table_recall_at_5', 'avg_table_recall_at_10',
        # Advanced metrics
        'avg_table_mrr', 'avg_table_jaccard', 'table_exact_match_rate',
        # Joint table-column metrics
        'avg_joint_column_precision', 'avg_joint_column_recall', 'avg_joint_column_f1',
        # Top-N Accuracy
        'avg_topn_table_accuracy', 'avg_topn_column_accuracy'
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
                # Basic metrics
                'avg_table_precision': f"{summary.avg_table_precision:.4f}",
                'avg_table_recall': f"{summary.avg_table_recall:.4f}",
                'avg_table_f1': f"{summary.avg_table_f1:.4f}",
                'avg_column_precision': f"{summary.avg_column_precision:.4f}",
                'avg_column_recall': f"{summary.avg_column_recall:.4f}",
                'avg_column_f1': f"{summary.avg_column_f1:.4f}",
                # Hit@k rates (binary)
                'table_hit_at_1_rate': f"{summary.table_hit_at_1_rate:.4f}",
                'table_hit_at_3_rate': f"{summary.table_hit_at_3_rate:.4f}",
                'table_hit_at_5_rate': f"{summary.table_hit_at_5_rate:.4f}",
                # Recall@k averages (fraction)
                'avg_table_recall_at_3': f"{summary.avg_table_recall_at_3:.4f}",
                'avg_table_recall_at_5': f"{summary.avg_table_recall_at_5:.4f}",
                'avg_table_recall_at_10': f"{summary.avg_table_recall_at_10:.4f}",
                # Advanced metrics
                'avg_table_mrr': f"{summary.avg_table_mrr:.4f}",
                'avg_table_jaccard': f"{summary.avg_table_jaccard:.4f}",
                'table_exact_match_rate': f"{summary.table_exact_match_rate:.4f}",
                # Joint table-column metrics
                'avg_joint_column_precision': f"{summary.avg_joint_column_precision:.4f}",
                'avg_joint_column_recall': f"{summary.avg_joint_column_recall:.4f}",
                'avg_joint_column_f1': f"{summary.avg_joint_column_f1:.4f}",
                # Top-N Accuracy
                'avg_topn_table_accuracy': f"{summary.avg_topn_table_accuracy:.4f}",
                'avg_topn_column_accuracy': f"{summary.avg_topn_column_accuracy:.4f}",
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
        n = len(successful)

        # Basic metrics
        summary.avg_execution_time_ms = sum(r.execution_time_ms for r in successful) / n
        summary.avg_table_precision = sum(r.table_precision for r in successful) / n
        summary.avg_table_recall = sum(r.table_recall for r in successful) / n
        summary.avg_table_f1 = sum(r.table_f1 for r in successful) / n
        summary.avg_column_precision = sum(r.column_precision for r in successful) / n
        summary.avg_column_recall = sum(r.column_recall for r in successful) / n
        summary.avg_column_f1 = sum(r.column_f1 for r in successful) / n

        # Hit@k rates (binary)
        summary.table_hit_at_1_rate = sum(1 for r in successful if r.table_hit_at_1) / n
        summary.table_hit_at_3_rate = sum(1 for r in successful if r.table_hit_at_3) / n
        summary.table_hit_at_5_rate = sum(1 for r in successful if r.table_hit_at_5) / n

        # Recall@k averages (fraction - better for multi-table)
        summary.avg_table_recall_at_3 = sum(r.table_recall_at_3 for r in successful) / n
        summary.avg_table_recall_at_5 = sum(r.table_recall_at_5 for r in successful) / n
        summary.avg_table_recall_at_10 = sum(r.table_recall_at_10 for r in successful) / n

        # Advanced metrics
        summary.avg_table_mrr = sum(r.table_mrr for r in successful) / n
        summary.avg_table_jaccard = sum(r.table_jaccard for r in successful) / n
        summary.table_exact_match_rate = sum(1 for r in successful if r.table_exact_match) / n

        # Joint table-column metrics
        summary.avg_joint_column_precision = sum(r.joint_column_precision for r in successful) / n
        summary.avg_joint_column_recall = sum(r.joint_column_recall for r in successful) / n
        summary.avg_joint_column_f1 = sum(r.joint_column_f1 for r in successful) / n

        # Top-N Accuracy
        summary.avg_topn_table_accuracy = sum(r.topn_table_accuracy for r in successful) / n
        summary.avg_topn_column_accuracy = sum(r.topn_column_accuracy for r in successful) / n

    return summary


# ============================================================================
# Browser Visualization
# ============================================================================

def generate_results_html(results: List[EvaluationResult],
                          summaries: List[DatabaseSummary],
                          run_params: Dict) -> str:
    """Generate a self-contained HTML page with evaluation results, summary, and run parameters."""

    timestamp = run_params.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    # --- Overall stats ---
    total_questions = sum(s.total_questions for s in summaries)
    total_successful = sum(s.successful_queries for s in summaries)
    total_failed = total_questions - total_successful
    overall_f1 = 0.0
    overall_hit1 = 0.0
    if total_successful > 0:
        overall_f1 = sum(s.avg_table_f1 * s.successful_queries for s in summaries) / total_successful
        overall_hit1 = sum(s.table_hit_at_1_rate * s.successful_queries for s in summaries) / total_successful

    # --- Build params table rows ---
    param_rows = ""
    for key, val in run_params.items():
        param_rows += f"<tr><td>{html.escape(str(key))}</td><td>{html.escape(str(val))}</td></tr>\n"

    # --- Build summary table rows ---
    summary_rows = ""
    for s in summaries:
        summary_rows += (
            f"<tr>"
            f"<td>{html.escape(s.db_id)}</td>"
            f"<td>{s.total_questions}</td>"
            f"<td>{s.successful_queries}</td>"
            f"<td>{s.failed_queries}</td>"
            f"<td>{s.avg_execution_time_ms:.2f}</td>"
            f"<td>{s.avg_table_precision:.4f}</td>"
            f"<td>{s.avg_table_recall:.4f}</td>"
            f"<td>{s.avg_table_f1:.4f}</td>"
            f"<td>{s.avg_column_precision:.4f}</td>"
            f"<td>{s.avg_column_recall:.4f}</td>"
            f"<td>{s.avg_column_f1:.4f}</td>"
            f"<td>{s.table_hit_at_1_rate:.2%}</td>"
            f"<td>{s.table_hit_at_3_rate:.2%}</td>"
            f"<td>{s.table_hit_at_5_rate:.2%}</td>"
            f"<td>{s.avg_table_mrr:.4f}</td>"
            f"<td>{s.avg_table_jaccard:.4f}</td>"
            f"<td>{s.table_exact_match_rate:.2%}</td>"
            f"<td>{s.avg_joint_column_f1:.4f}</td>"
            f"<td>{s.avg_topn_table_accuracy:.2%}</td>"
            f"<td>{s.avg_topn_column_accuracy:.2%}</td>"
            f"</tr>\n"
        )

    # --- Build results table rows (with data attrs for hover popup) ---
    result_rows = ""
    for r in results:
        error_class = ' class="error-row"' if r.error else ''
        f1_class = ""
        if r.error is None:
            if r.table_f1 >= 0.8:
                f1_class = ' class="good"'
            elif r.table_f1 >= 0.5:
                f1_class = ' class="fair"'
            else:
                f1_class = ' class="poor"'

        # Escape JSON for safe embedding in HTML data attributes
        esc_expected = html.escape(r.expected_json or '[]')
        esc_discovered = html.escape(r.discovered_json or '[]')
        esc_question = html.escape(r.question)

        result_rows += (
            f'<tr{error_class} data-question="{esc_question}" '
            f'data-expected="{esc_expected}" data-discovered="{esc_discovered}">'
            f"<td>{r.question_id}</td>"
            f"<td>{html.escape(r.db_id)}</td>"
            f"<td class='question-col'>{html.escape(r.question[:120])}</td>"
            f"<td>{r.execution_time_ms:.1f}</td>"
            f"<td>{', '.join(r.expected_tables)}</td>"
            f"<td>{', '.join(r.discovered_tables)}</td>"
            f"<td{f1_class}>{r.table_precision:.4f}</td>"
            f"<td{f1_class}>{r.table_recall:.4f}</td>"
            f"<td{f1_class}>{r.table_f1:.4f}</td>"
            f"<td>{r.column_precision:.4f}</td>"
            f"<td>{r.column_recall:.4f}</td>"
            f"<td>{r.column_f1:.4f}</td>"
            f"<td>{'Y' if r.table_hit_at_1 else 'N'}</td>"
            f"<td>{'Y' if r.table_hit_at_3 else 'N'}</td>"
            f"<td>{'Y' if r.table_hit_at_5 else 'N'}</td>"
            f"<td>{r.table_mrr:.4f}</td>"
            f"<td>{r.topn_table_accuracy:.2%}</td>"
            f"<td>{r.topn_column_accuracy:.2%}</td>"
            f"<td>{html.escape(r.error or '')}</td>"
            f"</tr>\n"
        )

    page_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hybrid Search Evaluation Results</title>
<style>
  :root {{
    --bg: #f5f6fa;
    --card-bg: #fff;
    --border: #dfe4ea;
    --text: #2f3542;
    --heading: #1e272e;
    --accent: #3742fa;
    --good: #2ed573;
    --fair: #ffa502;
    --poor: #ff4757;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, sans-serif;
    background: var(--bg); color: var(--text); padding: 20px; line-height: 1.5;
  }}
  h1 {{ color: var(--heading); margin-bottom: 6px; font-size: 1.8rem; }}
  .timestamp {{ color: #747d8c; font-size: 0.9rem; margin-bottom: 20px; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin: 16px 0; }}
  .card {{
    background: var(--card-bg); border-radius: 8px; padding: 18px; text-align: center;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08); border: 1px solid var(--border);
  }}
  .card .value {{ font-size: 2rem; font-weight: 700; color: var(--accent); }}
  .card .label {{ font-size: 0.82rem; color: #747d8c; margin-top: 4px; }}
  .section {{ background: var(--card-bg); border-radius: 8px; padding: 20px; margin: 16px 0; box-shadow: 0 1px 4px rgba(0,0,0,0.08); border: 1px solid var(--border); overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; }}
  th {{ background: #f1f2f6; text-align: left; padding: 10px 6px; border-bottom: 2px solid var(--border); position: sticky; top: 0; white-space: nowrap; font-size: 0.78rem; }}
  td {{ padding: 7px 6px; border-bottom: 1px solid var(--border); }}
  tr:hover {{ background: #f1f2f6; }}
  .error-row {{ background: #ffe0e3; }}
  .error-row:hover {{ background: #ffc9ce; }}
  .good {{ color: var(--good); font-weight: 600; }}
  .fair {{ color: var(--fair); font-weight: 600; }}
  .poor {{ color: var(--poor); font-weight: 600; }}
  .question-col {{ max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; }}
  .question-col:hover {{ color: var(--accent); }}
  .params-table {{ max-width: 600px; }}
  .params-table td:first-child {{ font-weight: 600; width: 220px; }}
  .filter-bar {{ margin: 12px 0; display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }}
  .filter-bar label {{ font-weight: 600; font-size: 0.85rem; }}
  .filter-bar select, .filter-bar input {{
    padding: 6px 10px; border: 1px solid var(--border); border-radius: 4px; font-size: 0.85rem;
  }}
  .filter-bar input[type="text"] {{ width: 240px; }}
  .tab-bar {{ display: flex; gap: 0; margin-bottom: -1px; position: relative; z-index: 1; }}
  .tab {{
    padding: 10px 24px; cursor: pointer; border: 1px solid var(--border); border-bottom: none;
    background: #f1f2f6; border-radius: 8px 8px 0 0; font-size: 0.9rem; font-weight: 600;
  }}
  .tab.active {{ background: var(--card-bg); border-bottom: 1px solid var(--card-bg); }}
  .tab-content {{ display: none; }}
  .tab-content.active {{ display: block; }}
  .server-note {{
    background: #dfe6e9; padding: 10px 16px; border-radius: 6px; font-size: 0.85rem;
    margin-top: 24px; color: #636e72;
  }}

  /* Hover detail popup */
  #detailPopup {{
    display: none; position: fixed; z-index: 999;
    background: var(--card-bg); border: 1px solid var(--border); border-radius: 10px;
    box-shadow: 0 8px 30px rgba(0,0,0,0.18); padding: 20px; max-width: 620px; max-height: 80vh;
    overflow-y: auto; font-size: 0.85rem;
  }}
  #detailPopup.visible {{ display: block; }}
  #detailPopup h3 {{ margin: 0 0 10px 0; font-size: 1rem; color: var(--heading); }}
  #detailPopup .popup-section {{ margin-bottom: 14px; }}
  #detailPopup .popup-label {{ font-weight: 700; color: #636e72; font-size: 0.78rem; text-transform: uppercase; margin-bottom: 4px; }}
  #detailPopup .popup-question {{ background: #f1f2f6; padding: 8px 12px; border-radius: 6px; line-height: 1.6; word-break: break-word; }}
  #detailPopup .json-block {{
    background: #2f3542; color: #dfe6e9; padding: 10px 12px; border-radius: 6px;
    font-family: 'SF Mono', 'Fira Code', monospace; font-size: 0.8rem;
    white-space: pre-wrap; word-break: break-word; max-height: 250px; overflow-y: auto;
  }}
  #detailPopup .close-btn {{
    position: absolute; top: 8px; right: 12px; cursor: pointer;
    font-size: 1.2rem; color: #747d8c; background: none; border: none;
  }}
  #detailPopup .close-btn:hover {{ color: var(--poor); }}
</style>
</head>
<body>

<h1>Oracle Hybrid Search Evaluation</h1>
<div class="timestamp">Run: {html.escape(timestamp)}</div>

<!-- Overall KPI cards -->
<div class="cards">
  <div class="card"><div class="value">{len(summaries)}</div><div class="label">Databases</div></div>
  <div class="card"><div class="value">{total_questions}</div><div class="label">Total Questions</div></div>
  <div class="card"><div class="value">{total_successful}</div><div class="label">Successful</div></div>
  <div class="card"><div class="value">{total_failed}</div><div class="label">Failed</div></div>
  <div class="card"><div class="value">{overall_f1:.4f}</div><div class="label">Overall Table F1</div></div>
  <div class="card"><div class="value">{overall_hit1:.2%}</div><div class="label">Overall Hit@1</div></div>
</div>

<!-- Tabs -->
<div class="tab-bar">
  <div class="tab active" onclick="switchTab('params')">Run Parameters</div>
  <div class="tab" onclick="switchTab('summary')">Database Summary</div>
  <div class="tab" onclick="switchTab('results')">Detailed Results</div>
</div>

<!-- Tab: Run Parameters -->
<div class="section tab-content active" id="tab-params">
  <table class="params-table">
    <tr><th>Parameter</th><th>Value</th></tr>
    {param_rows}
  </table>
</div>

<!-- Tab: Database Summary -->
<div class="section tab-content" id="tab-summary">
  <table>
    <tr>
      <th>Database</th><th>Questions</th><th>Success</th><th>Failed</th>
      <th>Avg Time (ms)</th>
      <th>Table P</th><th>Table R</th><th>Table F1</th>
      <th>Col P</th><th>Col R</th><th>Col F1</th>
      <th>Hit@1</th><th>Hit@3</th><th>Hit@5</th>
      <th>MRR</th><th>Jaccard</th><th>Exact Match</th><th>Joint Col F1</th>
      <th>Top-N Tbl</th><th>Top-N Col</th>
    </tr>
    {summary_rows}
  </table>
</div>

<!-- Tab: Detailed Results -->
<div class="section tab-content" id="tab-results">
  <div class="filter-bar">
    <label>Database:</label>
    <select id="dbFilter" onchange="filterResults()">
      <option value="">All</option>
    </select>
    <label>Search:</label>
    <input type="text" id="searchFilter" placeholder="Filter by question..." oninput="filterResults()">
  </div>
  <table id="resultsTable">
    <thead>
      <tr>
        <th>ID</th><th>Database</th><th>Question</th><th>Time (ms)</th>
        <th>Expected Tables</th><th>Discovered Tables</th>
        <th>Table P</th><th>Table R</th><th>Table F1</th>
        <th>Col P</th><th>Col R</th><th>Col F1</th>
        <th>Hit@1</th><th>Hit@3</th><th>Hit@5</th><th>MRR</th>
        <th>Top-N Tbl</th><th>Top-N Col</th>
        <th>Error</th>
      </tr>
    </thead>
    <tbody>
      {result_rows}
    </tbody>
  </table>
</div>

<!-- Hover detail popup -->
<div id="detailPopup">
  <button class="close-btn" onclick="hidePopup()">&times;</button>
  <h3 id="popupTitle">Question Details</h3>
  <div class="popup-section">
    <div class="popup-label">Full Question</div>
    <div class="popup-question" id="popupQuestion"></div>
  </div>
  <div class="popup-section">
    <div class="popup-label">Expected (tables &amp; columns)</div>
    <div class="json-block" id="popupExpected"></div>
  </div>
  <div class="popup-section">
    <div class="popup-label">Discovered (tables, scores &amp; columns)</div>
    <div class="json-block" id="popupDiscovered"></div>
  </div>
</div>

<div class="server-note">
  Press <strong>Ctrl+C</strong> in the terminal to stop the server. Click on a question to view expected vs discovered details.
</div>

<script>
  // Tab switching
  function switchTab(name) {{
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
    document.getElementById('tab-' + name).classList.add('active');
    event.target.classList.add('active');
  }}

  // Populate database filter dropdown
  (function() {{
    const rows = document.querySelectorAll('#resultsTable tbody tr');
    const dbs = new Set();
    rows.forEach(r => {{
      const db = r.children[1]?.textContent;
      if (db) dbs.add(db);
    }});
    const sel = document.getElementById('dbFilter');
    [...dbs].sort().forEach(db => {{
      const opt = document.createElement('option');
      opt.value = db; opt.textContent = db;
      sel.appendChild(opt);
    }});
  }})();

  // Filter results table
  function filterResults() {{
    const db = document.getElementById('dbFilter').value.toLowerCase();
    const q = document.getElementById('searchFilter').value.toLowerCase();
    document.querySelectorAll('#resultsTable tbody tr').forEach(row => {{
      const rowDb = row.children[1]?.textContent.toLowerCase() || '';
      const rowQ = row.children[2]?.textContent.toLowerCase() || '';
      const show = (db === '' || rowDb === db) && (q === '' || rowQ.includes(q));
      row.style.display = show ? '' : 'none';
    }});
  }}

  // Detail popup logic
  const popup = document.getElementById('detailPopup');

  function showPopup(row, evt) {{
    const question = row.dataset.question || '';
    const expected = row.dataset.expected || '[]';
    const discovered = row.dataset.discovered || '[]';

    document.getElementById('popupQuestion').textContent = question;

    try {{
      document.getElementById('popupExpected').textContent = JSON.stringify(JSON.parse(expected), null, 2);
    }} catch(e) {{
      document.getElementById('popupExpected').textContent = expected;
    }}
    try {{
      document.getElementById('popupDiscovered').textContent = JSON.stringify(JSON.parse(discovered), null, 2);
    }} catch(e) {{
      document.getElementById('popupDiscovered').textContent = discovered;
    }}

    // Position near click but keep on screen
    let x = evt.clientX + 16;
    let y = evt.clientY - 20;
    if (x + 640 > window.innerWidth) x = window.innerWidth - 650;
    if (x < 10) x = 10;
    if (y + 400 > window.innerHeight) y = window.innerHeight - 420;
    if (y < 10) y = 10;
    popup.style.left = x + 'px';
    popup.style.top = y + 'px';
    popup.classList.add('visible');
  }}

  function hidePopup() {{
    popup.classList.remove('visible');
  }}

  // Attach click handlers to question cells
  document.querySelectorAll('#resultsTable tbody tr').forEach(row => {{
    const qCell = row.children[2];
    if (qCell) {{
      qCell.addEventListener('click', function(e) {{
        e.stopPropagation();
        showPopup(row, e);
      }});
    }}
  }});

  // Close popup when clicking outside
  document.addEventListener('click', function(e) {{
    if (!popup.contains(e.target)) hidePopup();
  }});

  // Close popup with Escape key
  document.addEventListener('keydown', function(e) {{
    if (e.key === 'Escape') hidePopup();
  }});
</script>
</body>
</html>"""
    return page_html


def start_results_server(html_content: str, port: int = 8787):
    """Start a local HTTP server serving the results HTML page and open the browser."""

    class ResultsHandler(SimpleHTTPRequestHandler):
        """Serve the generated HTML for any request path."""
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html_content.encode('utf-8'))

        def log_message(self, format, *args):
            # Suppress per-request log noise
            pass

    # Try ports starting from the given one
    server = None
    for attempt_port in range(port, port + 20):
        try:
            server = HTTPServer(('127.0.0.1', attempt_port), ResultsHandler)
            port = attempt_port
            break
        except OSError:
            continue

    if server is None:
        print(f"Error: Could not find an open port in range {port}-{port + 19}")
        return

    url = f"http://127.0.0.1:{port}"
    print(f"\nResults server started at: {url}")
    print("Press Ctrl+C to stop the server and exit.\n")

    # Open browser after a short delay to let the server start
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()


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

    # Step 4: Execute index creation script and setup hybrid search
    package_installed = oracle_mgr.execute_index_creation(index_script)

    # Step 5: Call refresh_data and setup_hybrid_search (only if package was installed)
    if package_installed:
        refresh_ok = oracle_mgr.call_refresh_data()
        setup_ok = oracle_mgr.call_setup_hybrid_search()
        if not refresh_ok and not setup_ok:
            print(f"  Note: developer package not available, skipping hybrid search setup")
    else:
        print(f"  Note: Skipping hybrid search setup (package not installed)")

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
            expected_columns=expected_columns,
            num_expected_tables=len(expected_tables),
            num_expected_columns=len(expected_columns)
        )

        # Always populate expected JSON (known before calling Oracle)
        result.expected_json = json.dumps([
            {'table': o.table_name, 'columns': o.columns}
            for o in expected_objs
        ])

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
                # Populate discovered JSON
                result.discovered_json = json.dumps([
                    {'table': d.object_name, 'score': round(float(d.score), 4),
                     'columns': [col['name'] for col in d.columns]}
                    for d in discovered
                ])

                # Evaluate results
                metrics = evaluate_result(expected_objs, discovered)

                # Basic results
                result.discovered_tables = metrics['discovered_tables']
                result.discovered_columns = metrics['discovered_columns']

                # Basic metrics (Precision, Recall, F1)
                result.table_precision = metrics['table_precision']
                result.table_recall = metrics['table_recall']
                result.table_f1 = metrics['table_f1']
                result.column_precision = metrics['column_precision']
                result.column_recall = metrics['column_recall']
                result.column_f1 = metrics['column_f1']

                # Hit@k (binary)
                result.table_hit_at_1 = metrics['hit_at_1']
                result.table_hit_at_3 = metrics['hit_at_3']
                result.table_hit_at_5 = metrics['hit_at_5']

                # Recall@k (fraction - better for multi-table)
                result.table_recall_at_3 = metrics['recall_at_3']
                result.table_recall_at_5 = metrics['recall_at_5']
                result.table_recall_at_10 = metrics['recall_at_10']

                # Advanced metrics
                result.table_mrr = metrics['mrr']
                result.table_jaccard = metrics['jaccard']
                result.table_exact_match = metrics['exact_match']

                # Joint table-column metrics
                result.joint_column_precision = metrics['joint_column_precision']
                result.joint_column_recall = metrics['joint_column_recall']
                result.joint_column_f1 = metrics['joint_column_f1']

                # Top-N Accuracy
                result.topn_table_accuracy = metrics['topn_table_accuracy']
                result.topn_column_accuracy = metrics['topn_column_accuracy']
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
    parser.add_argument(
        '--test', '-t',
        action='store_true',
        help='Run in test mode: 2 databases, 5 questions each'
    )
    parser.add_argument(
        '--max-questions', '-q',
        type=int,
        default=None,
        help='Maximum questions per database (default: all)'
    )
    parser.add_argument(
        '--max-databases', '-n',
        type=int,
        default=None,
        help='Maximum number of databases to process (default: all)'
    )
    parser.add_argument(
        '--output-format', '-f',
        nargs='+',
        choices=['csv', 'browser'],
        default=['csv'],
        help='Output format(s): csv, browser, or both (default: csv)'
    )
    parser.add_argument(
        '--port', '-p',
        type=int,
        default=8787,
        help='Port for browser results server (default: 8787)'
    )

    args = parser.parse_args()

    # Apply test mode defaults
    if args.test:
        print("\n" + "="*60)
        print("RUNNING IN TEST MODE")
        print("="*60)
        if args.max_databases is None:
            args.max_databases = 2
        if args.max_questions is None:
            args.max_questions = 5
        # Use test output files
        if args.output == OUTPUT_CSV:
            args.output = "test_" + OUTPUT_CSV
        if args.summary == SUMMARY_CSV:
            args.summary = "test_" + SUMMARY_CSV
        print(f"  Max databases: {args.max_databases}")
        print(f"  Max questions per db: {args.max_questions}")
        print(f"  Output file: {args.output}")
        print(f"  Summary file: {args.summary}")
        print("="*60 + "\n")

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

    # Apply max_databases limit
    if args.max_databases is not None:
        ddl_folders = sorted(ddl_folders)[:args.max_databases]

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

            # Apply max_questions limit
            if args.max_questions is not None:
                questions = questions[:args.max_questions]

            results, summary = process_database(
                oracle_mgr, db_id, ddl_folder, questions, args.index_script
            )

            all_results.extend(results)
            all_summaries.append(summary)

        output_formats = args.output_format

        # Write CSV results
        if 'csv' in output_formats:
            if all_results:
                write_results_csv(all_results, args.output)
            if all_summaries:
                write_summary_csv(all_summaries, args.summary)

        # Print overall summary (always)
        if all_summaries:
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

    # Launch browser server (after DB connection is closed)
    if 'browser' in output_formats and all_results:
        run_params = {
            'connection_string': re.sub(r'/[^@]+@', '/***@', args.connection_string),
            'ddl_dir': args.ddl_dir,
            'metadata_file': args.metadata_file,
            'index_script': args.index_script,
            'databases': ', '.join(sorted(ddl_folders)) if not args.databases else ', '.join(args.databases),
            'test_mode': args.test,
            'max_questions': args.max_questions or 'all',
            'max_databases': args.max_databases or 'all',
            'output_formats': ', '.join(output_formats),
            'discover_k': 10,
            'discover_k0': 50,
            'discover_cols_per_obj': 5,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        html_content = generate_results_html(all_results, all_summaries, run_params)
        start_results_server(html_content, port=args.port)

    return 0


if __name__ == '__main__':
    sys.exit(main())
