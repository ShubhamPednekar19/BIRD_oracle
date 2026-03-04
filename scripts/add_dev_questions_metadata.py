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
import os
import re
from typing import List, Dict, Set, Tuple, Optional
from collections import defaultdict
from urllib import request, error

try:
    from groq import Groq
except ImportError:  # Optional dependency for --llm-provider groq
    Groq = None
try:
    import oci
except ImportError:  # Optional dependency for --llm-provider oci
    oci = None

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
# Keywords that may legitimately appear as unquoted column names in BIRD schemas
# and should not be dropped during heuristic extraction.
NON_FILTERABLE_IDENTIFIER_KEYWORDS = {
    'POWER',
}


# Keywords that may legitimately appear as unquoted table names in BIRD schemas.
NON_FILTERABLE_TABLE_KEYWORDS = {
    'MATCH',
    'ORDER',
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
        if table_name.upper() not in SQL_KEYWORDS or table_name.upper() in NON_FILTERABLE_TABLE_KEYWORDS:
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
        if table_name.upper() not in SQL_KEYWORDS or table_name.upper() in NON_FILTERABLE_TABLE_KEYWORDS:
            if table_name not in tables:
                tables.append(table_name)
            if alias:
                alias_to_table[alias.upper()] = table_name

    # Handle comma-separated tables in FROM clause
    from_clause_match = re.search(
        r'\bFROM\s+(.*?)(?:\bWHERE\b|\bJOIN\b|\bORDER\s+BY\b|\bGROUP\s+BY\b|\bLIMIT\b|\bHAVING\b|$)',
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
                if table_name.upper() not in SQL_KEYWORDS or table_name.upper() in NON_FILTERABLE_TABLE_KEYWORDS:
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
        (r'\bWHERE\s+(?:\w+\.)?(\w+)\s*(?:=|!=|<>|>=|<=|>|<|LIKE|IN|IS|BETWEEN)', 'where'),
        (r'\bORDER\s+BY\s+(?:\w+\.)?(\w+)', 'order'),
        (r'\bGROUP\s+BY\s+(?:\w+\.)?(\w+)', 'group'),
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

    # For single-table queries, recover identifiers across the full SQL expression.
    # This captures columns used in SELECT/WHERE/ORDER BY (e.g., DISTINCT availability,
    # power LIKE ..., promoTypes = ..., COUNT(id), etc.).
    if len(tables) == 1:
        single_table = tables[0]
        # Keep quoted identifiers out of token-based fallback extraction so pieces of
        # names like `County Name` or `Free Meal Count (K-12)` do not become spurious
        # columns such as County/Name/Free/Meal/K.
        scrubbed_sql = re.sub(r"'[^']*'", " ", sql_normalized)
        scrubbed_sql = re.sub(r'`[^`]+`|"[^"]+"', ' ', scrubbed_sql)
        # Skip aliases introduced with AS (e.g., SELECT ... AS atom_id1) so derived
        # labels are not treated as physical columns.
        as_aliases = {
            alias.strip('`"').upper()
            for alias in re.findall(r'\bAS\s+([`"\w]+)', sql_normalized, re.IGNORECASE)
        }
        tokens = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', scrubbed_sql)
        for token in tokens:
            upper_token = token.upper()
            if upper_token in SQL_KEYWORDS and upper_token not in NON_FILTERABLE_IDENTIFIER_KEYWORDS:
                continue
            if token == single_table or upper_token == single_table.upper():
                continue
            if upper_token in alias_to_table:
                continue
            if upper_token in as_aliases:
                continue
            # Skip function names (identifier followed by opening parenthesis)
            if re.search(rf'\b{re.escape(token)}\s*\(', scrubbed_sql):
                continue
            table_columns[single_table].add(token)

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
            if (col.upper() not in SQL_KEYWORDS or col.upper() in NON_FILTERABLE_IDENTIFIER_KEYWORDS)
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
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = text.find('{')
    end = text.rfind('}')
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in LLM response")
    parsed = json.loads(text[start:end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("LLM response JSON is not an object")
    return parsed


def _normalize_llm_table_payload(payload: Dict) -> List[Dict]:
    """Normalize/clean LLM JSON payload to expected tables schema."""
    tables = payload.get("tables", [])
    cleaned = []
    for table in tables:
        if not isinstance(table, dict):
            continue
        name = str(table.get("name", "")).strip('`" ')
        if "." in name:
            name = name.split(".")[-1]
        if not name:
            continue
        cols = []
        for col in table.get("columns", []):
            if not isinstance(col, dict):
                continue
            col_name = str(col.get("name", "")).strip('`" ')
            if col_name and col_name.upper() not in SQL_KEYWORDS:
                cols.append({"name": col_name})
        cleaned.append({"name": name, "columns": cols})
    return cleaned


def _build_batched_sql_prompt(sql_items: List[Tuple[int, str]]) -> Tuple[str, str]:
    """Build system/user prompts for batched SQL extraction."""
    instructions = (
        "You extract table and column metadata from SQL queries. "
        "Return strict JSON only with this schema: "
        "{\"items\":[{\"index\":0,\"tables\":[{\"name\":\"table_name\",\"columns\":[{\"name\":\"column_name\"}]}]}]}. "
        "The index must match the provided item index. "
        "Use unqualified table names only (no schema/database prefix). "
        "Do not include markdown fences, comments, or extra text. "
        "Return a single JSON object and nothing else."
    )

    lines = ["SQL items:"]
    for idx, sql in sql_items:
        lines.append(f"Index {idx}:")
        lines.append(sql)
        lines.append("---")
    return instructions, "\n".join(lines)


def _collect_text_candidates(value) -> List[str]:
    """Collect all string candidates from a nested response object."""
    candidates: List[str] = []
    if isinstance(value, str):
        candidates.append(value)
        return candidates
    if isinstance(value, (list, tuple)):
        for item in value:
            candidates.extend(_collect_text_candidates(item))
        return candidates
    if isinstance(value, dict):
        for item in value.values():
            candidates.extend(_collect_text_candidates(item))
        return candidates
    if hasattr(value, "__dict__"):
        for item in vars(value).values():
            candidates.extend(_collect_text_candidates(item))
    return candidates


def _extract_json_from_response(response_obj) -> Dict:
    """Find and parse the first JSON object in a response object."""
    for candidate in _collect_text_candidates(response_obj):
        try:
            parsed = _extract_json_object(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue
    raise RuntimeError("Unable to locate JSON object content in LLM response")


def _coerce_llm_items(parsed: Dict, sql_items: List[Tuple[int, str]]) -> List[Dict]:
    """Return standardized items list from LLM JSON payload."""
    items = parsed.get("items")
    if isinstance(items, list):
        return items
    tables = parsed.get("tables")
    if tables is not None:
        if len(sql_items) != 1:
            raise RuntimeError("LLM response missing items for batched request")
        return [{"index": sql_items[0][0], "tables": tables}]
    raise RuntimeError("LLM response missing items/tables")


def _extract_total_tokens(value) -> Optional[int]:
    """Extract total token count from known response shapes."""
    if value is None:
        return None
    if isinstance(value, dict):
        usage = value.get("usage")
        if isinstance(usage, dict):
            total = usage.get("total_tokens")
            if isinstance(total, int):
                return total
        if "total_tokens" in value and isinstance(value.get("total_tokens"), int):
            return value.get("total_tokens")
        return None
    usage = getattr(value, "usage", None)
    if usage is not None:
        total = getattr(usage, "total_tokens", None)
        if isinstance(total, int):
            return total
        if isinstance(usage, dict):
            total = usage.get("total_tokens")
            if isinstance(total, int):
                return total
    total = getattr(value, "total_tokens", None)
    if isinstance(total, int):
        return total
    return None



def extract_tables_with_columns_llm_groq_batch(
    sql_items: List[Tuple[int, str]],
    model: str,
    api_key: str,
    return_usage: bool = False,
) -> Dict[int, List[Dict]]:
    """Extract tables/columns for multiple SQL queries via the Groq Python SDK."""
    if Groq is None:
        raise RuntimeError("groq package is not installed; install it or use --llm-provider openrouter/openai_compat")

    instructions, user_prompt = _build_batched_sql_prompt(sql_items)
    client = Groq(api_key=api_key)
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": instructions},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
    )

    try:
        content = completion.choices[0].message.content
    except (AttributeError, IndexError, TypeError) as exc:
        raise RuntimeError("Unexpected Groq response shape") from exc

    parsed = _extract_json_object(content)
    items = _coerce_llm_items(parsed, sql_items)
    result: Dict[int, List[Dict]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("index"))
        except (TypeError, ValueError):
            continue
        result[idx] = _normalize_llm_table_payload({"tables": item.get("tables", [])})
    if return_usage:
        return result, _extract_total_tokens(completion)
    return result



def extract_tables_with_columns_llm_chat_completions_batch(
    sql_items: List[Tuple[int, str]],
    model: str,
    api_key: Optional[str],
    base_url: Optional[str],
    extra_headers: Optional[Dict[str, str]] = None,
    return_usage: bool = False,
) -> Dict[int, List[Dict]]:
    """Extract tables/columns for multiple SQL queries via HTTP chat-completions-compatible APIs (OpenAI/OpenRouter)."""
    endpoint = (base_url or "https://api.openai.com/v1").rstrip('/') + "/chat/completions"

    instructions, user_prompt = _build_batched_sql_prompt(sql_items)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
    }

    headers = {
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if extra_headers:
        headers.update(extra_headers)

    req = request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except error.URLError as exc:
        raise RuntimeError(f"OpenAI-compatible request failed: {exc}") from exc

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected chat completion response shape: {body}") from exc

    parsed = _extract_json_from_response(content)
    items = _coerce_llm_items(parsed, sql_items)
    result: Dict[int, List[Dict]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("index"))
        except (TypeError, ValueError):
            continue
        result[idx] = _normalize_llm_table_payload({"tables": item.get("tables", [])})
    if return_usage:
        return result, _extract_total_tokens(body)
    return result


def extract_tables_with_columns_llm_oci_batch(
    sql_items: List[Tuple[int, str]],
    compartment_id: str,
    model_id: str,
    endpoint: str,
    config_profile: str = "DEFAULT",
    config_file: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: int = 600,
    top_p: float = 0.75,
    return_usage: bool = False,
) -> Dict[int, List[Dict]]:
    """Extract tables/columns for multiple SQL queries via OCI Generative AI SDK."""
    if oci is None:
        raise RuntimeError("oci package is not installed; install it or use --llm-provider openai_compat/openrouter/groq/ollama")

    instructions, user_prompt = _build_batched_sql_prompt(sql_items)
    prompt = f"{instructions}\n\n{user_prompt}"

    if config_file:
        config = oci.config.from_file(config_file, config_profile)
    else:
        config = oci.config.from_file("~/.oci/config", config_profile)

    client = oci.generative_ai_inference.GenerativeAiInferenceClient(
        config=config,
        service_endpoint=endpoint,
        retry_strategy=oci.retry.NoneRetryStrategy(),
        timeout=(10, 240),
    )

    content = oci.generative_ai_inference.models.TextContent()
    content.text = prompt

    message = oci.generative_ai_inference.models.Message()
    message.role = "USER"
    message.content = [content]

    chat_request = oci.generative_ai_inference.models.GenericChatRequest()
    chat_request.api_format = oci.generative_ai_inference.models.BaseChatRequest.API_FORMAT_GENERIC
    chat_request.messages = [message]
    chat_request.max_tokens = max_tokens
    chat_request.temperature = temperature
    chat_request.top_p = top_p
    chat_request.frequency_penalty = 0
    chat_request.presence_penalty = 0

    chat_detail = oci.generative_ai_inference.models.ChatDetails()
    chat_detail.serving_mode = oci.generative_ai_inference.models.OnDemandServingMode(model_id=model_id)
    chat_detail.chat_request = chat_request
    chat_detail.compartment_id = compartment_id

    chat_response = client.chat(chat_detail)
    parsed = _extract_json_from_response(chat_response)
    items = _coerce_llm_items(parsed, sql_items)
    result: Dict[int, List[Dict]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("index"))
        except (TypeError, ValueError):
            continue
        result[idx] = _normalize_llm_table_payload({"tables": item.get("tables", [])})
    if return_usage:
        return result, _extract_total_tokens(chat_response)
    return result



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


def _retry_llm_single_items(
    sql_items: List[Tuple[int, str]],
    llm_provider: str,
    llm_model: str,
    llm_api_key: Optional[str],
    llm_base_url: Optional[str],
    extra_headers: Optional[Dict[str, str]],
    oci_compartment_id: Optional[str],
    oci_model_id: Optional[str],
    oci_endpoint: Optional[str],
    oci_config_profile: str,
    oci_config_file: Optional[str],
    oci_temperature: float,
    oci_max_tokens: int,
    oci_top_p: float,
) -> Dict[int, List[Dict]]:
    """Retry LLM extraction one item at a time after batch parsing failures."""
    result: Dict[int, List[Dict]] = {}
    for idx, sql in sql_items:
        try:
            if llm_provider == "oci":
                if not (oci_compartment_id and oci_model_id and oci_endpoint):
                    continue
                single = extract_tables_with_columns_llm_oci_batch(
                    [(idx, sql)],
                    compartment_id=oci_compartment_id,
                    model_id=oci_model_id,
                    endpoint=oci_endpoint,
                    config_profile=oci_config_profile,
                    config_file=oci_config_file,
                    temperature=oci_temperature,
                    max_tokens=oci_max_tokens,
                    top_p=oci_top_p,
                )
            elif llm_provider == "groq":
                if not llm_api_key:
                    continue
                single = extract_tables_with_columns_llm_groq_batch(
                    [(idx, sql)],
                    model=llm_model,
                    api_key=llm_api_key,
                )
            else:
                single = extract_tables_with_columns_llm_chat_completions_batch(
                    [(idx, sql)],
                    model=llm_model,
                    api_key=llm_api_key,
                    base_url=llm_base_url,
                    extra_headers=extra_headers or None,
                )
        except Exception:
            continue
        if idx in single:
            result[idx] = single[idx]
    return result


def process_dev_file(
    input_path: str,
    output_path: str,
    method: str = "rule_based",
    llm_model: str = "gpt-4o-mini",
    llm_api_key: Optional[str] = None,
    llm_base_url: Optional[str] = None,
    llm_provider: str = "openai_compat",
    llm_site_url: Optional[str] = None,
    llm_app_name: Optional[str] = None,
    llm_batch_size: int = 1,
    oci_compartment_id: Optional[str] = None,
    oci_model_id: Optional[str] = None,
    oci_endpoint: Optional[str] = None,
    oci_config_profile: str = "DEFAULT",
    oci_config_file: Optional[str] = None,
    oci_temperature: float = 0.0,
    oci_max_tokens: int = 600,
    oci_top_p: float = 0.75,
    output_format: str = "json",
    limit: Optional[int] = None,
) -> None:
    """
    Process the dev.json file and add tables with nested columns metadata
    and Oracle SQL conversion.

    Args:
        input_path: Path to input dev.json file
        output_path: Path to output file with added metadata
    """
    print(f"Reading input file: {input_path}")

    input_is_jsonl = input_path.lower().endswith(".jsonl")
    if input_is_jsonl:
        questions = []
        with open(input_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                questions.append(json.loads(line))
    else:
        with open(input_path, 'r', encoding='utf-8') as f:
            questions = json.load(f)

    # Normalize common JSONL fields to the expected schema
    for idx, question in enumerate(questions):
        if 'SQL' not in question and 'query' in question:
            question['SQL'] = question['query']
        if 'db_id' not in question and 'database_name' in question:
            question['db_id'] = question['database_name']
        if 'question_id' not in question:
            question['question_id'] = idx

    if limit is not None:
        if limit < 0:
            raise ValueError("limit must be non-negative")
        questions = questions[:limit]

    print(f"Processing {len(questions)} questions...")

    for question in questions:
        question['tables'] = []

    total_questions = len(questions)
    def _print_progress(done: int) -> None:
        if total_questions == 0:
            return
        percent = (done / total_questions) * 100
        print(f"\rProgress: {done}/{total_questions} ({percent:.1f}%)", end="", flush=True)

    total_tokens_used = 0
    if method == "llm":
        if llm_provider == "ollama":
            for i, question in enumerate(questions):
                sql = question.get('SQL', '')
                try:
                    question['tables'] = extract_tables_with_columns_llm_ollama(
                        sql,
                        model=llm_model,
                        base_url=llm_base_url,
                    )
                except Exception as exc:
                    print(f"Warning: LLM extraction failed for question index {i} ({exc}); falling back to rule_based")
                    question['tables'] = extract_tables_with_columns(sql)
                _print_progress(i + 1)
        elif llm_provider == "oci":
            if not oci_compartment_id:
                raise RuntimeError("Missing OCI compartment id. Pass --oci-compartment-id.")
            if not oci_model_id:
                raise RuntimeError("Missing OCI model id. Pass --oci-model-id.")
            if not oci_endpoint:
                raise RuntimeError("Missing OCI endpoint. Pass --oci-endpoint.")
            batch_size = max(1, llm_batch_size)
            for batch_start in range(0, len(questions), batch_size):
                batch_end = min(batch_start + batch_size, len(questions))
                sql_items = [
                    (idx, questions[idx].get('SQL', ''))
                    for idx in range(batch_start, batch_end)
                ]
                try:
                    batch_result, batch_tokens = extract_tables_with_columns_llm_oci_batch(
                        sql_items,
                        compartment_id=oci_compartment_id,
                        model_id=oci_model_id,
                        endpoint=oci_endpoint,
                        config_profile=oci_config_profile,
                        config_file=oci_config_file,
                        temperature=oci_temperature,
                        max_tokens=oci_max_tokens,
                        top_p=oci_top_p,
                        return_usage=True,
                    )
                except Exception as exc:
                    print(
                        f"Warning: LLM batch extraction failed for indexes {batch_start}-{batch_end - 1} ({exc}); "
                        "retrying single-item LLM requests for this batch"
                    )
                    batch_tokens = None
                    if "missing items/tables" in str(exc).lower():
                        batch_result = _retry_llm_single_items(
                            sql_items,
                            llm_provider=llm_provider,
                            llm_model=llm_model,
                            llm_api_key=None,
                            llm_base_url=None,
                            extra_headers=None,
                            oci_compartment_id=oci_compartment_id,
                            oci_model_id=oci_model_id,
                            oci_endpoint=oci_endpoint,
                            oci_config_profile=oci_config_profile,
                            oci_config_file=oci_config_file,
                            oci_temperature=oci_temperature,
                            oci_max_tokens=oci_max_tokens,
                            oci_top_p=oci_top_p,
                        )
                    else:
                        batch_result = {}

                if batch_tokens is not None:
                    total_tokens_used += batch_tokens
                    print(f"\nLLM tokens used (batch {batch_start}-{batch_end - 1}): {batch_tokens}")

                for idx, sql in sql_items:
                    if idx in batch_result:
                        questions[idx]['tables'] = batch_result[idx]
                    else:
                        questions[idx]['tables'] = extract_tables_with_columns(sql)

                _print_progress(batch_end)
        else:
            effective_api_key = llm_api_key
            effective_base_url = llm_base_url
            extra_headers: Dict[str, str] = {}

            if llm_provider == "openrouter":
                effective_api_key = effective_api_key or os.getenv("OPENROUTER_API_KEY")
                effective_base_url = effective_base_url or "https://openrouter.ai/api/v1"
                if not effective_api_key:
                    raise RuntimeError("Missing OpenRouter API key. Pass --llm-api-key or set OPENROUTER_API_KEY.")
                if llm_site_url:
                    extra_headers["HTTP-Referer"] = llm_site_url
                if llm_app_name:
                    extra_headers["X-Title"] = llm_app_name
            elif llm_provider == "groq":
                effective_api_key = effective_api_key or os.getenv("GROQ_API_KEY")
                effective_base_url = effective_base_url or "https://api.groq.com/openai/v1"
                if not effective_api_key:
                    raise RuntimeError("Missing Groq API key. Pass --llm-api-key or set GROQ_API_KEY.")
            else:
                effective_api_key = effective_api_key or os.getenv("OPENAI_API_KEY")

            batch_size = max(1, llm_batch_size)
            for batch_start in range(0, len(questions), batch_size):
                batch_end = min(batch_start + batch_size, len(questions))
                sql_items = [
                    (idx, questions[idx].get('SQL', ''))
                    for idx in range(batch_start, batch_end)
                ]
                try:
                    if llm_provider == "groq":
                        batch_result, batch_tokens = extract_tables_with_columns_llm_groq_batch(
                            sql_items,
                            model=llm_model,
                            api_key=effective_api_key,
                            return_usage=True,
                        )
                    else:
                        batch_result, batch_tokens = extract_tables_with_columns_llm_chat_completions_batch(
                            sql_items,
                            model=llm_model,
                            api_key=effective_api_key,
                            base_url=effective_base_url,
                            extra_headers=extra_headers or None,
                            return_usage=True,
                        )
                except Exception as exc:
                    print(
                        f"Warning: LLM batch extraction failed for indexes {batch_start}-{batch_end - 1} ({exc}); "
                        "retrying single-item LLM requests for this batch"
                    )
                    batch_tokens = None
                    if "missing items/tables" in str(exc).lower():
                        batch_result = _retry_llm_single_items(
                            sql_items,
                            llm_provider=llm_provider,
                            llm_model=llm_model,
                            llm_api_key=effective_api_key,
                            llm_base_url=effective_base_url,
                            extra_headers=extra_headers,
                            oci_compartment_id=None,
                            oci_model_id=None,
                            oci_endpoint=None,
                            oci_config_profile="DEFAULT",
                            oci_config_file=None,
                            oci_temperature=0.0,
                            oci_max_tokens=0,
                            oci_top_p=0.0,
                        )
                    else:
                        batch_result = {}

                if batch_tokens is not None:
                    total_tokens_used += batch_tokens
                    print(f"\nLLM tokens used (batch {batch_start}-{batch_end - 1}): {batch_tokens}")

                for idx, sql in sql_items:
                    if idx in batch_result:
                        questions[idx]['tables'] = batch_result[idx]
                    else:
                        questions[idx]['tables'] = extract_tables_with_columns(sql)

                _print_progress(batch_end)
    else:
        for i, question in enumerate(questions):
            sql = question.get('SQL', '')
            question['tables'] = extract_tables_with_columns(sql)
            _print_progress(i + 1)

    if total_questions > 0:
        print()
    if total_tokens_used > 0:
        print(f"Total LLM tokens used: {total_tokens_used}")

    for question in questions:
        question.pop('oracle_SQL', None)
        question.pop('difficulty', None)

    print(f"Writing output file: {output_path}")
    if output_format == "jsonl":
        with open(output_path, 'w', encoding='utf-8') as f:
            for item in questions:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
    else:
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


def run_llm_test(
    sql: str,
    llm_model: str,
    llm_api_key: Optional[str],
    llm_base_url: Optional[str],
    llm_provider: str,
    llm_site_url: Optional[str],
    llm_app_name: Optional[str],
    oci_compartment_id: Optional[str],
    oci_model_id: Optional[str],
    oci_endpoint: Optional[str],
    oci_config_profile: str,
    oci_config_file: Optional[str],
    oci_temperature: float,
    oci_max_tokens: int,
    oci_top_p: float,
) -> None:
    """Run a single LLM extraction to validate pipeline wiring."""
    print("Running LLM test mode...")
    print(f"Provider: {llm_provider}")
    print(f"SQL:\n{sql}")

    if llm_provider == "ollama":
        tables = extract_tables_with_columns_llm_ollama(
            sql,
            model=llm_model,
            base_url=llm_base_url,
        )
        payload = {
            "question_id": 0,
            "db_id": "test_db",
            "question": "test",
            "evidence": "",
            "SQL": sql,
            "tables": tables,
        }
        print("\nFull question object:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        print("\nTotal tokens: 0")
        return

    if llm_provider == "oci":
        if not oci_compartment_id:
            raise RuntimeError("Missing OCI compartment id. Pass --oci-compartment-id.")
        if not oci_model_id:
            raise RuntimeError("Missing OCI model id. Pass --oci-model-id.")
        if not oci_endpoint:
            raise RuntimeError("Missing OCI endpoint. Pass --oci-endpoint.")
        sql_items = [(0, sql)]
        result, total_tokens = extract_tables_with_columns_llm_oci_batch(
            sql_items,
            compartment_id=oci_compartment_id,
            model_id=oci_model_id,
            endpoint=oci_endpoint,
            config_profile=oci_config_profile,
            config_file=oci_config_file,
            temperature=oci_temperature,
            max_tokens=oci_max_tokens,
            top_p=oci_top_p,
            return_usage=True,
        )
        tables = result.get(0, [])
        payload = {
            "question_id": 0,
            "db_id": "test_db",
            "question": "test",
            "evidence": "",
            "SQL": sql,
            "tables": tables,
        }
        print("\nFull question object:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        if total_tokens is not None:
            print(f"\nTotal tokens: {total_tokens}")
        return

    effective_api_key = llm_api_key
    effective_base_url = llm_base_url
    extra_headers: Dict[str, str] = {}

    if llm_provider == "openrouter":
        effective_api_key = effective_api_key or os.getenv("OPENROUTER_API_KEY")
        effective_base_url = effective_base_url or "https://openrouter.ai/api/v1"
        if not effective_api_key:
            raise RuntimeError("Missing OpenRouter API key. Pass --llm-api-key or set OPENROUTER_API_KEY.")
        if llm_site_url:
            extra_headers["HTTP-Referer"] = llm_site_url
        if llm_app_name:
            extra_headers["X-Title"] = llm_app_name
    elif llm_provider == "groq":
        effective_api_key = effective_api_key or os.getenv("GROQ_API_KEY")
        effective_base_url = effective_base_url or "https://api.groq.com/openai/v1"
        if not effective_api_key:
            raise RuntimeError("Missing Groq API key. Pass --llm-api-key or set GROQ_API_KEY.")
    else:
        effective_api_key = effective_api_key or os.getenv("OPENAI_API_KEY")

    sql_items = [(0, sql)]
    if llm_provider == "groq":
        result, total_tokens = extract_tables_with_columns_llm_groq_batch(
            sql_items,
            model=llm_model,
            api_key=effective_api_key,
            return_usage=True,
        )
    else:
        result, total_tokens = extract_tables_with_columns_llm_chat_completions_batch(
            sql_items,
            model=llm_model,
            api_key=effective_api_key,
            base_url=effective_base_url,
            extra_headers=extra_headers or None,
            return_usage=True,
        )

    tables = result.get(0, [])
    payload = {
        "question_id": 0,
        "db_id": "test_db",
        "question": "test",
        "evidence": "",
        "SQL": sql,
        "tables": tables,
    }

    print("\nFull question object:")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    if total_tokens is not None:
        print(f"\nTotal tokens: {total_tokens}")



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
        choices=["openai_compat", "openrouter", "groq", "ollama", "oci"],
        default="openai_compat",
        help="LLM backend for --method llm. Supports openai_compat, openrouter, groq, ollama, and oci.",
    )
    parser.add_argument(
        "--llm-site-url",
        default=None,
        help="Optional site URL for OpenRouter HTTP-Referer header.",
    )
    parser.add_argument(
        "--llm-app-name",
        default=None,
        help="Optional app name for OpenRouter X-Title header.",
    )
    parser.add_argument(
        "--llm-batch-size",
        type=int,
        default=1,
        help="Number of questions sent in one LLM request for OpenAI-compatible providers (default: 1).",
    )
    parser.add_argument("--oci-compartment-id", default=None, help="OCI compartment OCID for Generative AI.")
    parser.add_argument("--oci-model-id", default=None, help="OCI model OCID for Generative AI.")
    parser.add_argument(
        "--oci-endpoint",
        default=None,
        help="OCI Generative AI inference endpoint, e.g. https://inference.generativeai.us-chicago-1.oci.oraclecloud.com",
    )
    parser.add_argument("--oci-config-profile", default="DEFAULT", help="OCI config profile name")
    parser.add_argument("--oci-config-file", default=None, help="OCI config file path (defaults to ~/.oci/config)")
    parser.add_argument("--oci-temperature", type=float, default=0.0, help="OCI LLM temperature")
    parser.add_argument("--oci-max-tokens", type=int, default=600, help="OCI LLM max tokens")
    parser.add_argument("--oci-top-p", type=float, default=0.75, help="OCI LLM top_p")
    parser.add_argument(
        "--output-format",
        choices=["json", "jsonl"],
        default="json",
        help="Output format (default: json).",
    )
    parser.add_argument("--test-llm", action="store_true", help="Run a single LLM extraction and exit.")
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Process only the first N questions (default: 20).",
    )
    parser.add_argument(
        "--test-limit",
        type=int,
        default=20,
        help="Number of questions to process in --test-mode (default: 20).",
    )
    parser.add_argument(
        "--test-sql",
        default="SELECT P.PERCENTAGE,\n       M.MAX_UNIVERSITY\nFROM (\n  SELECT CAST(SUM(CASE WHEN T2.SCORE > 80 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) AS PERCENTAGE\n  FROM UNIVERSITY.RANKING_CRITERIA T1\n  INNER JOIN UNIVERSITY.RANKING_YEAR T2 ON T1.ID = T2.RANKING_CRITERIA_ID\n  INNER JOIN UNIVERSITY.UNIVERSITY T3 ON T3.ID = T2.UNIVERSITY.ID\n  WHERE T1.CRITERIA_NAME = 'International'\n    AND T2.YEAR = 2016\n) P\nCROSS JOIN (\n  SELECT T3.UNIVERSITY.NAME AS MAX_UNIVERSITY\n  FROM UNIVERSITY.RANKING_CRITERIA T1\n  INNER JOIN UNIVERSITY.RANKING_YEAR T2 ON T1.ID = T2.RANKING_CRITERIA_ID\n  INNER JOIN UNIVERSITY.UNIVERSITY T3 ON T3.ID = T2.UNIVERSITY.ID\n  WHERE T1.CRITERIA_NAME = 'International'\n    AND T2.YEAR = 2016\n    AND T2.SCORE > 80\n  ORDER BY T2.SCORE DESC\n  FETCH FIRST 1 ROWS ONLY\n) M",
        help="SQL to use with --test-llm.",
    )
    args = parser.parse_args()

    output_path = args.output_dev if args.output_dev else args.input_dev
    if args.test_llm:
        run_llm_test(
            sql=args.test_sql,
            llm_model=args.llm_model,
            llm_api_key=args.llm_api_key,
            llm_base_url=args.llm_base_url,
            llm_provider=args.llm_provider,
            llm_site_url=args.llm_site_url,
            llm_app_name=args.llm_app_name,
            oci_compartment_id=args.oci_compartment_id,
            oci_model_id=args.oci_model_id,
            oci_endpoint=args.oci_endpoint,
            oci_config_profile=args.oci_config_profile,
            oci_config_file=args.oci_config_file,
            oci_temperature=args.oci_temperature,
            oci_max_tokens=args.oci_max_tokens,
            oci_top_p=args.oci_top_p,
        )
        return
    process_dev_file(
        args.input_dev,
        output_path,
        method=args.method,
        llm_model=args.llm_model,
        llm_api_key=args.llm_api_key,
        llm_base_url=args.llm_base_url,
        llm_provider=args.llm_provider,
        llm_site_url=args.llm_site_url,
        llm_app_name=args.llm_app_name,
        llm_batch_size=args.llm_batch_size,
        oci_compartment_id=args.oci_compartment_id,
        oci_model_id=args.oci_model_id,
        oci_endpoint=args.oci_endpoint,
        oci_config_profile=args.oci_config_profile,
        oci_config_file=args.oci_config_file,
        oci_temperature=args.oci_temperature,
        oci_max_tokens=args.oci_max_tokens,
        oci_top_p=args.oci_top_p,
        output_format=args.output_format,
        limit=args.test_limit if args.test_mode else None,
    )


if __name__ == "__main__":
    main()    
