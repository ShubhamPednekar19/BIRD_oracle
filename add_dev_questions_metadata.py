#!/usr/bin/env python3
"""
Script to add tables and columns metadata to BIRD dev.json questions
and convert SQLite SQL to Oracle SQL format.

This script parses the SQL field in each question and:
1. Extracts tables with their associated columns in a nested structure
2. Converts SQLite SQL syntax to Oracle SQL syntax

Output structure:
{
  "tables": [
    {"name": "table_name", "columns": [{"name": "col1"}, {"name": "col2"}]}
  ],
  "oracle_SQL": "SELECT ... FROM ... FETCH FIRST 1 ROWS ONLY"
}

Usage:
    python add_dev_questions_metadata.py <input_dev.json> [output_dev.json]

Example:
    python add_dev_questions_metadata.py dev.json dev_with_metadata.json
"""

import argparse
import json
import re
import sys
from typing import List, Dict, Set, Tuple, Optional
from collections import defaultdict
from urllib import request, error

try:
    from openai import OpenAI
except ImportError:  # Optional dependency for --method llm
    OpenAI = None


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

# Oracle reserved words that need to be quoted
ORACLE_RESERVED_WORDS = {
    'ACCESS', 'ADD', 'ALL', 'ALTER', 'AND', 'ANY', 'AS', 'ASC', 'AUDIT',
    'BETWEEN', 'BY', 'CHAR', 'CHECK', 'CLUSTER', 'COLUMN', 'COMMENT',
    'COMPRESS', 'CONNECT', 'CREATE', 'CURRENT', 'DATE', 'DECIMAL', 'DEFAULT',
    'DELETE', 'DESC', 'DISTINCT', 'DROP', 'ELSE', 'EXCLUSIVE', 'EXISTS',
    'FILE', 'FLOAT', 'FOR', 'FROM', 'GRANT', 'GROUP', 'HAVING', 'IDENTIFIED',
    'IMMEDIATE', 'IN', 'INCREMENT', 'INDEX', 'INITIAL', 'INSERT', 'INTEGER',
    'INTERSECT', 'INTO', 'IS', 'LEVEL', 'LIKE', 'LOCK', 'LONG', 'MAXEXTENTS',
    'MINUS', 'MLSLABEL', 'MODE', 'MODIFY', 'NOAUDIT', 'NOCOMPRESS', 'NOT',
    'NOWAIT', 'NULL', 'NUMBER', 'OF', 'OFFLINE', 'ON', 'ONLINE', 'OPTION',
    'OR', 'ORDER', 'PCTFREE', 'PRIOR', 'PUBLIC', 'RAW', 'RENAME', 'RESOURCE',
    'REVOKE', 'ROW', 'ROWID', 'ROWNUM', 'ROWS', 'SELECT', 'SESSION', 'SET',
    'SHARE', 'SIZE', 'SMALLINT', 'START', 'SUCCESSFUL', 'SYNONYM', 'SYSDATE',
    'TABLE', 'THEN', 'TO', 'TRIGGER', 'UID', 'UNION', 'UNIQUE', 'UPDATE',
    'USER', 'VALIDATE', 'VALUES', 'VARCHAR', 'VARCHAR2', 'VIEW', 'WHENEVER',
    'WHERE', 'WITH', 'CROSS', 'COMMENT', 'STATUS', 'TYPE', 'RANK', 'RESULT',
    'LOOP', 'OPEN', 'CLOSE', 'CURSOR', 'FETCH', 'EXCEPTION', 'RAISE', 'END',
    'IF', 'THEN', 'ELSIF', 'RETURN', 'FUNCTION', 'PROCEDURE', 'PACKAGE',
    'BODY', 'EXECUTE', 'TRANSACTION', 'COMMIT', 'ROLLBACK', 'SAVEPOINT',
    'ACCOUNT', 'ACTION', 'ADMIN', 'ALGORITHM', 'ANALYZE', 'ARCHIVE', 'ARRAY',
    'ATTRIBUTE', 'ATTRIBUTES', 'BFILE', 'BINARY', 'BLOB', 'BLOCK', 'BOOLEAN',
    'BOTH', 'BUFFER', 'BUILD', 'CACHE', 'CALL', 'CASCADE', 'CAST', 'CHANGE',
    'CHARACTER', 'CHARSET', 'CLOB', 'COLLATE', 'COLLATION', 'COLUMNS',
    'COMPACT', 'COMPILE', 'CONSTRAINT', 'CONSTRAINTS', 'CONTENT', 'CONTEXT',
    'CONTINUE', 'CONVERT', 'COPY', 'COUNT', 'CROSS', 'CUBE', 'CYCLE',
    'DATABASE', 'DATABASES', 'DAY', 'DEALLOCATE', 'DECLARE', 'DEFERRABLE',
    'DEFERRED', 'DEFINER', 'DENSE_RANK', 'DIRECTORY', 'DISABLE', 'DISCARD',
    'DISK', 'DO', 'DOCUMENT', 'DOMAIN', 'DOUBLE', 'DUMP', 'EACH', 'ELEMENT',
    'ENABLE', 'ENCODING', 'ENCRYPT', 'ENCRYPTION', 'ENGINE', 'ENUM', 'ERROR',
    'ERRORS', 'ESCAPE', 'EVENT', 'EVENTS', 'EXCHANGE', 'EXCLUDE', 'EXCLUDING',
    'EXEC', 'EXPANSION', 'EXPIRE', 'EXPLAIN', 'EXPORT', 'EXTENDED', 'EXTENT',
    'EXTERNAL', 'EXTRACT', 'FALSE', 'FAST', 'FAULTS', 'FIELDS', 'FIRST',
    'FIXED', 'FOLLOWING', 'FORCE', 'FOREIGN', 'FORMAT', 'FOUND', 'FREELIST',
    'FREELISTS', 'FULL', 'GLOBAL', 'GROUPING', 'GROUPS', 'HASH', 'HEAP',
    'HIERARCHY', 'HOUR', 'IDENTITY', 'IGNORE', 'IMPORT', 'INCLUDE', 'INCLUDING',
    'INDEXES', 'INDICATOR', 'INHERIT', 'INITIALLY', 'INITRANS', 'INNER', 'INPUT',
    'INSTANCE', 'INSTANCES', 'INSTEAD', 'INTERVAL', 'ISOLATION', 'JAVA', 'JOIN',
    'JSON', 'KEEP', 'KEY', 'KEYS', 'LAG', 'LANGUAGE', 'LAST', 'LATERAL', 'LEAD',
    'LEADING', 'LEFT', 'LIMIT', 'LINEAR', 'LINK', 'LIST', 'LOB', 'LOBS', 'LOCAL',
    'LOCATION', 'LOCATOR', 'LOGGING', 'LOGFILE', 'MANAGED', 'MANAGEMENT', 'MANUAL',
    'MAP', 'MAPPING', 'MASTER', 'MATCH', 'MATCHED', 'MATERIALIZED', 'MAX', 'MAXVALUE',
    'MEASURES', 'MEMBER', 'MEMORY', 'MERGE', 'METHOD', 'MIN', 'MINEXTENTS', 'MINIMUM',
    'MINUTE', 'MINVALUE', 'MISSING', 'MODEL', 'MODIFY', 'MODULE', 'MONTH', 'MOUNT',
    'MOVE', 'MULTISET', 'NAME', 'NAMES', 'NATIONAL', 'NATURAL', 'NAV', 'NCHAR',
    'NCLOB', 'NESTED', 'NEVER', 'NEW', 'NEXT', 'NO', 'NOARCHIVE', 'NOCACHE',
    'NOCOPY', 'NOCYCLE', 'NOLOGGING', 'NOMAPPING', 'NOMAXVALUE', 'NOMINVALUE',
    'NONE', 'NOORDER', 'NOPARALLEL', 'NORELY', 'NOREVERSE', 'NORMAL', 'NOTHING',
    'NULLS', 'OBJECT', 'OBJECTS', 'OFF', 'OFFSET', 'OID', 'OLD', 'ONLY', 'OPERATOR',
    'OPTIMAL', 'OPTIMIZE', 'OTHERS', 'OUT', 'OUTER', 'OUTPUT', 'OVER', 'OVERFLOW',
    'OVERLAPS', 'OWNER', 'PARALLEL', 'PARAMETERS', 'PARENT', 'PARTIAL', 'PARTITION',
    'PARTITIONS', 'PASSING', 'PASSWORD', 'PATH', 'PCTINCREASE', 'PCTTHRESHOLD',
    'PCTUSED', 'PCTVERSION', 'PERCENT', 'PERMANENT', 'PHYSICAL', 'PIVOT', 'PLAN',
    'POSITION', 'PRAGMA', 'PRECEDING', 'PRECISION', 'PREPARE', 'PRESERVE', 'PRIMARY',
    'PRIVATE', 'PRIVILEGE', 'PRIVILEGES', 'PROFILE', 'PROGRAM', 'PURGE', 'QUERY',
    'QUEUE', 'QUOTA', 'RANDOM', 'RANGE', 'READ', 'READS', 'REBUILD', 'RECORD',
    'RECORDS', 'RECOVER', 'RECOVERY', 'RECYCLE', 'REDO', 'REF', 'REFERENCE',
    'REFERENCES', 'REFERENCING', 'REFRESH', 'REGEXP', 'REJECT', 'RELATIONAL',
    'RELY', 'REMOTE', 'REPLACE', 'REPLICATION', 'REQUIRED', 'RESET', 'RESIZE',
    'RESOLVE', 'RESOLVER', 'RESTART', 'RESTRICT', 'RESTRICTED', 'RESULT', 'REUSE',
    'REVERSE', 'RIGHT', 'RLIKE', 'ROLE', 'ROLES', 'ROLLUP', 'ROUTINE', 'ROWCOUNT',
    'RULE', 'RULES', 'SAMPLE', 'SAVE', 'SCAN', 'SCHEMA', 'SCHEMAS', 'SCN', 'SCOPE',
    'SCROLL', 'SEARCH', 'SECOND', 'SECTION', 'SEGMENT', 'SELF', 'SEQUENCE', 'SEQUENCES',
    'SERIALIZABLE', 'SERVER', 'SETS', 'SETTINGS', 'SHUTDOWN', 'SIBLINGS', 'SINGLE',
    'SKIP', 'SNAPSHOT', 'SOME', 'SORT', 'SPACE', 'SPECIFICATION', 'SPLIT', 'SQL',
    'STANDBY', 'STARTUP', 'STATEMENT', 'STATIC', 'STATISTICS', 'STOP', 'STORAGE',
    'STORE', 'STRICT', 'STRING', 'STRUCTURE', 'SUBPARTITION', 'SUBPARTITIONS', 'SUBTYPE',
    'SUSPEND', 'SWITCH', 'SYSTEM', 'TABLES', 'TABLESPACE', 'TEMP', 'TEMPLATE',
    'TEMPORARY', 'TEST', 'TEXT', 'THAN', 'THREAD', 'THROUGH', 'TIME', 'TIMESTAMP',
    'TIMEZONE', 'TIMEOUT', 'TRACE', 'TRAILING', 'TRANSFORM', 'TREAT', 'TRIGGERS',
    'TRIM', 'TRUE', 'TRUNCATE', 'TRUSTED', 'TUNING', 'TYPES', 'UNBOUNDED', 'UNDER',
    'UNDO', 'UNIFORM', 'UNLIMITED', 'UNLOCK', 'UNPIVOT', 'UNRECOVERABLE', 'UNTIL',
    'UNUSABLE', 'UPDATED', 'UPGRADE', 'UPSERT', 'USAGE', 'USE', 'USING', 'VALID',
    'VALIDATION', 'VALUE', 'VARYING', 'VERSION', 'VERSIONS', 'VIRTUAL', 'VISIBLE',
    'WAIT', 'WELLFORMED', 'WITHIN', 'WITHOUT', 'WORK', 'WRAPPER', 'WRITE', 'XML',
    'XMLAGG', 'XMLCAST', 'XMLCOLATTVAL', 'XMLELEMENT', 'XMLEXISTS', 'XMLFOREST',
    'XMLNAMESPACES', 'XMLPARSE', 'XMLPI', 'XMLQUERY', 'XMLROOT', 'XMLSCHEMA',
    'XMLSERIALIZE', 'XMLTABLE', 'XMLTYPE', 'YEAR', 'YES', 'ZONE'
}


