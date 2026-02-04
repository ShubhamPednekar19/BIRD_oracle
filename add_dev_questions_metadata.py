#!/usr/bin/env python3
"""
Script to add tables and columns metadata to BIRD dev.json questions.

This script parses the SQL field in each question and extracts tables with
their associated columns in a nested structure:

{
  "tables": [
    {"name": "table_name", "columns": [{"name": "col1"}, {"name": "col2"}]}
  ]
}

Usage:
    python add_dev_questions_metadata.py <input_dev.json> [output_dev.json]

Example:
    python add_dev_questions_metadata.py dev.json dev_with_metadata.json
"""

import json
import re
import sys
from typing import List, Dict, Set, Tuple
from collections import defaultdict


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
    'EXTRACT', 'JULIANDAY', 'RANDOM', 'SIGN', 'CEIL', 'FLOOR',
    'POWER', 'SQRT', 'LOG', 'LOG10', 'EXP', 'MOD', 'PI', 'SIN', 'COS', 'TAN',
    # Table aliases
    'T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8', 'T9', 'T10',
    'T11', 'T12', 'T13', 'T14', 'T15', 'T16', 'T17', 'T18', 'T19', 'T20'
}


def extract_tables_with_aliases(sql: str) -> Tuple[Dict[str, str], List[str]]:
    """
    Extract table names and their aliases from SQL query.

    Returns:
        Tuple of (alias_to_table mapping, list of table names)
    """
    alias_to_table = {}
    tables = []

    # Normalize whitespace
    sql_normalized = ' '.join(sql.split())

    # Pattern for FROM clause: FROM table_name [AS] alias
    # Matches: FROM district T1, FROM district AS T1, FROM district
    from_pattern = r'\bFROM\s+(\w+)(?:\s+(?:AS\s+)?(\w+))?'
    from_matches = re.findall(from_pattern, sql_normalized, re.IGNORECASE)
    for match in from_matches:
        table_name = match[0]
        alias = match[1] if match[1] else None
        if table_name.upper() not in SQL_KEYWORDS:
            if table_name not in tables:
                tables.append(table_name)
            if alias:
                alias_to_table[alias.upper()] = table_name

    # Pattern for JOIN clauses
    join_pattern = r'\bJOIN\s+(\w+)(?:\s+(?:AS\s+)?(\w+))?'
    join_matches = re.findall(join_pattern, sql_normalized, re.IGNORECASE)
    for match in join_matches:
        table_name = match[0]
        alias = match[1] if match[1] else None
        if table_name.upper() not in SQL_KEYWORDS:
            if table_name not in tables:
                tables.append(table_name)
            if alias:
                alias_to_table[alias.upper()] = table_name

    # Handle comma-separated tables in FROM clause
    from_clause_match = re.search(
        r'\bFROM\s+(.*?)(?:\bWHERE\b|\bJOIN\b|\bORDER\b|\bGROUP\b|\bLIMIT\b|\bHAVING\b|$)',
        sql_normalized, re.IGNORECASE
    )
    if from_clause_match:
        from_clause = from_clause_match.group(1)
        parts = from_clause.split(',')
        for part in parts:
            part = part.strip()
            # Match: table_name [AS] alias
            match = re.match(r'(\w+)(?:\s+(?:AS\s+)?(\w+))?', part, re.IGNORECASE)
            if match:
                table_name = match.group(1)
                alias = match.group(2) if match.group(2) else None
                if table_name.upper() not in SQL_KEYWORDS:
                    if table_name not in tables:
                        tables.append(table_name)
                    if alias:
                        alias_to_table[alias.upper()] = table_name

    return alias_to_table, tables


