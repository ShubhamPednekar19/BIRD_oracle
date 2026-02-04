#!/usr/bin/env python3
"""
Script to add tables and columns metadata to BIRD dev.json questions.

This script parses the SQL field in each question and extracts:
- tables: Array of table names used in the SQL query
- columns: Array of column names used in the SQL query

Usage:
    python add_dev_questions_metadata.py <input_dev.json> [output_dev.json]

Example:
    python add_dev_questions_metadata.py dev.json dev_with_metadata.json
"""

import json
import re
import sys
from typing import List, Set, Tuple


# SQL keywords to exclude from columns
SQL_KEYWORDS = {
    'SELECT', 'FROM', 'WHERE', 'AND', 'OR', 'NOT', 'IN', 'LIKE', 'IS', 'NULL',
    'ORDER', 'BY', 'GROUP', 'HAVING', 'LIMIT', 'OFFSET', 'ASC', 'DESC',
    'JOIN', 'LEFT', 'RIGHT', 'INNER', 'OUTER', 'CROSS', 'ON', 'AS',
    'DISTINCT', 'ALL', 'UNION', 'INTERSECT', 'EXCEPT',
    'COUNT', 'SUM', 'AVG', 'MAX', 'MIN', 'ROUND', 'CAST', 'COALESCE',
    'CASE', 'WHEN', 'THEN', 'ELSE', 'END', 'BETWEEN',
    'EXISTS', 'ANY', 'SOME', 'TRUE', 'FALSE',
    'INTEGER', 'REAL', 'TEXT', 'NUMERIC', 'BLOB', 'VARCHAR', 'CHAR', 'INT',
    'CREATE', 'TABLE', 'INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER',
    'PRIMARY', 'KEY', 'FOREIGN', 'REFERENCES', 'INDEX', 'UNIQUE',
    'T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8', 'T9', 'T10',
    'IFNULL', 'IIF', 'SUBSTR', 'LENGTH', 'UPPER', 'LOWER', 'TRIM',
    'REPLACE', 'INSTR', 'PRINTF', 'STRFTIME', 'DATE', 'TIME', 'DATETIME',
    'NULLS', 'FIRST', 'LAST', 'WITH', 'RECURSIVE', 'OVER', 'PARTITION',
    'ROW', 'ROWS', 'RANGE', 'UNBOUNDED', 'PRECEDING', 'FOLLOWING', 'CURRENT',
    'ABS', 'TOTAL', 'GROUP_CONCAT', 'TYPEOF', 'HEX', 'QUOTE', 'ZEROBLOB',
    'GLOB', 'MATCH', 'REGEXP', 'COLLATE', 'NOCASE', 'RTRIM', 'LTRIM',
    'VALUES', 'SET', 'DEFAULT', 'CHECK', 'CONSTRAINT', 'AUTOINCREMENT',
    'NATURAL', 'USING', 'FULL', 'BOOLEAN', 'DOUBLE', 'FLOAT', 'DECIMAL',
    'BIGINT', 'SMALLINT', 'TINYINT', 'NUMBER', 'STRING', 'TIMESTAMP',
    'YEAR', 'MONTH', 'DAY', 'HOUR', 'MINUTE', 'SECOND', 'INTERVAL',
    'EXTRACT', 'JULIANDAY', 'RANDOM', 'ABS', 'SIGN', 'CEIL', 'FLOOR',
    'POWER', 'SQRT', 'LOG', 'LOG10', 'EXP', 'MOD', 'PI', 'SIN', 'COS', 'TAN'
}

# Table aliases to skip
TABLE_ALIASES = {'T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8', 'T9', 'T10'}


def extract_quoted_identifiers(sql: str) -> Tuple[Set[str], str]:
    """
    Extract all quoted identifiers (backticks, double quotes, brackets) and
    replace them with placeholders.

    Returns:
        Tuple of (set of quoted identifiers, modified SQL with placeholders)
    """
    identifiers = set()
    placeholder_map = {}
    placeholder_count = [0]  # Use list for mutable int in closure

    def replace_with_placeholder(match):
        identifier = match.group(1)
        placeholder = f"__PLACEHOLDER_{placeholder_count[0]}__"
        placeholder_map[placeholder] = identifier
        identifiers.add(identifier)
        placeholder_count[0] += 1
        return placeholder

    # Extract backtick-quoted identifiers
    modified_sql = re.sub(r'`([^`]+)`', replace_with_placeholder, sql)

    # Extract double-quoted identifiers (but not string literals in WHERE)
    # Be careful to distinguish between column names and string values
    modified_sql = re.sub(r'"([^"]+)"(?=\s*(?:,|\)|FROM|WHERE|AND|OR|ORDER|GROUP|HAVING|JOIN|ON|AS|=|!=|<|>|LIKE|IN|BETWEEN|$))',
                          replace_with_placeholder, modified_sql, flags=re.IGNORECASE)

    # Extract bracket-quoted identifiers [column name]
    modified_sql = re.sub(r'\[([^\]]+)\]', replace_with_placeholder, sql)

    return identifiers, modified_sql


