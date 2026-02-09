#!/usr/bin/env python3
"""
Oracle Metadata Generator for BIRD Benchmark

This script extracts column descriptions and value descriptions from the
BIRD benchmark dataset CSV files and generates Oracle DDL statements for:
- COMMENT ON COLUMN: For column descriptions
- ALTER TABLE MODIFY ANNOTATIONS: For value descriptions

Usage:
    python generate_oracle_metadata.py -i <input_dir> -o <output_dir>
"""

import os
import csv
import re
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# Oracle reserved words that need to be quoted when used as identifiers
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


def needs_quoting(identifier: str) -> bool:
    """Check if an identifier needs to be quoted in Oracle."""
    if not identifier:
        return False
    upper_id = identifier.upper()
    # Quote if it's a reserved word, contains special chars, or starts with a digit
    if upper_id in ORACLE_RESERVED_WORDS:
        return True
    if not identifier[0].isalpha() and identifier[0] != '_':
        return True
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', identifier):
        return True
    return False


def quote_identifier(identifier: str) -> str:
    """Quote an identifier for Oracle if needed."""
    if not identifier:
        return identifier
    # Remove existing backticks or quotes
    identifier = identifier.strip('`"')

    if needs_quoting(identifier):
        # Escape any double quotes in the identifier
        identifier = identifier.replace('"', '""')
        return f'"{identifier}"'
    return identifier


def escape_sql_string(text: str) -> str:
    """Escape a string for use in SQL single quotes."""
    if not text:
        return text
    # Replace single quotes with two single quotes for SQL escaping
    return text.replace("'", "''")


def is_valid_description(desc: str) -> bool:
    """Check if a description is valid (non-empty and not just placeholders)."""
    if not desc:
        return False
    desc = desc.strip()
    if not desc:
        return False
    # Skip placeholder values
    if desc.lower() in ['', '<comment>', 'comment', 'null', 'none', 'n/a']:
        return False
    return True


def clean_description(desc: str) -> str:
    """Clean and format a description for SQL."""
    if not desc:
        return desc
    # Replace multiple whitespace/newlines with single space
    desc = ' '.join(desc.split())
    # Trim to reasonable length for Oracle (max 4000 chars for VARCHAR2)
    if len(desc) > 3900:
        desc = desc[:3900] + '...'
    return desc.strip()


def parse_csv_file(csv_path: str) -> List[Dict]:
    """Parse a CSV file and extract column metadata."""
    columns = []

    try:
        # Try different encodings
        encodings = ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']
        content = None

        for encoding in encodings:
            try:
                with open(csv_path, 'r', encoding=encoding) as f:
                    content = f.read()
                break
            except UnicodeDecodeError:
                continue

        if content is None:
            print(f"Warning: Could not decode {csv_path}")
            return columns

        # Parse CSV
        reader = csv.DictReader(content.splitlines())

        for row in reader:
            # Get column name - try different possible field names
            col_name = (
                row.get('original_column_name', '') or
                row.get('column_name', '') or
                ''
            ).strip()

            if not col_name:
                continue

            # Get descriptions
            col_desc = row.get('column_description', '').strip()
            value_desc = row.get('value_description', '').strip()

            columns.append({
                'column_name': col_name,
                'column_description': col_desc,
                'value_description': value_desc
            })

    except Exception as e:
        print(f"Error parsing {csv_path}: {e}")

    return columns


def generate_metadata_sql(db_name: str, table_name: str, columns: List[Dict]) -> List[str]:
    """Generate Oracle SQL statements for metadata."""
    statements = []

    quoted_table = quote_identifier(table_name)

    for col in columns:
        col_name = col['column_name']
        col_desc = col['column_description']
        value_desc = col['value_description']

        quoted_col = quote_identifier(col_name)

        # Generate COMMENT ON COLUMN if description is valid
        if is_valid_description(col_desc):
            clean_desc = clean_description(col_desc)
            escaped_desc = escape_sql_string(clean_desc)
            comment_sql = f"COMMENT ON COLUMN {quoted_table}.{quoted_col} IS '{escaped_desc}';"
            statements.append(comment_sql)

        # Generate ANNOTATION if value_description is valid
        if is_valid_description(value_desc):
            clean_value = clean_description(value_desc)
            escaped_value = escape_sql_string(clean_value)
            annotation_sql = f"ALTER TABLE {quoted_table} MODIFY ({quoted_col} ANNOTATIONS (ADD value_description '{escaped_value}'));"
            statements.append(annotation_sql)

    return statements


def process_database(db_path: str, output_dir: str) -> Tuple[bool, int]:
    """Process a single database and generate metadata SQL file."""
    db_name = os.path.basename(db_path)
    desc_dir = os.path.join(db_path, 'database_description')

    if not os.path.exists(desc_dir):
        print(f"  No database_description folder found for {db_name}")
        return False, 0

    all_statements = []
    all_statements.append(f"-- Oracle Metadata for {db_name}")
    all_statements.append(f"-- Generated from BIRD benchmark database_description CSVs")
    all_statements.append("")

    # Find all CSV files
    csv_files = sorted([f for f in os.listdir(desc_dir) if f.endswith('.csv')])

    if not csv_files:
        print(f"  No CSV files found in {desc_dir}")
        return False, 0

    total_statements = 0

    for csv_file in csv_files:
        csv_path = os.path.join(desc_dir, csv_file)
        table_name = os.path.splitext(csv_file)[0]

        columns = parse_csv_file(csv_path)

        if columns:
            statements = generate_metadata_sql(db_name, table_name, columns)

            if statements:
                all_statements.append(f"-- Table: {table_name}")
                all_statements.extend(statements)
                all_statements.append("")
                total_statements += len(statements)

    if total_statements > 0:
        # Write output file
        output_path = os.path.join(output_dir, db_name, f"{db_name}_metadata.sql")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(all_statements))

        return True, total_statements

    return False, 0


def main():
    parser = argparse.ArgumentParser(
        description='Generate Oracle metadata SQL from BIRD benchmark CSVs'
    )
    parser.add_argument(
        '--input-dir', '-i',
        default='/tmp/dev_20240627/dev_databases',
        help='Input directory containing database folders with database_description CSVs'
    )
    parser.add_argument(
        '--output-dir', '-o',
        default='oracle_ddl',
        help='Output directory for Oracle metadata SQL files'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Print verbose output'
    )

    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if not input_dir.exists():
        print(f"Error: Input directory '{input_dir}' does not exist")
        return 1

    # Find all database folders (those with database_description subdirectory)
    db_folders = []
    for item in sorted(input_dir.iterdir()):
        if item.is_dir() and (item / 'database_description').exists():
            db_folders.append(item)

    if not db_folders:
        print(f"No database folders with database_description found in '{input_dir}'")
        return 1

    print(f"Found {len(db_folders)} databases with metadata")

    success_count = 0
    total_statements = 0

    for db_folder in db_folders:
        db_name = db_folder.name

        if args.verbose:
            print(f"Processing: {db_name}")

        success, stmt_count = process_database(str(db_folder), str(output_dir))

        if success:
            success_count += 1
            total_statements += stmt_count
            print(f"[OK] {db_name} ({stmt_count} statements)")
        else:
            print(f"[SKIP] {db_name} (no metadata generated)")

    print(f"\nMetadata generation complete: {success_count} databases, {total_statements} total statements")
    return 0


if __name__ == '__main__':
    exit(main())
