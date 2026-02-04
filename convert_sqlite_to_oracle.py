#!/usr/bin/env python3
"""
SQLite to Oracle DDL Converter

This script converts SQLite DDL schemas from the BIRD benchmark dataset
to Oracle DDL format. It handles:
- Data type conversions (TEXT → VARCHAR2, INTEGER → NUMBER, etc.)
- Reserved word quoting
- Column names with special characters
- Primary key with AUTOINCREMENT → GENERATED ALWAYS AS IDENTITY
- Foreign key constraints
- Removal of SQLite-specific syntax (IF NOT EXISTS, etc.)
"""

import os
import re
import sqlite3
import argparse
from pathlib import Path
from typing import List, Tuple, Dict, Optional


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
    # Remove existing backticks or quotes
    identifier = identifier.strip('`"')

    if needs_quoting(identifier):
        # Escape any double quotes in the identifier
        identifier = identifier.replace('"', '""')
        return f'"{identifier}"'
    return identifier


def convert_data_type(sqlite_type: str, column_name: str = "") -> str:
    """Convert SQLite data type to Oracle data type."""
    if not sqlite_type:
        return "VARCHAR2(4000)"

    sqlite_type = sqlite_type.upper().strip()

    # Handle compound types like VARCHAR(255)
    size_match = re.match(r'(\w+)\s*\(\s*(\d+)\s*(?:,\s*(\d+))?\s*\)', sqlite_type)
    if size_match:
        base_type = size_match.group(1)
        size = int(size_match.group(2))
        scale = size_match.group(3)

        if base_type in ('VARCHAR', 'CHAR', 'CHARACTER', 'VARYING'):
            if size > 4000:
                return "CLOB"
            return f"VARCHAR2({size})"
        elif base_type in ('NUMERIC', 'DECIMAL'):
            if scale:
                return f"NUMBER({size},{scale})"
            return f"NUMBER({size})"
        elif base_type in ('FLOAT', 'DOUBLE'):
            return "NUMBER"

    # Map SQLite types to Oracle types
    type_mapping = {
        'TEXT': 'VARCHAR2(4000)',
        'VARCHAR': 'VARCHAR2(4000)',
        'CHAR': 'VARCHAR2(4000)',
        'CHARACTER': 'VARCHAR2(4000)',
        'CLOB': 'CLOB',
        'NVARCHAR': 'NVARCHAR2(4000)',
        'NCHAR': 'NCHAR(4000)',
        'INTEGER': 'NUMBER',
        'INT': 'NUMBER',
        'SMALLINT': 'NUMBER',
        'MEDIUMINT': 'NUMBER',
        'BIGINT': 'NUMBER',
        'TINYINT': 'NUMBER',
        'UNSIGNED BIG INT': 'NUMBER',
        'INT2': 'NUMBER',
        'INT8': 'NUMBER',
        'REAL': 'NUMBER',
        'DOUBLE': 'NUMBER',
        'DOUBLE PRECISION': 'NUMBER',
        'FLOAT': 'NUMBER',
        'NUMERIC': 'NUMBER',
        'DECIMAL': 'NUMBER',
        'BOOLEAN': 'NUMBER(1)',
        'DATE': 'DATE',
        'DATETIME': 'TIMESTAMP',
        'TIMESTAMP': 'TIMESTAMP',
        'TIME': 'TIMESTAMP',
        'BLOB': 'BLOB',
        'NONE': 'VARCHAR2(4000)',
    }

    return type_mapping.get(sqlite_type, 'VARCHAR2(4000)')