def extract_tables(sql: str) -> Set[str]:
    """Extract table names from SQL query."""
    tables = set()

    # Normalize whitespace
    sql_normalized = ' '.join(sql.split())

    # Pattern for FROM clause: FROM table_name [AS alias]
    # Handle both simple table names and those followed by aliases
    from_pattern = r'\bFROM\s+(\w+)(?:\s+(?:AS\s+)?(?:T\d+|\w+))?'
    from_matches = re.findall(from_pattern, sql_normalized, re.IGNORECASE)
    for table in from_matches:
        if table.upper() not in TABLE_ALIASES and table.upper() not in SQL_KEYWORDS:
            tables.add(table)

    # Pattern for JOIN clauses
    join_pattern = r'\bJOIN\s+(\w+)(?:\s+(?:AS\s+)?(?:T\d+|\w+))?'
    join_matches = re.findall(join_pattern, sql_normalized, re.IGNORECASE)
    for table in join_matches:
        if table.upper() not in TABLE_ALIASES and table.upper() not in SQL_KEYWORDS:
            tables.add(table)

    # Also handle comma-separated tables in FROM clause
    # FROM table1, table2, table3 WHERE ...
    from_clause_match = re.search(r'\bFROM\s+(.*?)(?:\bWHERE\b|\bJOIN\b|\bORDER\b|\bGROUP\b|\bLIMIT\b|\bHAVING\b|$)',
                                   sql_normalized, re.IGNORECASE)
    if from_clause_match:
        from_clause = from_clause_match.group(1)
        # Split by comma and extract table names
        parts = from_clause.split(',')
        for part in parts:
            part = part.strip()
            # Get first word (table name)
            match = re.match(r'(\w+)', part)
            if match:
                table = match.group(1)
                if table.upper() not in TABLE_ALIASES and table.upper() not in SQL_KEYWORDS:
                    tables.add(table)

    return tables