def needs_oracle_quoting(identifier: str) -> bool:
    """Check if an identifier needs to be quoted in Oracle."""
    upper_id = identifier.upper()
    if upper_id in ORACLE_RESERVED_WORDS:
        return True
    if not identifier[0].isalpha() and identifier[0] != '_':
        return True
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', identifier):
        return True
    return False


def convert_identifier_to_oracle(identifier: str) -> str:
    """Convert a SQLite identifier to Oracle format."""
    # Remove backticks
    identifier = identifier.strip('`')

    if needs_oracle_quoting(identifier):
        # Escape double quotes and wrap in double quotes
        identifier = identifier.replace('"', '""')
        return f'"{identifier}"'
    return identifier


def convert_sqlite_to_oracle_sql(sql: str) -> str:
    """
    Convert SQLite SQL syntax to Oracle SQL syntax.

    Handles:
    - LIMIT n -> FETCH FIRST n ROWS ONLY
    - LIMIT n OFFSET m -> OFFSET m ROWS FETCH NEXT n ROWS ONLY
    - IFNULL(a, b) -> NVL(a, b)
    - Backticks -> double quotes
    - CAST(x AS REAL/INTEGER/TEXT) -> Oracle types
    - GROUP_CONCAT -> LISTAGG
    - IIF -> CASE WHEN
    - strftime -> TO_CHAR
    - Date functions
    """
    oracle_sql = sql

    # Convert backtick-quoted identifiers to Oracle double-quoted
    def replace_backtick(match):
        identifier = match.group(1)
        return convert_identifier_to_oracle(identifier)

    oracle_sql = re.sub(r'`([^`]+)`', replace_backtick, oracle_sql)

    # Convert IFNULL to NVL
    oracle_sql = re.sub(r'\bIFNULL\s*\(', 'NVL(', oracle_sql, flags=re.IGNORECASE)

    # Convert NULLIF (same in Oracle, but ensure uppercase)
    oracle_sql = re.sub(r'\bNULLIF\s*\(', 'NULLIF(', oracle_sql, flags=re.IGNORECASE)

    # Convert IIF(condition, true_val, false_val) to CASE WHEN condition THEN true_val ELSE false_val END
    def convert_iif(match):
        # This is a simplified conversion - may need adjustment for complex nested cases
        content = match.group(1)
        # Find the first comma (condition separator)
        depth = 0
        first_comma = -1
        second_comma = -1
        for i, char in enumerate(content):
            if char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
            elif char == ',' and depth == 0:
                if first_comma == -1:
                    first_comma = i
                else:
                    second_comma = i
                    break

        if first_comma != -1 and second_comma != -1:
            condition = content[:first_comma].strip()
            true_val = content[first_comma+1:second_comma].strip()
            false_val = content[second_comma+1:].strip()
            return f'CASE WHEN {condition} THEN {true_val} ELSE {false_val} END'
        return match.group(0)

    oracle_sql = re.sub(r'\bIIF\s*\(([^)]+(?:\([^)]*\)[^)]*)*)\)', convert_iif, oracle_sql, flags=re.IGNORECASE)

    # Convert GROUP_CONCAT to LISTAGG
    # GROUP_CONCAT(col) -> LISTAGG(col, ',') WITHIN GROUP (ORDER BY col)
    # GROUP_CONCAT(col, sep) -> LISTAGG(col, sep) WITHIN GROUP (ORDER BY col)
    def convert_group_concat(match):
        content = match.group(1)
        parts = content.split(',', 1)
        col = parts[0].strip()
        sep = parts[1].strip() if len(parts) > 1 else "','"
        return f'LISTAGG({col}, {sep}) WITHIN GROUP (ORDER BY {col})'

    oracle_sql = re.sub(r'\bGROUP_CONCAT\s*\(([^)]+)\)', convert_group_concat, oracle_sql, flags=re.IGNORECASE)

    # Convert CAST types - use word boundary to match type names
    # Handle AS REAL, AS INTEGER, etc. by replacing the type name directly
    oracle_sql = re.sub(r'\bAS\s+REAL\b', 'AS NUMBER', oracle_sql, flags=re.IGNORECASE)
    oracle_sql = re.sub(r'\bAS\s+INTEGER\b', 'AS NUMBER', oracle_sql, flags=re.IGNORECASE)
    oracle_sql = re.sub(r'\bAS\s+INT\b', 'AS NUMBER', oracle_sql, flags=re.IGNORECASE)
    oracle_sql = re.sub(r'\bAS\s+TEXT\b', 'AS VARCHAR2(4000)', oracle_sql, flags=re.IGNORECASE)
    oracle_sql = re.sub(r'\bAS\s+FLOAT\b', 'AS NUMBER', oracle_sql, flags=re.IGNORECASE)
    oracle_sql = re.sub(r'\bAS\s+NUMERIC\b', 'AS NUMBER', oracle_sql, flags=re.IGNORECASE)

    # Convert strftime to TO_CHAR
    # strftime('%Y', date_col) -> TO_CHAR(date_col, 'YYYY')
    # strftime('%m', date_col) -> TO_CHAR(date_col, 'MM')
    # strftime('%d', date_col) -> TO_CHAR(date_col, 'DD')
    # strftime('%Y-%m-%d', date_col) -> TO_CHAR(date_col, 'YYYY-MM-DD')
    def convert_strftime(match):
        format_str = match.group(1)
        col = match.group(2)

        # Convert SQLite format to Oracle format
        oracle_format = format_str
        oracle_format = oracle_format.replace('%Y', 'YYYY')
        oracle_format = oracle_format.replace('%m', 'MM')
        oracle_format = oracle_format.replace('%d', 'DD')
        oracle_format = oracle_format.replace('%H', 'HH24')
        oracle_format = oracle_format.replace('%M', 'MI')
        oracle_format = oracle_format.replace('%S', 'SS')
        oracle_format = oracle_format.replace('%W', 'IW')  # Week number
        oracle_format = oracle_format.replace('%j', 'DDD')  # Day of year
        oracle_format = oracle_format.replace('%w', 'D')    # Day of week

        return f"TO_CHAR({col}, '{oracle_format}')"

    oracle_sql = re.sub(r"\bstrftime\s*\(\s*'([^']+)'\s*,\s*([^)]+)\)", convert_strftime, oracle_sql, flags=re.IGNORECASE)

    # Convert date('now') to SYSDATE
    oracle_sql = re.sub(r"\bdate\s*\(\s*'now'\s*\)", 'SYSDATE', oracle_sql, flags=re.IGNORECASE)

    # Convert datetime('now') to SYSTIMESTAMP
    oracle_sql = re.sub(r"\bdatetime\s*\(\s*'now'\s*\)", 'SYSTIMESTAMP', oracle_sql, flags=re.IGNORECASE)

    # Convert RANDOM() to DBMS_RANDOM.VALUE
    oracle_sql = re.sub(r'\bRANDOM\s*\(\s*\)', 'DBMS_RANDOM.VALUE', oracle_sql, flags=re.IGNORECASE)

    # Convert TOTAL() to SUM() (TOTAL is SQLite-specific)
    oracle_sql = re.sub(r'\bTOTAL\s*\(', 'SUM(', oracle_sql, flags=re.IGNORECASE)

    # Convert GLOB to LIKE (approximate - GLOB uses * and ?, LIKE uses % and _)
    # This is a simplified conversion
    def convert_glob(match):
        col = match.group(1)
        pattern = match.group(2)
        # Convert GLOB wildcards to LIKE wildcards
        like_pattern = pattern.replace('*', '%').replace('?', '_')
        return f"{col} LIKE {like_pattern}"

    oracle_sql = re.sub(r"(\w+)\s+GLOB\s+('[^']+')", convert_glob, oracle_sql, flags=re.IGNORECASE)

    # Convert printf to TO_CHAR for number formatting
    # printf('%.2f', col) -> TO_CHAR(col, '99999999.99')
    def convert_printf(match):
        format_str = match.group(1)
        col = match.group(2)
        # Simple conversion for common formats
        if '.2f' in format_str:
            return f"TO_CHAR({col}, 'FM99999999990.00')"
        elif '.1f' in format_str:
            return f"TO_CHAR({col}, 'FM99999999990.0')"
        elif '%d' in format_str or '%i' in format_str:
            return f"TO_CHAR({col}, 'FM99999999999')"
        return f"TO_CHAR({col})"

    oracle_sql = re.sub(r"\bprintf\s*\(\s*'([^']+)'\s*,\s*([^)]+)\)", convert_printf, oracle_sql, flags=re.IGNORECASE)

    # Handle LIMIT and OFFSET - must be done last as it restructures the query
    # LIMIT n OFFSET m -> OFFSET m ROWS FETCH NEXT n ROWS ONLY
    # LIMIT n -> FETCH FIRST n ROWS ONLY

    # Check for LIMIT with OFFSET
    limit_offset_match = re.search(r'\bLIMIT\s+(\d+)\s+OFFSET\s+(\d+)\s*$', oracle_sql, re.IGNORECASE)
    if limit_offset_match:
        limit_val = limit_offset_match.group(1)
        offset_val = limit_offset_match.group(2)
        oracle_sql = re.sub(r'\bLIMIT\s+\d+\s+OFFSET\s+\d+\s*$',
                           f'OFFSET {offset_val} ROWS FETCH NEXT {limit_val} ROWS ONLY',
                           oracle_sql, flags=re.IGNORECASE)
    else:
        # Check for OFFSET before LIMIT (SQLite allows both orders)
        offset_limit_match = re.search(r'\bOFFSET\s+(\d+)\s+LIMIT\s+(\d+)\s*$', oracle_sql, re.IGNORECASE)
        if offset_limit_match:
            offset_val = offset_limit_match.group(1)
            limit_val = offset_limit_match.group(2)
            oracle_sql = re.sub(r'\bOFFSET\s+\d+\s+LIMIT\s+\d+\s*$',
                               f'OFFSET {offset_val} ROWS FETCH NEXT {limit_val} ROWS ONLY',
                               oracle_sql, flags=re.IGNORECASE)
        else:
            # Simple LIMIT without OFFSET
            limit_match = re.search(r'\bLIMIT\s+(\d+)\s*$', oracle_sql, re.IGNORECASE)
            if limit_match:
                limit_val = limit_match.group(1)
                oracle_sql = re.sub(r'\bLIMIT\s+\d+\s*$',
                                   f'FETCH FIRST {limit_val} ROWS ONLY',
                                   oracle_sql, flags=re.IGNORECASE)

    # Convert != to <> (both work in Oracle, but <> is more standard)
    # Actually, Oracle supports both, so this is optional
    # oracle_sql = oracle_sql.replace('!=', '<>')

    # Convert || for string concatenation (same in both SQLite and Oracle)
    # No change needed

    # Convert SUBSTR (same in both, but ensure proper case)
    # No change needed as Oracle supports SUBSTR

    return oracle_sql


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
    from_pattern = r'\bFROM\s+([`"\w]+)(?:\s+(?:AS\s+)?([`"\w]+))?'
    from_matches = re.findall(from_pattern, sql_normalized, re.IGNORECASE)
    for match in from_matches:
        table_name = match[0].strip('`"')
        alias = match[1].strip('`"') if match[1] else None
        if table_name.upper() not in SQL_KEYWORDS:
            if table_name not in tables:
                tables.append(table_name)
            if alias:
                alias_to_table[alias.upper()] = table_name

    # Pattern for JOIN clauses
    join_pattern = r'\bJOIN\s+([`"\w]+)(?:\s+(?:AS\s+)?([`"\w]+))?'
    join_matches = re.findall(join_pattern, sql_normalized, re.IGNORECASE)
    for match in join_matches:
        table_name = match[0].strip('`"')
        alias = match[1].strip('`"') if match[1] else None
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
            match = re.match(r'([`"\w]+)(?:\s+(?:AS\s+)?([`"\w]+))?', part, re.IGNORECASE)
            if match:
                table_name = match.group(1).strip('`"')
                alias = match.group(2).strip('`"') if match.group(2) else None
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