def parse_column_def(col_def: str) -> Optional[Dict]:
    """Parse a column definition and extract its components."""
    col_def = col_def.strip()

    # Skip comments
    if col_def.startswith('--') or not col_def:
        return None

    # Handle inline primary key autoincrement
    is_pk = False
    is_autoincrement = False
    is_unique = False
    is_not_null = False
    default_value = None
    references = None

    # Extract column name (may be quoted)
    if col_def.startswith('`') or col_def.startswith('"'):
        quote_char = col_def[0]
        end_quote = col_def.find(quote_char, 1)
        col_name = col_def[1:end_quote]
        rest = col_def[end_quote + 1:].strip()
    else:
        parts = col_def.split(None, 1)
        col_name = parts[0]
        rest = parts[1] if len(parts) > 1 else ""

    # Extract data type
    data_type = ""
    if rest:
        # Find the data type (first word or word with parentheses)
        type_match = re.match(r'^(\w+(?:\s*\([^)]*\))?)', rest, re.IGNORECASE)
        if type_match:
            data_type = type_match.group(1)
            rest = rest[type_match.end():].strip()

    # Parse constraints
    rest_upper = rest.upper()

    if 'PRIMARY KEY' in rest_upper:
        is_pk = True
    if 'AUTOINCREMENT' in rest_upper:
        is_autoincrement = True
    if 'UNIQUE' in rest_upper and 'PRIMARY KEY' not in rest_upper:
        is_unique = True
    if 'NOT NULL' in rest_upper:
        is_not_null = True

    # Extract DEFAULT value
    default_match = re.search(r'DEFAULT\s+(\S+|\'[^\']*\'|\"[^\"]*\")', rest, re.IGNORECASE)
    if default_match:
        default_value = default_match.group(1)
        # Handle NULL default
        if default_value.upper() == 'NULL':
            default_value = 'NULL'

    # Extract REFERENCES
    ref_match = re.search(r'REFERENCES\s+[`"]?(\w+)[`"]?\s*\(\s*[`"]?(\w+)[`"]?\s*\)', rest, re.IGNORECASE)
    if ref_match:
        references = {
            'table': ref_match.group(1),
            'column': ref_match.group(2)
        }

    return {
        'name': col_name,
        'data_type': data_type,
        'is_pk': is_pk,
        'is_autoincrement': is_autoincrement,
        'is_unique': is_unique,
        'is_not_null': is_not_null,
        'default': default_value,
        'references': references
    }


def parse_create_table(sql: str) -> Optional[Dict]:
    """Parse a CREATE TABLE statement and extract its components."""
    # Remove IF NOT EXISTS
    sql = re.sub(r'\s+IF\s+NOT\s+EXISTS\s+', ' ', sql, flags=re.IGNORECASE)

    # Extract table name
    match = re.match(r'CREATE\s+TABLE\s+[`"]?(\w+)[`"]?\s*\((.*)\)\s*;?\s*$',
                     sql, re.IGNORECASE | re.DOTALL)
    if not match:
        return None

    table_name = match.group(1)
    body = match.group(2)

    # Skip internal SQLite tables
    if table_name.lower() == 'sqlite_sequence':
        return None

    # Parse the body - split by comma but respect parentheses
    items = []
    current = ""
    paren_depth = 0

    for char in body:
        if char == '(':
            paren_depth += 1
        elif char == ')':
            paren_depth -= 1
        elif char == ',' and paren_depth == 0:
            items.append(current.strip())
            current = ""
            continue
        current += char

    if current.strip():
        items.append(current.strip())

    columns = []
    constraints = []

    for item in items:
        item = item.strip()
        if not item:
            continue

        item_upper = item.upper()

        # Skip comments
        if item.startswith('--'):
            continue

        # Check if it's a constraint
        if item_upper.startswith('PRIMARY KEY') or \
           item_upper.startswith('FOREIGN KEY') or \
           item_upper.startswith('UNIQUE') or \
           item_upper.startswith('CHECK') or \
           item_upper.startswith('CONSTRAINT'):
            constraints.append(item)
        else:
            # It's a column definition
            col_info = parse_column_def(item)
            if col_info:  # Skip None results (comments, etc.)
                columns.append(col_info)

    return {
        'table_name': table_name,
        'columns': columns,
        'constraints': constraints
    }