def extract_columns(sql: str, tables: Set[str]) -> Set[str]:
    """Extract column names from SQL query."""
    columns = set()

    # First, extract all quoted identifiers (these are likely column names)
    quoted_identifiers, _ = extract_quoted_identifiers(sql)

    # Add quoted identifiers that aren't tables
    for identifier in quoted_identifiers:
        if identifier not in tables and identifier.upper() not in SQL_KEYWORDS:
            columns.add(identifier)

    # Normalize whitespace
    sql_normalized = ' '.join(sql.split())

    # Extract columns from table.column or alias.column patterns
    # Match: T1.column_name or table.column_name
    table_col_pattern = r'(?:T\d+|\w+)\.([`"\[\]]?[\w]+[`"\]]?)'
    table_col_matches = re.findall(table_col_pattern, sql_normalized)
    for col in table_col_matches:
        col = col.strip('`"[]')
        if col.upper() not in SQL_KEYWORDS and col not in tables:
            columns.add(col)

    # Extract simple column names from SELECT clause
    select_match = re.search(r'\bSELECT\s+(.*?)\s+FROM\b', sql_normalized, re.IGNORECASE)
    if select_match:
        select_clause = select_match.group(1)
        # Remove DISTINCT keyword
        select_clause = re.sub(r'\bDISTINCT\s+', '', select_clause, flags=re.IGNORECASE)

        # Find simple column references (not in function calls)
        simple_cols = re.findall(r'\b([a-zA-Z_]\w*)\b', select_clause)
        for col in simple_cols:
            if (col.upper() not in SQL_KEYWORDS and
                col not in tables and
                col.upper() not in TABLE_ALIASES and
                not col.startswith('T') or len(col) > 2):  # Skip T1, T2, etc.
                columns.add(col)

    # Extract columns from WHERE clause
    where_match = re.search(r'\bWHERE\s+(.*?)(?:\bGROUP\b|\bORDER\b|\bLIMIT\b|\bHAVING\b|$)',
                            sql_normalized, re.IGNORECASE)
    if where_match:
        where_clause = where_match.group(1)
        # Find column references before operators
        col_pattern = r'\b([a-zA-Z_]\w*)\s*(?:=|!=|<>|>=|<=|>|<|LIKE|IN|IS|BETWEEN)'
        col_matches = re.findall(col_pattern, where_clause, re.IGNORECASE)
        for col in col_matches:
            if (col.upper() not in SQL_KEYWORDS and
                col not in tables and
                col.upper() not in TABLE_ALIASES):
                columns.add(col)

    # Extract columns from GROUP BY clause
    groupby_match = re.search(r'\bGROUP\s+BY\s+(.*?)(?:\bHAVING\b|\bORDER\b|\bLIMIT\b|$)',
                              sql_normalized, re.IGNORECASE)
    if groupby_match:
        groupby_clause = groupby_match.group(1)
        cols = re.findall(r'\b([a-zA-Z_]\w*)\b', groupby_clause)
        for col in cols:
            if (col.upper() not in SQL_KEYWORDS and
                col not in tables and
                col.upper() not in TABLE_ALIASES):
                columns.add(col)

    # Extract columns from ORDER BY clause
    orderby_match = re.search(r'\bORDER\s+BY\s+(.*?)(?:\bLIMIT\b|\bOFFSET\b|$)',
                              sql_normalized, re.IGNORECASE)
    if orderby_match:
        orderby_clause = orderby_match.group(1)
        cols = re.findall(r'\b([a-zA-Z_]\w*)\b', orderby_clause)
        for col in cols:
            if (col.upper() not in SQL_KEYWORDS and
                col not in tables and
                col.upper() not in TABLE_ALIASES):
                columns.add(col)

    # Extract columns from ON clause (JOINs)
    on_matches = re.findall(r'\bON\s+(.*?)(?:\bWHERE\b|\bGROUP\b|\bORDER\b|\bLIMIT\b|\bJOIN\b|$)',
                            sql_normalized, re.IGNORECASE)
    for on_clause in on_matches:
        cols = re.findall(r'\b([a-zA-Z_]\w*)\s*=', on_clause)
        cols += re.findall(r'=\s*\b([a-zA-Z_]\w*)\b', on_clause)
        for col in cols:
            if (col.upper() not in SQL_KEYWORDS and
                col not in tables and
                col.upper() not in TABLE_ALIASES):
                columns.add(col)

    # Clean up - remove table aliases like T1, T2, etc.
    columns = {c for c in columns if not re.match(r'^T\d+$', c, re.IGNORECASE)}

    return columns


def extract_tables_and_columns(sql: str) -> Tuple[List[str], List[str]]:
    """
    Extract table names and column names from a SQL query.

    Args:
        sql: The SQL query string

    Returns:
        Tuple of (tables list, columns list)
    """
    tables = extract_tables(sql)
    columns = extract_columns(sql, tables)

    # Final cleanup - ensure columns don't include tables
    columns = columns - tables

    # Filter out any remaining keywords or aliases
    filtered_columns = set()
    for col in columns:
        if (col.upper() not in SQL_KEYWORDS and
            col.upper() not in TABLE_ALIASES and
            len(col) > 0 and
            not col.isdigit()):
            filtered_columns.add(col)

    return sorted(list(tables)), sorted(list(filtered_columns))


def process_dev_file(input_path: str, output_path: str) -> None:
    """
    Process the dev.json file and add tables and columns metadata.

    Args:
        input_path: Path to input dev.json file
        output_path: Path to output file with added metadata
    """
    print(f"Reading input file: {input_path}")

    with open(input_path, 'r', encoding='utf-8') as f:
        questions = json.load(f)

    print(f"Processing {len(questions)} questions...")

    for i, question in enumerate(questions):
        sql = question.get('SQL', '')
        tables, columns = extract_tables_and_columns(sql)

        question['tables'] = tables
        question['columns'] = columns

        if (i + 1) % 100 == 0:
            print(f"  Processed {i + 1} questions...")

    print(f"Writing output file: {output_path}")

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(questions, f, indent=2, ensure_ascii=False)

    print("Done!")

    # Print some statistics
    total_tables = sum(len(q.get('tables', [])) for q in questions)
    total_columns = sum(len(q.get('columns', [])) for q in questions)
    print(f"\nStatistics:")
    print(f"  Total questions: {len(questions)}")
    print(f"  Total table references: {total_tables}")
    print(f"  Total column references: {total_columns}")
    print(f"  Average tables per question: {total_tables / len(questions):.2f}")
    print(f"  Average columns per question: {total_columns / len(questions):.2f}")


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python add_dev_questions_metadata.py <input_dev.json> [output_dev.json]")
        print("\nIf output path is not specified, the input file will be modified in place.")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else input_path

    process_dev_file(input_path, output_path)


if __name__ == "__main__":
    main()