def extract_columns_for_tables(sql: str, alias_to_table: Dict[str, str], tables: List[str]) -> Dict[str, Set[str]]:
    """
    Extract columns and associate them with their respective tables.

    Returns:
        Dictionary mapping table names to sets of column names
    """
    table_columns = defaultdict(set)

    # Normalize whitespace
    sql_normalized = ' '.join(sql.split())

    # Extract all backtick-quoted identifiers
    backtick_cols = re.findall(r'`([^`]+)`', sql)

    # Extract columns with explicit table/alias prefix: T1.column or table.column
    # Pattern matches: alias.column or alias.`column`
    prefixed_pattern = r'\b(\w+)\.`?([^`\s,\(\)]+)`?'
    prefixed_matches = re.findall(prefixed_pattern, sql_normalized)

    for prefix, column in prefixed_matches:
        column = column.strip('`"[]')
        if column.upper() in SQL_KEYWORDS:
            continue

        # Resolve alias to table name
        table_name = alias_to_table.get(prefix.upper(), prefix)

        # Only add if table_name is in our tables list
        if table_name in tables:
            table_columns[table_name].add(column)
        elif prefix in tables:
            table_columns[prefix].add(column)

    # For backtick columns without prefix, try to associate with tables
    # These are columns that appear without a table prefix
    for col in backtick_cols:
        if col.upper() not in SQL_KEYWORDS and col not in tables:
            # Check if this column was already assigned to a table
            already_assigned = any(col in cols for cols in table_columns.values())
            if not already_assigned:
                # If only one table, assign to it
                if len(tables) == 1:
                    table_columns[tables[0]].add(col)
                else:
                    # Try to find context clues from the SQL
                    # For now, assign to first table if we can't determine
                    if tables:
                        table_columns[tables[0]].add(col)

    # Extract simple columns from various clauses and try to associate them
    # Look for patterns like: WHERE column = or ORDER BY column
    simple_col_contexts = [
        (r'\bWHERE\s+(\w+)\s*(?:=|!=|<>|>=|<=|>|<|LIKE|IN|IS|BETWEEN)', 'where'),
        (r'\bORDER\s+BY\s+(\w+)', 'order'),
        (r'\bGROUP\s+BY\s+(\w+)', 'group'),
    ]

    for pattern, context in simple_col_contexts:
        matches = re.findall(pattern, sql_normalized, re.IGNORECASE)
        for col in matches:
            if col.upper() not in SQL_KEYWORDS and col not in tables:
                # Check if already assigned
                already_assigned = any(col in cols for cols in table_columns.values())
                if not already_assigned and tables:
                    # Assign to first table as default
                    table_columns[tables[0]].add(col)

    return table_columns


def extract_tables_with_columns(sql: str) -> List[Dict]:
    """
    Extract tables with their nested columns from a SQL query.

    Args:
        sql: The SQL query string

    Returns:
        List of table objects with nested columns:
        [{"name": "table", "columns": [{"name": "col1"}, {"name": "col2"}]}]
    """
    # Extract tables and their aliases
    alias_to_table, tables = extract_tables_with_aliases(sql)

    # Extract columns for each table
    table_columns = extract_columns_for_tables(sql, alias_to_table, tables)

    # Build the result structure
    result = []
    for table_name in tables:
        columns = table_columns.get(table_name, set())
        # Filter out any remaining keywords
        filtered_columns = [
            col for col in sorted(columns)
            if col.upper() not in SQL_KEYWORDS
            and not col.isdigit()
            and len(col) > 0
        ]

        table_obj = {
            "name": table_name,
            "columns": [{"name": col} for col in filtered_columns]
        }
        result.append(table_obj)

    return result


def process_dev_file(input_path: str, output_path: str) -> None:
    """
    Process the dev.json file and add tables with nested columns metadata.

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
        tables_with_columns = extract_tables_with_columns(sql)
        question['tables'] = tables_with_columns

        if (i + 1) % 100 == 0:
            print(f"  Processed {i + 1} questions...")

    print(f"Writing output file: {output_path}")

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(questions, f, indent=2, ensure_ascii=False)

    print("Done!")

    # Print some statistics
    total_tables = sum(len(q.get('tables', [])) for q in questions)
    total_columns = sum(
        sum(len(t.get('columns', [])) for t in q.get('tables', []))
        for q in questions
    )
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