def _extract_json_object(text: str) -> Dict:
    """Extract a JSON object from raw LLM text output."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find('{')
    end = text.rfind('}')
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in LLM response")
    return json.loads(text[start:end + 1])


def _normalize_llm_table_payload(payload: Dict) -> List[Dict]:
    """Normalize/clean LLM JSON payload to expected tables schema."""
    tables = payload.get("tables", [])
    cleaned = []
    for table in tables:
        name = str(table.get("name", "")).strip('`" ')
        if not name:
            continue
        cols = []
        for col in table.get("columns", []):
            col_name = str(col.get("name", "")).strip('`" ')
            if col_name and col_name.upper() not in SQL_KEYWORDS:
                cols.append({"name": col_name})
        cleaned.append({"name": name, "columns": cols})
    return cleaned


def extract_tables_with_columns_llm_openai_compat(sql: str, model: str, api_key: Optional[str], base_url: Optional[str]) -> List[Dict]:
    """Extract tables/columns using an OpenAI-compatible LLM endpoint."""
    if OpenAI is None:
        raise RuntimeError("openai package is not installed; install it or use --method rule_based")

    client_kwargs = {}
    if api_key:
        client_kwargs["api_key"] = api_key
    if base_url:
        client_kwargs["base_url"] = base_url
    client = OpenAI(**client_kwargs)

    prompt = (
        "Extract table names and corresponding column names from the SQL query. "
        "Return strict JSON with this schema: "
        "{\"tables\":[{\"name\":\"table_name\",\"columns\":[{\"name\":\"column_name\"}]}]}. "
        "Do not include extra keys or commentary. SQL:\n"
        f"{sql}"
    )

    response = client.responses.create(
        model=model,
        input=prompt,
        temperature=0,
    )

    parsed = _extract_json_object(response.output_text)
    return _normalize_llm_table_payload(parsed)


def extract_tables_with_columns_llm_ollama(sql: str, model: str, base_url: Optional[str]) -> List[Dict]:
    """Extract tables/columns using a local Ollama server (open-source models)."""
    endpoint = (base_url or "http://localhost:11434").rstrip('/') + "/api/generate"
    prompt = (
        "Extract table names and corresponding column names from the SQL query. "
        "Return strict JSON with this schema: "
        "{\"tables\":[{\"name\":\"table_name\",\"columns\":[{\"name\":\"column_name\"}]}]}. "
        "Do not include extra keys or commentary. SQL:\n"
        f"{sql}"
    )
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
    }).encode("utf-8")
    req = request.Request(endpoint, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except error.URLError as exc:
        raise RuntimeError(f"Ollama request failed: {exc}") from exc

    parsed = _extract_json_object(body.get("response", ""))
    return _normalize_llm_table_payload(parsed)


def process_dev_file(
    input_path: str,
    output_path: str,
    method: str = "rule_based",
    llm_model: str = "gpt-4o-mini",
    llm_api_key: Optional[str] = None,
    llm_base_url: Optional[str] = None,
    llm_provider: str = "openai_compat",
) -> None:
    """
    Process the dev.json file and add tables with nested columns metadata
    and Oracle SQL conversion.

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

        # Extract tables and columns
        if method == "llm":
            try:
                if llm_provider == "ollama":
                    tables_with_columns = extract_tables_with_columns_llm_ollama(
                        sql,
                        model=llm_model,
                        base_url=llm_base_url,
                    )
                else:
                    tables_with_columns = extract_tables_with_columns_llm_openai_compat(
                        sql,
                        model=llm_model,
                        api_key=llm_api_key,
                        base_url=llm_base_url,
                    )
            except Exception as exc:
                print(f"Warning: LLM extraction failed for question index {i} ({exc}); falling back to rule_based")
                tables_with_columns = extract_tables_with_columns(sql)
        else:
            tables_with_columns = extract_tables_with_columns(sql)
        question['tables'] = tables_with_columns

        # Convert SQL to Oracle format
        oracle_sql = convert_sqlite_to_oracle_sql(sql)
        question['oracle_SQL'] = oracle_sql

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
    parser = argparse.ArgumentParser(
        description="Add tables/columns metadata and Oracle SQL conversion to BIRD dev questions."
    )
    parser.add_argument("input_dev", help="Path to input dev.json")
    parser.add_argument("output_dev", nargs="?", help="Path to output file (defaults to input path)")
    parser.add_argument(
        "--method",
        choices=["rule_based", "llm"],
        default="rule_based",
        help="Table/column extraction strategy. llm uses an OpenAI-compatible endpoint.",
    )
    parser.add_argument("--llm-model", default="gpt-4o-mini", help="Model name for --method llm")
    parser.add_argument("--llm-api-key", default=None, help="API key for OpenAI-compatible endpoint")
    parser.add_argument("--llm-base-url", default=None, help="Base URL for OpenAI-compatible endpoint")
    parser.add_argument(
        "--llm-provider",
        choices=["openai_compat", "ollama"],
        default="openai_compat",
        help="LLM backend for --method llm. Use ollama for local open-source models.",
    )
    args = parser.parse_args()

    output_path = args.output_dev if args.output_dev else args.input_dev
    process_dev_file(
        args.input_dev,
        output_path,
        method=args.method,
        llm_model=args.llm_model,
        llm_api_key=args.llm_api_key,
        llm_base_url=args.llm_base_url,
        llm_provider=args.llm_provider,
    )


if __name__ == "__main__":
    main()