def convert_constraint_to_oracle(constraint: str, table_name: str) -> str:
    """Convert a SQLite constraint to Oracle syntax."""
    constraint = constraint.strip()
    constraint_upper = constraint.upper()

    # Handle FOREIGN KEY
    if constraint_upper.startswith('FOREIGN KEY'):
        # Extract the foreign key details
        match = re.match(
            r'FOREIGN\s+KEY\s*\(\s*([^)]+)\s*\)\s*REFERENCES\s+[`"]?(\w+)[`"]?\s*\(\s*([^)]+)\s*\)(.*)',
            constraint, re.IGNORECASE | re.DOTALL
        )
        if match:
            local_cols = match.group(1)
            ref_table = match.group(2)
            ref_cols = match.group(3)
            extra = match.group(4).strip() if match.group(4) else ""

            # Quote column names
            local_cols_list = [quote_identifier(c.strip().strip('`"')) for c in local_cols.split(',')]
            ref_cols_list = [quote_identifier(c.strip().strip('`"')) for c in ref_cols.split(',')]

            # Build the constraint
            result = f"FOREIGN KEY ({', '.join(local_cols_list)}) REFERENCES {quote_identifier(ref_table)} ({', '.join(ref_cols_list)})"

            # Handle ON DELETE/UPDATE
            if extra:
                # Oracle supports ON DELETE CASCADE/SET NULL/SET DEFAULT
                on_delete_match = re.search(r'ON\s+DELETE\s+(CASCADE|SET\s+NULL|SET\s+DEFAULT|NO\s+ACTION|RESTRICT)', extra, re.IGNORECASE)
                if on_delete_match:
                    action = on_delete_match.group(1).upper()
                    if action == 'CASCADE':
                        result += " ON DELETE CASCADE"
                    elif action == 'SET NULL':
                        result += " ON DELETE SET NULL"
                    # NO ACTION and RESTRICT are default in Oracle

            return result

    # Handle PRIMARY KEY
    if constraint_upper.startswith('PRIMARY KEY'):
        match = re.match(r'PRIMARY\s+KEY\s*\(\s*([^)]+)\s*\)', constraint, re.IGNORECASE)
        if match:
            cols = match.group(1)
            cols_list = [quote_identifier(c.strip().strip('`"')) for c in cols.split(',')]
            return f"PRIMARY KEY ({', '.join(cols_list)})"

    # Handle UNIQUE
    if constraint_upper.startswith('UNIQUE'):
        match = re.match(r'UNIQUE\s*\(\s*([^)]+)\s*\)', constraint, re.IGNORECASE)
        if match:
            cols = match.group(1)
            cols_list = [quote_identifier(c.strip().strip('`"')) for c in cols.split(',')]
            return f"UNIQUE ({', '.join(cols_list)})"

    # Handle CHECK
    if constraint_upper.startswith('CHECK'):
        return constraint  # Keep as-is for simple cases

    return constraint


def convert_table_to_oracle(parsed_table: Dict) -> str:
    """Convert a parsed table to Oracle DDL."""
    table_name = quote_identifier(parsed_table['table_name'])
    columns = parsed_table['columns']
    constraints = parsed_table['constraints']

    lines = []
    lines.append(f"CREATE TABLE {table_name}")
    lines.append("(")

    col_defs = []
    pk_columns = []
    inline_fk_constraints = []

    for col in columns:
        col_name = quote_identifier(col['name'])
        data_type = convert_data_type(col['data_type'], col['name'])

        parts = [f"    {col_name}"]

        # Handle AUTOINCREMENT -> GENERATED ALWAYS AS IDENTITY
        if col['is_autoincrement']:
            parts.append("NUMBER GENERATED BY DEFAULT AS IDENTITY")
        else:
            parts.append(data_type)

        # Add DEFAULT if present
        if col['default'] is not None:
            default_val = col['default']
            # Handle SQLite-specific defaults
            if default_val.upper() == 'NULL':
                parts.append("DEFAULT NULL")
            elif default_val.upper() == 'CURRENT_TIMESTAMP':
                parts.append("DEFAULT SYSTIMESTAMP")
            elif default_val.upper() == 'CURRENT_DATE':
                parts.append("DEFAULT SYSDATE")
            else:
                parts.append(f"DEFAULT {default_val}")

        # Add NOT NULL if present
        if col['is_not_null']:
            parts.append("NOT NULL")

        # Add UNIQUE if present (and not primary key)
        if col['is_unique'] and not col['is_pk']:
            parts.append("UNIQUE")

        # Track primary key columns
        if col['is_pk']:
            pk_columns.append(col_name)

        # Handle inline REFERENCES
        if col['references']:
            ref_table = quote_identifier(col['references']['table'])
            ref_col = quote_identifier(col['references']['column'])
            inline_fk_constraints.append(
                f"    FOREIGN KEY ({col_name}) REFERENCES {ref_table} ({ref_col})"
            )

        col_defs.append(" ".join(parts))

    # Add column definitions
    lines.append(",\n".join(col_defs))

    # Add primary key constraint if we have PK columns
    if pk_columns:
        lines[-1] += ","
        lines.append(f"    PRIMARY KEY ({', '.join(pk_columns)})")

    # Add inline foreign key constraints
    for fk in inline_fk_constraints:
        lines[-1] += ","
        lines.append(fk)

    # Add table-level constraints
    for constraint in constraints:
        oracle_constraint = convert_constraint_to_oracle(constraint, parsed_table['table_name'])
        if oracle_constraint:
            lines[-1] += ","
            lines.append(f"    {oracle_constraint}")

    lines.append(");")

    return "\n".join(lines)


def extract_schema_from_sqlite(db_path: str) -> List[str]:
    """Extract CREATE TABLE statements from a SQLite database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all CREATE TABLE statements
    cursor.execute("""
        SELECT sql FROM sqlite_master
        WHERE type='table' AND sql IS NOT NULL
        ORDER BY name
    """)

    schemas = [row[0] for row in cursor.fetchall()]
    conn.close()

    return schemas


def convert_database(db_path: str, output_path: str) -> bool:
    """Convert a SQLite database schema to Oracle DDL and save to file."""
    try:
        schemas = extract_schema_from_sqlite(db_path)

        oracle_ddls = []
        oracle_ddls.append(f"-- Oracle DDL for {os.path.basename(db_path)}")
        oracle_ddls.append(f"-- Converted from SQLite schema")
        oracle_ddls.append("")

        for schema in schemas:
            parsed = parse_create_table(schema)
            if parsed:
                oracle_ddl = convert_table_to_oracle(parsed)
                oracle_ddls.append(oracle_ddl)
                oracle_ddls.append("")

        # Write to output file
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w') as f:
            f.write("\n".join(oracle_ddls))

        return True
    except Exception as e:
        print(f"Error converting {db_path}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Convert SQLite DDL schemas to Oracle DDL format'
    )
    parser.add_argument(
        '--input-dir', '-i',
        default='dev_20240627/dev_databases',
        help='Input directory containing SQLite databases'
    )
    parser.add_argument(
        '--output-dir', '-o',
        default='oracle_ddl',
        help='Output directory for Oracle DDL files'
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

    # Find all SQLite databases
    sqlite_files = list(input_dir.glob('**/*.sqlite'))

    if not sqlite_files:
        print(f"No SQLite files found in '{input_dir}'")
        return 1

    print(f"Found {len(sqlite_files)} SQLite databases")

    success_count = 0
    fail_count = 0

    for sqlite_file in sorted(sqlite_files):
        # Get the database name (parent folder name)
        db_name = sqlite_file.parent.name
        output_file = output_dir / db_name / f"{db_name}_oracle.sql"

        if args.verbose:
            print(f"Converting: {sqlite_file} -> {output_file}")

        if convert_database(str(sqlite_file), str(output_file)):
            success_count += 1
            print(f"[OK] {db_name}")
        else:
            fail_count += 1
            print(f"[FAIL] {db_name}")

    print(f"\nConversion complete: {success_count} succeeded, {fail_count} failed")
    return 0 if fail_count == 0 else 1


if __name__ == '__main__':
    exit(main())
