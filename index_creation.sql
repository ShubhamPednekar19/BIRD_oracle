/* ============================================================================

  FILE  : developer_metadata_discovery.sql
  PURPOSE
  -------
  End-to-end setup for NL metadata discovery using Hybrid Vector Search in Oracle 23ai.

  WHAT THIS SCRIPT DOES
  ---------------------
  1) Creates three metadata search tables:
       - ALL_OBJECTS_SEARCH_TEXT  (object-level)        — for sequential / parallel strategies
       - ALL_COLS_SEARCH_TEXT     (column-level)         — for sequential / parallel strategies
       - ALL_UNIFIED_SEARCH_TEXT  (denormalized column)  — for unified single-pass strategy

  2) Creates package developer (AUTHID CURRENT_USER) with procedures:
       - REFRESH_DATA              : refresh metadata tables from DBMS_DEVELOPER.GET_METADATA
       - SETUP_HYBRID_SEARCH       : load ONNX model, create vectorizer, datastores,
                                     section groups, hybrid indexes (obj + col + unified)
       - DISCOVER_OBJECTS           : two-phase sequential hybrid search + rerank
       - DISCOVER_OBJECTS_PARALLEL  : parallel object+column search + merge + rerank
       - DISCOVER_OBJECTS_UNIFIED   : single-pass search on denormalized unified table

  STRATEGIES OVERVIEW
  -------------------
  A) Sequential  (discover_objects):
       Phase 1 — search ALL_OBJECTS_SEARCH_TEXT → top-K0 objects
       Phase 2 — search ALL_COLS_SEARCH_TEXT filtered to those objects → rerank

  B) Parallel    (discover_objects_parallel):
       Search ALL_OBJECTS_SEARCH_TEXT and ALL_COLS_SEARCH_TEXT independently,
       then merge + normalize + rerank.

  C) Unified     (discover_objects_unified):   ★ NEW ★
       Single search on ALL_UNIFIED_SEARCH_TEXT (one row per column,
       with table-level comment + annotation denormalized into each row).
       Group hits by (owner, table_name), aggregate column scores, rank objects.

  NOTES
  -----
  - DBMS_HYBRID_VECTOR.SEARCH returns a CLOB (JSON array) in your environment.
  - Multi-column datastore cannot include native JSON columns directly (DRG-12605),
    so we store annotation as CLOB.
  - Hybrid index base column must be text -> we use DUMMY CHAR(1).

/* ============================================================================ */
/*  0) DROP objects (ignore if missing)                                         */
/* ============================================================================ */
BEGIN EXECUTE IMMEDIATE 'DROP INDEX obj_discovery_hvix'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP INDEX col_discovery_hvix'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP INDEX uni_discovery_hvix'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP PACKAGE developer'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP TABLE all_cols_search_text PURGE'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP TABLE all_objects_search_text PURGE'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP TABLE all_unified_search_text PURGE'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP PUBLIC SYNONYM developer'; EXCEPTION WHEN OTHERS THEN NULL; END;
/

BEGIN
  EXECUTE IMMEDIATE '
    CREATE TABLE all_objects_search_text (
      object_id NUMBER PRIMARY KEY,
      object_name VARCHAR2(128) NOT NULL,
      owner VARCHAR2(128) NOT NULL,
      object_type VARCHAR2(23) NOT NULL,
      comment_text CLOB,
      annotation CLOB,
      column_summary CLOB,
      dummy CHAR(1) DEFAULT ''X'' NOT NULL
    )';
EXCEPTION
  WHEN OTHERS THEN
    IF SQLCODE != -955 THEN RAISE; END IF;
END;
/

BEGIN
  EXECUTE IMMEDIATE '
    CREATE TABLE all_cols_search_text (
      object_id NUMBER NOT NULL,
      owner VARCHAR2(128) NOT NULL,
      table_name VARCHAR2(128) NOT NULL,
      column_name VARCHAR2(128) NOT NULL,
      data_type VARCHAR2(128),
      comment_text CLOB,
      annotation CLOB,
      dummy CHAR(1) DEFAULT ''X'' NOT NULL,
      CONSTRAINT all_cols_search_pk PRIMARY KEY (owner, table_name, column_name),
      CONSTRAINT all_cols_search_fk FOREIGN KEY (object_id)
        REFERENCES all_objects_search_text(object_id)
    )';
EXCEPTION
  WHEN OTHERS THEN
    IF SQLCODE != -955 THEN RAISE; END IF;
END;
/

BEGIN
  EXECUTE IMMEDIATE '
    CREATE TABLE all_unified_search_text (
      owner VARCHAR2(128) NOT NULL,
      table_name VARCHAR2(128) NOT NULL,
      column_name VARCHAR2(128) NOT NULL,
      object_type VARCHAR2(23) NOT NULL,
      data_type VARCHAR2(128),
      column_comment CLOB,
      column_annotation CLOB,
      table_comment CLOB,
      table_annotation CLOB,
      dummy CHAR(1) DEFAULT ''X'' NOT NULL,
      CONSTRAINT all_unified_search_pk PRIMARY KEY (owner, table_name, column_name)
    )';
EXCEPTION
  WHEN OTHERS THEN
    IF SQLCODE != -955 THEN RAISE; END IF;
END;
/

/* ============================================================================ */
/*  2) PACKAGE: developer                                                         */
/* ============================================================================ */

CREATE OR REPLACE PACKAGE developer AUTHID CURRENT_USER AS
-------------------------------------------------------------------------------
-- PACKAGE: developer
--
-- PURPOSE:
--   Metadata discovery utilities for Hybrid Vector Search.
--   Maintains object/column metadata search tables and exposes NL discovery API.
--
-- TABLES USED:
--   ALL_OBJECTS_SEARCH_TEXT   — Object-level metadata corpus
--   ALL_COLS_SEARCH_TEXT      — Column-level metadata corpus
--   ALL_UNIFIED_SEARCH_TEXT   — Denormalized column+table metadata corpus
--
-- INDEXES USED:
--   OBJ_DISCOVERY_HVIX        — Hybrid vector index (objects)
--   COL_DISCOVERY_HVIX        — Hybrid vector index (columns)
--   UNI_DISCOVERY_HVIX        — Hybrid vector index (unified)
-------------------------------------------------------------------------------

-------------------------------------------------------------------------------
-- REFRESH_DATA: Refresh search metadata for tables/views in caller schema.
--
-- PARAMETERS:
--   p_table_name     - Optional. If NULL (default), refreshes all TABLE/VIEW
--                      objects in the caller schema (excluding DM$%, BIN$%).
--                      If provided, refreshes only that object.
--
-- BEHAVIOR:
--   - Inserts/updates rows even when comments are NULL.
--   - Deletes and reinserts column rows for each refreshed object.
--   - Uses DBMS_DEVELOPER.GET_METADATA(JSON) for annotations and datatype.
-------------------------------------------------------------------------------
  PROCEDURE refresh_data(p_table_name IN VARCHAR2 DEFAULT NULL);

-------------------------------------------------------------------------------
-- SETUP_HYBRID_SEARCH: Initialize hybrid vector search infrastructure.
--
-- PARAMETERS:
--   p_model_dir      - Directory object containing ONNX model file.
--                      Default: 'ONNX_IMPORT'
--   p_model_file     - ONNX model filename.
--                      Default: 'MiniLM.onnx'
--   p_model_name     - Logical name for the model.
--                      Default: 'ALL_MINILM_L6'
--   p_vectorizer     - Vectorizer preference name.
--                      Default: 'VEC_MINILM_IVF'
--
-- NOTES:
--   - Uses MULTI_COLUMN_DATASTORE with FILTER=N for all columns (no HTML).
--   - Uses ANNOTATION_TEXT (CLOB) rather than ANNOTATION (JSON) to avoid DRG-12605.
--   - Creates hybrid vector indexes on DUMMY column (text anchor).
-------------------------------------------------------------------------------
  PROCEDURE setup_hybrid_search(
    p_model_dir   IN VARCHAR2 DEFAULT 'ONNX_IMPORT',
    p_model_file  IN VARCHAR2 DEFAULT 'MiniLM.onnx',
    p_model_name  IN VARCHAR2 DEFAULT 'ALL_MINILM_L6',
    p_vectorizer  IN VARCHAR2 DEFAULT 'VEC_MINILM_IVF'
  );

-------------------------------------------------------------------------------
-- DISCOVER_OBJECTS: NL metadata discovery using two-phase hybrid search + rerank.
--
-- STRATEGY:
--   1) Object discovery: hybrid search on ALL_OBJECTS_SEARCH_TEXT (top p_k0)
--   2) Column discovery: hybrid search on ALL_COLS_SEARCH_TEXT restricted to
--      object_ids from (1) (top p_n, default p_k0*5)
--   3) Group: top p_cols_per_obj columns per object
--   4) Normalize and rerank:
--        final_score = p_alpha * obj_norm + (1-p_alpha) * avg(top_col_norm)
--   5) Output: JSON array of ranked objects with matched columns
--
-- PARAMETERS:
--   p_query          - Natural language query (CLOB)
--   p_k              - Final objects returned (default 10)
--   p_k0             - Stage-1 candidate objects (default 50)
--   p_n              - Stage-2 column hits (default NULL -> p_k0*5)
--   p_cols_per_obj   - Max columns attached per object (default 3)
--   p_alpha          - Weight object vs column evidence (default 0.65)
--   p_result_json    - OUT JSON result array
-------------------------------------------------------------------------------
  PROCEDURE discover_objects(
    p_query         IN  CLOB,
    p_k             IN  PLS_INTEGER DEFAULT 10,
    p_k0            IN  PLS_INTEGER DEFAULT 50,
    p_n             IN  PLS_INTEGER DEFAULT NULL,
    p_cols_per_obj  IN  PLS_INTEGER DEFAULT 3,
    p_alpha         IN  NUMBER      DEFAULT 0.65,
    p_search_scorer IN  VARCHAR2    DEFAULT 'RSF',
    p_search_fusion IN  VARCHAR2    DEFAULT 'UNION',
    p_vector_search_mode  IN VARCHAR2 DEFAULT 'DOCUMENT',
    p_vector_aggregator   IN VARCHAR2 DEFAULT 'MAX',
    p_vector_score_weight IN NUMBER   DEFAULT 1,
    p_vector_rank_penalty IN NUMBER   DEFAULT 5,
    p_text_contains       IN CLOB     DEFAULT NULL,
    p_text_score_weight   IN NUMBER   DEFAULT 10,
    p_text_rank_penalty   IN NUMBER   DEFAULT 1,
    p_result_json   OUT JSON
  );

-------------------------------------------------------------------------------
-- DISCOVER_OBJECTS_PARALLEL: NL metadata discovery using parallel hybrid search.
--
-- STRATEGY:
--   1) Run hybrid object search on ALL_OBJECTS_SEARCH_TEXT (top p_k)
--   2) Run hybrid column search on ALL_COLS_SEARCH_TEXT (top p_m, default p_k*5)
--   3) Group column hits by object_id and retain per-column scores
--   4) Normalize object/column scores and rerank merged candidates
--   5) Output top p_k objects as JSON array
--
-- PARAMETERS:
--   p_query          - Natural language query text (CLOB)
--   p_hints          - Optional text hints (object/schema regex text query)
--   p_k              - Top-N final objects
--   p_m              - Column hit budget, must be > p_k (default p_k*5)
--   p_cols_per_obj   - Max columns attached per object in output
--   p_alpha          - Weight object evidence vs column evidence
--   p_result_json    - OUT JSON result array
-------------------------------------------------------------------------------
  PROCEDURE discover_objects_parallel(
    p_query         IN  CLOB,
    p_hints         IN  CLOB DEFAULT NULL,
    p_k             IN  PLS_INTEGER DEFAULT 10,
    p_m             IN  PLS_INTEGER DEFAULT NULL,
    p_cols_per_obj  IN  PLS_INTEGER DEFAULT 3,
    p_alpha         IN  NUMBER      DEFAULT 0.60,
    p_search_scorer IN  VARCHAR2    DEFAULT 'RSF',
    p_search_fusion IN  VARCHAR2    DEFAULT 'UNION',
    p_vector_search_mode  IN VARCHAR2 DEFAULT 'DOCUMENT',
    p_vector_aggregator   IN VARCHAR2 DEFAULT 'MAX',
    p_vector_score_weight IN NUMBER   DEFAULT 1,
    p_vector_rank_penalty IN NUMBER   DEFAULT 5,
    p_text_contains       IN CLOB     DEFAULT NULL,
    p_text_score_weight   IN NUMBER   DEFAULT 10,
    p_text_rank_penalty   IN NUMBER   DEFAULT 1,
    p_result_json   OUT JSON
  );

-------------------------------------------------------------------------------
-- DISCOVER_OBJECTS_UNIFIED: Single-pass NL metadata discovery.
--
-- STRATEGY:
--   1) Hybrid search on ALL_UNIFIED_SEARCH_TEXT (top p_n hits).
--      Each hit is a column row that also carries table_comment/table_annotation.
--   2) Discard any column hit whose normalized score < p_score_threshold.
--   3) Group surviving hits by (owner, table_name).
--   4) Per-object score = average of top-p_cols_per_obj normalized column scores.
--   5) Return top p_k objects as JSON array, each with matched columns.
--
-- PARAMETERS:
--   p_query            - Natural language query (CLOB)
--   p_k                - Final objects returned            (REQUIRED, no default)
--   p_n                - Total column hits to retrieve     (default p_k * 10)
--   p_cols_per_obj     - Max columns per object in output  (REQUIRED, no default)
--   p_score_threshold  - Minimum normalized score [0..1] for a column hit to be
--                        included. Columns scoring below this are discarded.
--                        Default 0.6.
--   p_result_json      - OUT JSON result array
-------------------------------------------------------------------------------
  PROCEDURE discover_objects_unified(
    p_query            IN  CLOB,
    p_k                IN  PLS_INTEGER DEFAULT NULL,
    p_m                IN  PLS_INTEGER DEFAULT 10,
    p_cols_per_obj     IN  PLS_INTEGER DEFAULT 10,
    p_score_threshold  IN  NUMBER      DEFAULT 0.6,
    p_search_scorer IN  VARCHAR2    DEFAULT 'RSF',
    p_search_fusion IN  VARCHAR2    DEFAULT 'UNION',
    p_vector_search_mode  IN VARCHAR2 DEFAULT 'DOCUMENT',
    p_vector_aggregator   IN VARCHAR2 DEFAULT 'MAX',
    p_vector_score_weight IN NUMBER   DEFAULT 1,
    p_vector_rank_penalty IN NUMBER   DEFAULT 5,
    p_text_contains       IN CLOB     DEFAULT NULL,
    p_text_score_weight   IN NUMBER   DEFAULT 10,
    p_text_rank_penalty   IN NUMBER   DEFAULT 1,
    p_result_json      OUT JSON
  );

END developer;
/

CREATE OR REPLACE PACKAGE BODY developer AS

  PROCEDURE apply_hybrid_search_params(
    p_req IN OUT NOCOPY JSON_OBJECT_T,
    p_query IN CLOB,
    p_search_scorer IN VARCHAR2,
    p_search_fusion IN VARCHAR2,
    p_vector_search_mode IN VARCHAR2,
    p_vector_aggregator IN VARCHAR2,
    p_vector_score_weight IN NUMBER,
    p_vector_rank_penalty IN NUMBER,
    p_text_contains IN CLOB,
    p_text_score_weight IN NUMBER,
    p_text_rank_penalty IN NUMBER
  ) IS
    l_vector JSON_OBJECT_T := JSON_OBJECT_T();
    l_text JSON_OBJECT_T := JSON_OBJECT_T();
    l_contains CLOB;
  BEGIN
    p_req.put('search_scorer', UPPER(NVL(p_search_scorer, 'RSF')));
    p_req.put('search_fusion', UPPER(NVL(p_search_fusion, 'UNION')));

    l_vector.put('search_text', p_query);
    l_vector.put('search_mode', UPPER(NVL(p_vector_search_mode, 'DOCUMENT')));
    l_vector.put('aggregator', UPPER(NVL(p_vector_aggregator, 'MAX')));
    l_vector.put('score_weight', NVL(p_vector_score_weight, 1));
    l_vector.put('rank_penalty', NVL(p_vector_rank_penalty, 5));
    p_req.put('vector', l_vector);

    l_contains := p_text_contains;
    IF l_contains IS NOT NULL THEN
      l_text.put('contains', l_contains);
    END IF;
    l_text.put('score_weight', NVL(p_text_score_weight, 10));
    l_text.put('rank_penalty', NVL(p_text_rank_penalty, 1));
    p_req.put('text', l_text);
  END apply_hybrid_search_params;

  /* ------------------------------------------------------------------------ */
  /* Utility: best-effort drop helper (ignore not-exists)                      */
  /* ------------------------------------------------------------------------ */
  PROCEDURE safe_exec(p_sql IN VARCHAR2) IS
  BEGIN
    EXECUTE IMMEDIATE p_sql;
  EXCEPTION
    WHEN OTHERS THEN
      IF SQLCODE IN (-1418, -942, -4043) THEN 
        NULL; 
      ELSE 
        RAISE; 
      END IF;
  END;

  /* ======================================================================== */
  /* REFRESH_DATA                                                             */
  /* ======================================================================== */
  PROCEDURE refresh_data(p_table_name IN VARCHAR2 DEFAULT NULL) IS
    l_meta           JSON;
    l_owner          VARCHAR2(128) := SYS_CONTEXT('USERENV','CURRENT_SCHEMA');
    l_target_name    VARCHAR2(128) := CASE
                                       WHEN p_table_name IS NULL THEN NULL
                                       ELSE UPPER(TRIM(p_table_name))
                                     END;
    l_obj_annotation JSON;
    l_col_summary    CLOB;
    l_table_comment  CLOB;

    -- JSON text for table-level annotation
    l_obj_ann_clob   CLOB;
  BEGIN
    FOR r IN (
      SELECT object_id, object_name, object_type
      FROM   user_objects
      WHERE  object_type IN ('TABLE','VIEW')
      AND    (l_target_name IS NULL OR object_name = l_target_name)
      AND    object_name NOT IN ('ALL_OBJECTS_SEARCH_TEXT','ALL_COLS_SEARCH_TEXT','ALL_UNIFIED_SEARCH_TEXT')
      AND    object_name NOT LIKE 'DM$%'
      AND    object_name NOT LIKE 'BIN$%'
    )
    LOOP
      l_meta := DBMS_DEVELOPER.GET_METADATA(
                  name        => r.object_name,
                  object_type => r.object_type,
                  level       => 'TYPICAL'
                );

      -- Object annotations 
      SELECT jt.obj_annotations
      INTO   l_obj_annotation
      FROM   JSON_TABLE(
               l_meta,
               '$.objectInfo'
               COLUMNS (
                 obj_annotations JSON PATH '$.annotations'
               )
             ) jt;

      -- Serialize object annotation to CLOB for the unified table
      l_obj_ann_clob := CASE
                          WHEN l_obj_annotation IS NOT NULL
                          THEN JSON_SERIALIZE(l_obj_annotation RETURNING CLOB)
                          ELSE NULL
                        END;

      -- Column summary: concat column names
      SELECT LISTAGG(col_name, ' ') WITHIN GROUP (ORDER BY col_pos)
      INTO   l_col_summary
      FROM   JSON_TABLE(
               l_meta,
               '$.objectInfo.columns[*]'
               COLUMNS (
                 col_pos  FOR ORDINALITY,
                 col_name VARCHAR2(128) PATH '$.name'
               )
             );

      -- Table comment
      BEGIN
        SELECT comments INTO l_table_comment
        FROM   user_tab_comments
        WHERE  table_name = r.object_name;
      EXCEPTION
        WHEN NO_DATA_FOUND THEN l_table_comment := NULL;
      END;

      /* ----- Upsert into ALL_OBJECTS_SEARCH_TEXT ----- */
      MERGE INTO all_objects_search_text dst
      USING (
        SELECT
          r.object_id      AS object_id,
          r.object_name    AS object_name,
          l_owner          AS owner,
          r.object_type    AS object_type,
          l_table_comment  AS comment_text,
          l_obj_annotation AS annotation,
          l_col_summary    AS column_summary
        FROM dual
      ) src
      ON (dst.object_id = src.object_id)
      WHEN MATCHED THEN UPDATE SET
        dst.object_name    = src.object_name,
        dst.owner          = src.owner,
        dst.object_type    = src.object_type,
        dst.comment_text   = src.comment_text,
        dst.annotation     = src.annotation,
        dst.column_summary = src.column_summary
      WHEN NOT MATCHED THEN INSERT (
        object_id, object_name, owner, object_type, comment_text, annotation, column_summary, dummy
      ) VALUES (
        src.object_id, src.object_name, src.owner, src.object_type, src.comment_text, src.annotation, src.column_summary, 'X'
      );

      -- Refresh columns for this object
      DELETE FROM all_cols_search_text
      WHERE  object_id = r.object_id;

      INSERT INTO all_cols_search_text (
        object_id, owner, table_name, column_name, data_type, comment_text, annotation, dummy
      )
      SELECT
        r.object_id,
        l_owner,
        r.object_name,
        jt.col_name,
        jt.data_type,
        ucc.comments,
        jt.col_annotations,
        'X'
      FROM JSON_TABLE(
             l_meta,
             '$.objectInfo.columns[*]'
             COLUMNS (
               col_name        VARCHAR2(128) PATH '$.name',
               data_type       VARCHAR2(128) PATH '$.dataType.type',
               col_annotations JSON          PATH '$.annotations'
             )
           ) jt
      LEFT JOIN user_col_comments ucc
        ON ucc.table_name  = r.object_name
       AND ucc.column_name = jt.col_name
      WHERE jt.col_name IS NOT NULL;

      /* ----- Refresh ALL_UNIFIED_SEARCH_TEXT ----- */
      DELETE FROM all_unified_search_text
      WHERE  owner      = l_owner
      AND    table_name = r.object_name;

      INSERT INTO all_unified_search_text (
        owner, table_name, column_name, object_type, data_type,
        column_comment, column_annotation,
        table_comment, table_annotation,
        dummy
      )
      SELECT
        l_owner,
        r.object_name,
        jt.col_name,
        r.object_type,
        jt.data_type,
        ucc.comments,                                                   -- column comment
        CASE WHEN jt.col_annotations IS NOT NULL
             THEN JSON_SERIALIZE(jt.col_annotations RETURNING CLOB)
             ELSE NULL
        END,                                                             -- column annotation (CLOB)
        l_table_comment,                                                 -- table comment (denormalized)
        l_obj_ann_clob,                                                  -- table annotation (denormalized)
        'X'
      FROM JSON_TABLE(
             l_meta,
             '$.objectInfo.columns[*]'
             COLUMNS (
               col_name        VARCHAR2(128) PATH '$.name',
               data_type       VARCHAR2(128) PATH '$.dataType.type',
               col_annotations JSON          PATH '$.annotations'
             )
           ) jt
      LEFT JOIN user_col_comments ucc
        ON ucc.table_name  = r.object_name
       AND ucc.column_name = jt.col_name
      WHERE jt.col_name IS NOT NULL;

    END LOOP;

    COMMIT;
  END refresh_data;

  /* ======================================================================== */
  /* SETUP_HYBRID_SEARCH                                                      */
  /* ======================================================================== */
  PROCEDURE setup_hybrid_search(
    p_model_dir   IN VARCHAR2 DEFAULT 'ONNX_IMPORT',
    p_model_file  IN VARCHAR2 DEFAULT 'MiniLM.onnx',
    p_model_name  IN VARCHAR2 DEFAULT 'ALL_MINILM_L6',
    p_vectorizer  IN VARCHAR2 DEFAULT 'VEC_MINILM_IVF'
  ) IS
    l_params_obj  VARCHAR2(4000);
    l_params_col  VARCHAR2(4000);
    l_params_uni  VARCHAR2(4000);
  BEGIN
    /* Refresh metadata data */
    refresh_data();

    /* 1) Load ONNX model (drop if exists) */
    BEGIN
      DBMS_VECTOR.DROP_ONNX_MODEL(model_name => p_model_name);
    EXCEPTION WHEN OTHERS THEN NULL;
    END;

    DBMS_VECTOR.LOAD_ONNX_MODEL(
      directory  => p_model_dir,
      file_name  => p_model_file,
      model_name => p_model_name,
      metadata   => JSON('{"function":"embedding","embeddingOutput":"embedding","input":{"input":["DATA"]}}')
    );

    /* 2) Vectorizer preference */
    BEGIN
      DBMS_VECTOR_CHAIN.DROP_PREFERENCE(p_vectorizer);
    EXCEPTION WHEN OTHERS THEN NULL;
    END;

    DBMS_VECTOR_CHAIN.CREATE_PREFERENCE(
      pref_name => p_vectorizer,
      pref_type => DBMS_VECTOR_CHAIN.VECTORIZER,
      params    => JSON(
        '{
          "vector_idxtype":"ivf",
          "model":"' || p_model_name || '",
          "by":"words",
          "max":"100",
          "overlap":"10",
          "split":"recursively",
          "language":"english"
        }'
      )
    );

    /* 3) Multi-column datastore preferences (FILTER all N; no HTML content) */
    BEGIN ctx_ddl.drop_preference('OBJ_DISCOVERY_DS'); EXCEPTION WHEN OTHERS THEN NULL; END;
    ctx_ddl.create_preference('OBJ_DISCOVERY_DS', 'MULTI_COLUMN_DATASTORE');
    ctx_ddl.set_attribute('OBJ_DISCOVERY_DS', 'COLUMNS',
      'object_name, owner, object_type, comment_text, annotation, column_summary');
    ctx_ddl.set_attribute('OBJ_DISCOVERY_DS', 'FILTER', 'N,N,N,N,N,N');

    BEGIN ctx_ddl.drop_preference('COL_DISCOVERY_DS'); EXCEPTION WHEN OTHERS THEN NULL; END;
    ctx_ddl.create_preference('COL_DISCOVERY_DS', 'MULTI_COLUMN_DATASTORE');
    ctx_ddl.set_attribute('COL_DISCOVERY_DS', 'COLUMNS',
      'table_name, column_name, data_type, comment_text, annotation');
    ctx_ddl.set_attribute('COL_DISCOVERY_DS', 'FILTER', 'N,N,N,N,N');

    /* 4) Section groups (tagged fields from multi-column datastore) */
    BEGIN ctx_ddl.drop_preference('UNI_DISCOVERY_DS'); EXCEPTION WHEN OTHERS THEN NULL; END;
    ctx_ddl.create_preference('UNI_DISCOVERY_DS', 'MULTI_COLUMN_DATASTORE');
    ctx_ddl.set_attribute('UNI_DISCOVERY_DS', 'COLUMNS',
      'owner, table_name, column_name, object_type, data_type, ' ||
      'column_comment, column_annotation, table_comment, table_annotation');
    ctx_ddl.set_attribute('UNI_DISCOVERY_DS', 'FILTER', 'N,N,N,N,N,N,N,N,N');

    BEGIN ctx_ddl.drop_section_group('OBJ_DISCOVERY_SG'); EXCEPTION WHEN OTHERS THEN NULL; END;
    ctx_ddl.create_section_group('OBJ_DISCOVERY_SG', 'BASIC_SECTION_GROUP');
    ctx_ddl.add_field_section('OBJ_DISCOVERY_SG', 'OBJECT_NAME', 'object_name', TRUE);
    ctx_ddl.add_field_section('OBJ_DISCOVERY_SG', 'OWNER',       'owner',       TRUE);
    ctx_ddl.add_field_section('OBJ_DISCOVERY_SG', 'OBJECT_TYPE', 'object_type', TRUE);

    BEGIN ctx_ddl.drop_section_group('COL_DISCOVERY_SG'); EXCEPTION WHEN OTHERS THEN NULL; END;
    ctx_ddl.create_section_group('COL_DISCOVERY_SG', 'BASIC_SECTION_GROUP');
    ctx_ddl.add_field_section('COL_DISCOVERY_SG', 'TABLE_NAME',  'table_name',  TRUE);
    ctx_ddl.add_field_section('COL_DISCOVERY_SG', 'COLUMN_NAME', 'column_name', TRUE);
    ctx_ddl.add_field_section('COL_DISCOVERY_SG', 'DATA_TYPE',   'data_type',   TRUE);

    BEGIN ctx_ddl.drop_section_group('UNI_DISCOVERY_SG'); EXCEPTION WHEN OTHERS THEN NULL; END;
    ctx_ddl.create_section_group('UNI_DISCOVERY_SG', 'BASIC_SECTION_GROUP');
    ctx_ddl.add_field_section('UNI_DISCOVERY_SG', 'OWNER',       'owner',       TRUE);
    ctx_ddl.add_field_section('UNI_DISCOVERY_SG', 'TABLE_NAME',  'table_name',  TRUE);
    ctx_ddl.add_field_section('UNI_DISCOVERY_SG', 'COLUMN_NAME', 'column_name', TRUE);
    ctx_ddl.add_field_section('UNI_DISCOVERY_SG', 'OBJECT_TYPE', 'object_type', TRUE);
    ctx_ddl.add_field_section('UNI_DISCOVERY_SG', 'DATA_TYPE',   'data_type',   TRUE);

    /* Optional wordlists (basic) */
    BEGIN ctx_ddl.drop_preference('OBJ_DISCOVERY_WL'); EXCEPTION WHEN OTHERS THEN NULL; END;
    ctx_ddl.create_preference('OBJ_DISCOVERY_WL', 'BASIC_WORDLIST');

    BEGIN ctx_ddl.drop_preference('COL_DISCOVERY_WL'); EXCEPTION WHEN OTHERS THEN NULL; END;
    ctx_ddl.create_preference('COL_DISCOVERY_WL', 'BASIC_WORDLIST');

    BEGIN ctx_ddl.drop_preference('UNI_DISCOVERY_WL'); EXCEPTION WHEN OTHERS THEN NULL; END;
    ctx_ddl.create_preference('UNI_DISCOVERY_WL', 'BASIC_WORDLIST');

    /* 5) Hybrid vector indexes (base column must be text -> DUMMY) */
    safe_exec('DROP INDEX obj_discovery_hvix');
    safe_exec('DROP INDEX col_discovery_hvix');
    safe_exec('DROP INDEX uni_discovery_hvix');

    l_params_obj :=
      'VECTORIZER '    || p_vectorizer       || ' ' ||
      'DATASTORE '     || 'OBJ_DISCOVERY_DS' || ' ' ||
      'WORDLIST '      || 'OBJ_DISCOVERY_WL' || ' ' ||
      'SECTION GROUP ' || 'OBJ_DISCOVERY_SG';

    EXECUTE IMMEDIATE
      'CREATE HYBRID VECTOR INDEX obj_discovery_hvix ON all_objects_search_text(dummy) ' ||
      'PARAMETERS(''' || l_params_obj || ''')';

    l_params_col :=
      'VECTORIZER '    || p_vectorizer       || ' ' ||
      'DATASTORE '     || 'COL_DISCOVERY_DS' || ' ' ||
      'WORDLIST '      || 'COL_DISCOVERY_WL' || ' ' ||
      'SECTION GROUP ' || 'COL_DISCOVERY_SG';

    EXECUTE IMMEDIATE
      'CREATE HYBRID VECTOR INDEX col_discovery_hvix ON all_cols_search_text(dummy) ' ||
      'PARAMETERS(''' || l_params_col || ''')';

    l_params_uni :=
      'VECTORIZER '    || p_vectorizer       || ' ' ||
      'DATASTORE '     || 'UNI_DISCOVERY_DS' || ' ' ||
      'WORDLIST '      || 'UNI_DISCOVERY_WL' || ' ' ||
      'SECTION GROUP ' || 'UNI_DISCOVERY_SG';

    EXECUTE IMMEDIATE
      'CREATE HYBRID VECTOR INDEX uni_discovery_hvix ON all_unified_search_text(dummy) ' ||
      'PARAMETERS(''' || l_params_uni || ''')';

  END setup_hybrid_search;

  /* ======================================================================== */
  /* DISCOVER_OBJECTS                                                         */
  /* ======================================================================== */
  PROCEDURE discover_objects(
    p_query         IN  CLOB,
    p_k             IN  PLS_INTEGER DEFAULT 10,
    p_k0            IN  PLS_INTEGER DEFAULT 50,
    p_n             IN  PLS_INTEGER DEFAULT NULL,
    p_cols_per_obj  IN  PLS_INTEGER DEFAULT 3,
    p_alpha         IN  NUMBER      DEFAULT 0.65,
    p_search_scorer IN  VARCHAR2    DEFAULT 'RSF',
    p_search_fusion IN  VARCHAR2    DEFAULT 'UNION',
    p_vector_search_mode  IN VARCHAR2 DEFAULT 'DOCUMENT',
    p_vector_aggregator   IN VARCHAR2 DEFAULT 'MAX',
    p_vector_score_weight IN NUMBER   DEFAULT 1,
    p_vector_rank_penalty IN NUMBER   DEFAULT 5,
    p_text_contains       IN CLOB     DEFAULT NULL,
    p_text_score_weight   IN NUMBER   DEFAULT 10,
    p_text_rank_penalty   IN NUMBER   DEFAULT 1,
    p_result_json   OUT JSON
  ) IS
    c_obj_index CONSTANT VARCHAR2(128) := 'OBJ_DISCOVERY_HVIX';
    c_col_index CONSTANT VARCHAR2(128) := 'COL_DISCOVERY_HVIX';

    l_n       PLS_INTEGER := NVL(p_n, p_k0 * 5);

    l_obj_res CLOB;
    l_col_res CLOB;

    l_min_obj NUMBER := NULL;
    l_max_obj NUMBER := NULL;
    l_min_col NUMBER := NULL;
    l_max_col NUMBER := NULL;

    TYPE t_obj_rec IS RECORD (
      object_id     NUMBER,
      object_name   VARCHAR2(128),
      owner         VARCHAR2(128),
      object_type   VARCHAR2(23),
      obj_score_raw NUMBER,
      obj_norm      NUMBER,
      col_support   NUMBER,
      final_score   NUMBER
    );
    TYPE t_obj_tab IS TABLE OF t_obj_rec;
    l_objs t_obj_tab := t_obj_tab();

    TYPE t_col_rec IS RECORD (
      object_id     NUMBER,
      column_name   VARCHAR2(128),
      data_type     VARCHAR2(128),
      col_score_raw NUMBER,
      col_norm      NUMBER
    );
    TYPE t_col_tab IS TABLE OF t_col_rec;
    l_cols t_col_tab := t_col_tab();

    TYPE t_objid_to_idx IS TABLE OF PLS_INTEGER INDEX BY VARCHAR2(64);
    l_obj_map t_objid_to_idx;

    TYPE t_top_cols  IS TABLE OF t_col_rec INDEX BY PLS_INTEGER;
    TYPE t_count_tab IS TABLE OF PLS_INTEGER INDEX BY PLS_INTEGER;
    TYPE t_best_tab  IS TABLE OF t_top_cols INDEX BY PLS_INTEGER;
    l_counts t_count_tab;
    l_best   t_best_tab;

    FUNCTION clamp01(p_x NUMBER) RETURN NUMBER IS
    BEGIN
      IF p_x < 0 THEN RETURN 0; END IF;
      IF p_x > 1 THEN RETURN 1; END IF;
      RETURN p_x;
    END;
  BEGIN
    p_result_json := JSON('[]');
    IF p_query IS NULL OR DBMS_LOB.getlength(p_query) = 0 THEN 
      RETURN; 
    END IF;

    /* ---- Stage 1: object hybrid search ---- */
    DECLARE
      req  JSON_OBJECT_T := JSON_OBJECT_T();
      ret  JSON_OBJECT_T := JSON_OBJECT_T();
      vals JSON_ARRAY_T  := JSON_ARRAY_T();
    BEGIN
      vals.append('rowid'); vals.append('score');
      ret.put('topN', p_k0);
      ret.put('values', vals);

      req.put('hybrid_index_name', c_obj_index);
      apply_hybrid_search_params(
        req, p_query, p_search_scorer, p_search_fusion,
        p_vector_search_mode, p_vector_aggregator,
        p_vector_score_weight, p_vector_rank_penalty,
        p_text_contains, p_text_score_weight, p_text_rank_penalty
      );
      req.put('return', ret);

      l_obj_res := DBMS_HYBRID_VECTOR.SEARCH(req.to_json);
    END;

    FOR r IN (
      SELECT 
        o.object_id, o.object_name, o.owner, o.object_type, 
        jt.score AS obj_score_raw
      FROM JSON_TABLE(
            l_obj_res, 
            '$[*]'
             COLUMNS (
                rowid_txt VARCHAR2(200) PATH '$.rowid', 
                score NUMBER PATH '$.score'
             )
           ) jt
      JOIN all_objects_search_text o 
        ON o.rowid = CHARTOROWID(jt.rowid_txt)
    ) 
    LOOP
      l_objs.EXTEND;
      l_objs(l_objs.COUNT).object_id     := r.object_id;
      l_objs(l_objs.COUNT).object_name   := r.object_name;
      l_objs(l_objs.COUNT).owner         := r.owner;
      l_objs(l_objs.COUNT).object_type   := r.object_type;
      l_objs(l_objs.COUNT).obj_score_raw := r.obj_score_raw;
      l_obj_map(TO_CHAR(r.object_id)) := l_objs.COUNT;
      IF l_min_obj IS NULL OR r.obj_score_raw < l_min_obj THEN l_min_obj := r.obj_score_raw; END IF;
      IF l_max_obj IS NULL OR r.obj_score_raw > l_max_obj THEN l_max_obj := r.obj_score_raw; END IF;
    END LOOP;

    IF l_objs.COUNT = 0 THEN 
      RETURN; 
    END IF;

    FOR i IN 1 .. l_objs.COUNT LOOP
      l_objs(i).obj_norm := 
      CASE
        WHEN l_max_obj = l_min_obj THEN 1
        ELSE (l_objs(i).obj_score_raw - l_min_obj) / (l_max_obj - l_min_obj)
      END;
      l_objs(i).obj_norm := clamp01(l_objs(i).obj_norm);
    END LOOP;

    /* ---- Stage 2: column hybrid search restricted to stage-1 object_ids ---- */
    DECLARE
      req  JSON_OBJECT_T := JSON_OBJECT_T();
      ret  JSON_OBJECT_T := JSON_OBJECT_T();
      vals JSON_ARRAY_T  := JSON_ARRAY_T();
      fb   JSON_OBJECT_T := JSON_OBJECT_T();
      args JSON_ARRAY_T  := JSON_ARRAY_T();
    BEGIN
      FOR i IN 1 .. l_objs.COUNT LOOP 
        args.append(l_objs(i).object_id); 
      END LOOP;

      fb.put('op', 'IN'); 
      fb.put('type', 'number'); 
      fb.put('col', 'OBJECT_ID'); 
      fb.put('args', args);

      vals.append('rowid'); vals.append('score');
      ret.put('topN', l_n); 
      ret.put('values', vals);

      req.put('hybrid_index_name', c_col_index);
      apply_hybrid_search_params(
        req, p_query, p_search_scorer, p_search_fusion,
        p_vector_search_mode, p_vector_aggregator,
        p_vector_score_weight, p_vector_rank_penalty,
        p_text_contains, p_text_score_weight, p_text_rank_penalty
      );
      req.put('filter_by', fb);
      req.put('return', ret);

      l_col_res := DBMS_HYBRID_VECTOR.SEARCH(req.to_json);
    END;

    FOR r IN (
      SELECT 
      c.object_id, 
      c.column_name, 
      c.data_type, 
      jt.score AS col_score_raw
      FROM JSON_TABLE(
               l_col_res, 
               '$[*]'
               COLUMNS (
                rowid_txt VARCHAR2(200) PATH '$.rowid', 
                score NUMBER PATH '$.score'
               )
           ) jt
      JOIN all_cols_search_text c 
        ON c.rowid = CHARTOROWID(jt.rowid_txt)
    ) 
    LOOP
      l_cols.EXTEND;
      l_cols(l_cols.COUNT).object_id     := r.object_id;
      l_cols(l_cols.COUNT).column_name   := r.column_name;
      l_cols(l_cols.COUNT).data_type     := r.data_type;
      l_cols(l_cols.COUNT).col_score_raw := r.col_score_raw;
      IF l_min_col IS NULL OR r.col_score_raw < l_min_col THEN l_min_col := r.col_score_raw; END IF;
      IF l_max_col IS NULL OR r.col_score_raw > l_max_col THEN l_max_col := r.col_score_raw; END IF;
    END LOOP;

    IF l_cols.COUNT > 0 THEN
      FOR i IN 1 .. l_cols.COUNT LOOP
        l_cols(i).col_norm := 
        CASE
          WHEN l_max_col = l_min_col THEN 1
          ELSE (l_cols(i).col_score_raw - l_min_col) / (l_max_col - l_min_col)
        END;
        l_cols(i).col_norm := clamp01(l_cols(i).col_norm);
      END LOOP;
    END IF;

    /* ---- Group top columns per object ---- */
    FOR i IN 1 .. l_objs.COUNT LOOP 
      l_counts(i) := 0; 
    END LOOP;

    FOR i IN 1 .. l_cols.COUNT LOOP
      DECLARE
        obj_idx PLS_INTEGER;
        tmp     t_col_rec;
      BEGIN
        obj_idx := l_obj_map(TO_CHAR(l_cols(i).object_id));
        IF obj_idx IS NULL THEN 
          CONTINUE; 
        END IF;
        tmp := l_cols(i);
        IF l_counts(obj_idx) < p_cols_per_obj THEN
          l_counts(obj_idx) := l_counts(obj_idx) + 1;
          l_best(obj_idx)(l_counts(obj_idx)) := tmp;
        ELSE
          IF tmp.col_norm > l_best(obj_idx)(l_counts(obj_idx)).col_norm THEN
            l_best(obj_idx)(l_counts(obj_idx)) := tmp;
          ELSE 
            CONTINUE;
          END IF;
        END IF;
        FOR j IN REVERSE 2 .. l_counts(obj_idx) LOOP
          IF l_best(obj_idx)(j).col_norm > l_best(obj_idx)(j-1).col_norm THEN
            tmp := l_best(obj_idx)(j-1);
            l_best(obj_idx)(j-1) := l_best(obj_idx)(j);
            l_best(obj_idx)(j) := tmp;
          END IF;
        END LOOP;
      END;
    END LOOP;

    /* ---- Rerank ---- */
    FOR i IN 1 .. l_objs.COUNT LOOP
      IF l_counts(i) IS NULL OR l_counts(i) = 0 THEN
        l_objs(i).col_support := 0;
      ELSE
        DECLARE 
          s NUMBER := 0; 
          m PLS_INTEGER := l_counts(i);
        BEGIN
          FOR j IN 1 .. m LOOP 
            s := s + l_best(i)(j).col_norm; 
          END LOOP;
          l_objs(i).col_support := s / m;
        END;
      END IF;
      l_objs(i).final_score := 
        clamp01(p_alpha * l_objs(i).obj_norm + (1 - p_alpha) * l_objs(i).col_support);
    END LOOP;

    /* ---- Emit top K ---- */
    DECLARE
      TYPE t_used_tab IS TABLE OF BOOLEAN INDEX BY PLS_INTEGER;
      l_used  t_used_tab;
      out_arr JSON_ARRAY_T := JSON_ARRAY_T();
      best_i  PLS_INTEGER;
      best_s  NUMBER;
    BEGIN
      FOR pick IN 1 .. LEAST(p_k, l_objs.COUNT) LOOP
        best_i := NULL; 
        best_s := -1;
        FOR i IN 1 .. l_objs.COUNT LOOP
          IF l_used.EXISTS(i) AND l_used(i) THEN 
            CONTINUE; 
          END IF;
          IF l_objs(i).final_score > best_s THEN 
            best_s := l_objs(i).final_score; 
            best_i := i; 
          END IF;
        END LOOP;
        EXIT WHEN best_i IS NULL;
        l_used(best_i) := TRUE;
        DECLARE
          o    JSON_OBJECT_T := JSON_OBJECT_T();
          cols JSON_ARRAY_T  := JSON_ARRAY_T();
        BEGIN
          o.put('objectName', l_objs(best_i).object_name);
          o.put('objectType', l_objs(best_i).object_type);
          o.put('schema',     l_objs(best_i).owner);
          o.put('score',      ROUND(l_objs(best_i).final_score, 6));
          IF l_counts(best_i) IS NOT NULL AND l_counts(best_i) > 0 THEN
            FOR j IN 1 .. l_counts(best_i) LOOP
              DECLARE 
                c JSON_OBJECT_T := JSON_OBJECT_T();
              BEGIN
                c.put('name',     l_best(best_i)(j).column_name);
                c.put('dataType', l_best(best_i)(j).data_type);
                cols.append(c);
              END;
            END LOOP;
            o.put('columns', cols);
          END IF;
          out_arr.append(o);
        END;
      END LOOP;
      p_result_json := out_arr.to_json;
    END;
  END discover_objects;

  /* ======================================================================== */
  /* DISCOVER_OBJECTS_PARALLEL                                                */
  /* ======================================================================== */
  PROCEDURE discover_objects_parallel(
    p_query         IN  CLOB,
    p_hints         IN  CLOB DEFAULT NULL,
    p_k             IN  PLS_INTEGER DEFAULT 10,
    p_m             IN  PLS_INTEGER DEFAULT NULL,
    p_cols_per_obj  IN  PLS_INTEGER DEFAULT 3,
    p_alpha         IN  NUMBER      DEFAULT 0.60,
    p_search_scorer IN  VARCHAR2    DEFAULT 'RSF',
    p_search_fusion IN  VARCHAR2    DEFAULT 'UNION',
    p_vector_search_mode  IN VARCHAR2 DEFAULT 'DOCUMENT',
    p_vector_aggregator   IN VARCHAR2 DEFAULT 'MAX',
    p_vector_score_weight IN NUMBER   DEFAULT 1,
    p_vector_rank_penalty IN NUMBER   DEFAULT 5,
    p_text_contains       IN CLOB     DEFAULT NULL,
    p_text_score_weight   IN NUMBER   DEFAULT 10,
    p_text_rank_penalty   IN NUMBER   DEFAULT 1,
    p_result_json   OUT JSON
  ) IS
    c_obj_index CONSTANT VARCHAR2(128) := 'OBJ_DISCOVERY_HVIX';
    c_col_index CONSTANT VARCHAR2(128) := 'COL_DISCOVERY_HVIX';

    l_k PLS_INTEGER := GREATEST(1, NVL(p_k, 10));
    l_m PLS_INTEGER := GREATEST(l_k + 1, NVL(p_m, l_k * 5));

    l_obj_res CLOB;
    l_col_res CLOB;

    l_min_obj NUMBER := NULL;
    l_max_obj NUMBER := NULL;
    l_min_col NUMBER := NULL;
    l_max_col NUMBER := NULL;

    TYPE t_obj_rec IS RECORD (
      object_id NUMBER, 
      object_name VARCHAR2(128), 
      owner VARCHAR2(128),
      object_type VARCHAR2(23), 
      obj_score_raw NUMBER, 
      obj_norm NUMBER,
      col_support NUMBER, 
      final_score NUMBER
    );
    TYPE t_obj_tab IS TABLE OF t_obj_rec;
    l_objs t_obj_tab := t_obj_tab();

    TYPE t_col_rec IS RECORD (
      object_id NUMBER, 
      column_name VARCHAR2(128), 
      data_type VARCHAR2(128),
      col_score_raw NUMBER, 
      col_norm      NUMBER
    );
    TYPE t_col_tab IS TABLE OF t_col_rec;
    l_cols t_col_tab := t_col_tab();

    TYPE t_objid_to_idx IS TABLE OF PLS_INTEGER INDEX BY VARCHAR2(64);
    l_obj_map t_objid_to_idx;

    TYPE t_top_cols  IS TABLE OF t_col_rec INDEX BY PLS_INTEGER;
    TYPE t_count_tab IS TABLE OF PLS_INTEGER INDEX BY PLS_INTEGER;
    TYPE t_best_tab  IS TABLE OF t_top_cols INDEX BY PLS_INTEGER;
    l_counts t_count_tab;
    l_best   t_best_tab;

    FUNCTION clamp01(p_x NUMBER) RETURN NUMBER IS
    BEGIN
      IF p_x < 0 THEN RETURN 0; END IF;
      IF p_x > 1 THEN RETURN 1; END IF;
      RETURN p_x;
    END;
  BEGIN
    p_result_json := JSON('[]');
    IF p_query IS NULL OR DBMS_LOB.getlength(p_query) = 0 THEN 
      RETURN; 
    END IF;

    /* ---- Stage 1: object hybrid search ---- */
    DECLARE
      req JSON_OBJECT_T := JSON_OBJECT_T(); 
      ret_obj JSON_OBJECT_T := JSON_OBJECT_T();
      return_vals JSON_ARRAY_T := JSON_ARRAY_T();
    BEGIN
      return_vals.append('rowid'); 
      return_vals.append('score');
      return_vals.append('vector_score'); 
      return_vals.append('chunk_text'); 
      return_vals.append('chunk_id');
      ret_obj.put('values', return_vals); 
      ret_obj.put('topN', l_k);
      req.put('hybrid_index_name', c_obj_index);
      apply_hybrid_search_params(
        req, p_query, p_search_scorer, p_search_fusion,
        p_vector_search_mode, p_vector_aggregator,
        p_vector_score_weight, p_vector_rank_penalty,
        p_text_contains, p_text_score_weight, p_text_rank_penalty
      );
      req.put('return', ret_obj);
      l_obj_res := DBMS_HYBRID_VECTOR.SEARCH(req.to_json);
    END;

    FOR r IN (
      SELECT
        o.object_id, 
        o.object_name, 
        o.owner, 
        o.object_type, 
        jt.score AS obj_score_raw
      FROM JSON_TABLE(
                l_obj_res, 
                '$[*]'
             COLUMNS (
              rowid_txt VARCHAR2(200) PATH '$.rowid', 
              score     NUMBER        PATH '$.score'
             )
           ) jt
      JOIN all_objects_search_text o 
      ON o.rowid = CHARTOROWID(jt.rowid_txt)
    ) LOOP
      l_objs.EXTEND;
      l_objs(l_objs.COUNT).object_id     := r.object_id;
      l_objs(l_objs.COUNT).object_name   := r.object_name;
      l_objs(l_objs.COUNT).owner         := r.owner;
      l_objs(l_objs.COUNT).object_type   := r.object_type;
      l_objs(l_objs.COUNT).obj_score_raw := r.obj_score_raw;
      l_obj_map(TO_CHAR(r.object_id)) := l_objs.COUNT;
      IF l_min_obj IS NULL OR r.obj_score_raw < l_min_obj THEN l_min_obj := r.obj_score_raw; END IF;
      IF l_max_obj IS NULL OR r.obj_score_raw > l_max_obj THEN l_max_obj := r.obj_score_raw; END IF;
    END LOOP;

    /* ---- Stage 2: column hybrid search ---- */
    DECLARE
      req         JSON_OBJECT_T := JSON_OBJECT_T(); 
      ret_obj     JSON_OBJECT_T := JSON_OBJECT_T();
      return_vals JSON_ARRAY_T  := JSON_ARRAY_T();
    BEGIN
      return_vals.append('rowid'); 
      return_vals.append('score');
      return_vals.append('vector_score'); 
      return_vals.append('chunk_text'); 
      return_vals.append('chunk_id');
      ret_obj.put('values', return_vals); 
      ret_obj.put('topN', l_m);
      req.put('hybrid_index_name', c_col_index);
      apply_hybrid_search_params(
        req, p_query, p_search_scorer, p_search_fusion,
        p_vector_search_mode, p_vector_aggregator,
        p_vector_score_weight, p_vector_rank_penalty,
        p_text_contains, p_text_score_weight, p_text_rank_penalty
      );
      req.put('return', ret_obj);
      l_col_res := DBMS_HYBRID_VECTOR.SEARCH(req.to_json);
    END;

    FOR r IN (
      SELECT 
        c.object_id, 
        c.column_name, 
        c.data_type, 
        jt.score AS col_score_raw
      FROM JSON_TABLE(
            l_col_res, 
            '$[*]'
             COLUMNS (
              rowid_txt VARCHAR2(200) PATH '$.rowid', 
              score     NUMBER        PATH '$.score'
              )
           ) jt
      JOIN all_cols_search_text c 
        ON c.rowid = CHARTOROWID(jt.rowid_txt)
    ) LOOP
      l_cols.EXTEND;
      l_cols(l_cols.COUNT).object_id     := r.object_id;
      l_cols(l_cols.COUNT).column_name   := r.column_name;
      l_cols(l_cols.COUNT).data_type     := r.data_type;
      l_cols(l_cols.COUNT).col_score_raw := r.col_score_raw;
      IF l_min_col IS NULL OR r.col_score_raw < l_min_col THEN l_min_col := r.col_score_raw; END IF;
      IF l_max_col IS NULL OR r.col_score_raw > l_max_col THEN l_max_col := r.col_score_raw; END IF;
    END LOOP;

    IF l_objs.COUNT = 0 AND l_cols.COUNT = 0 THEN 
      RETURN;
    END IF;

    -- Promote column-only objects into l_objs
    IF l_cols.COUNT > 0 THEN
      FOR i IN 1 .. l_cols.COUNT LOOP
        IF NOT l_obj_map.EXISTS(TO_CHAR(l_cols(i).object_id)) THEN
          l_objs.EXTEND;
          SELECT object_id, object_name, owner, object_type
            INTO l_objs(l_objs.COUNT).object_id, 
                 l_objs(l_objs.COUNT).object_name,
                 l_objs(l_objs.COUNT).owner, 
                 l_objs(l_objs.COUNT).object_type
            FROM all_objects_search_text 
            WHERE object_id = l_cols(i).object_id;
          l_objs(l_objs.COUNT).obj_score_raw := l_min_obj;
          l_obj_map(TO_CHAR(l_cols(i).object_id)) := l_objs.COUNT;
        END IF;
      END LOOP;
    END IF;

    FOR i IN 1 .. l_objs.COUNT LOOP
      l_objs(i).obj_norm := 
      CASE
        WHEN l_min_obj IS NULL OR l_max_obj IS NULL OR l_max_obj = l_min_obj THEN 1
        ELSE (l_objs(i).obj_score_raw - l_min_obj) / (l_max_obj - l_min_obj)
      END;
      l_objs(i).obj_norm := clamp01(l_objs(i).obj_norm);
      l_counts(i) := 0;
    END LOOP;

    IF l_cols.COUNT > 0 THEN
      FOR i IN 1 .. l_cols.COUNT LOOP
        l_cols(i).col_norm := 
        CASE
          WHEN l_max_col = l_min_col THEN 1
          ELSE (l_cols(i).col_score_raw - l_min_col) / (l_max_col - l_min_col)
        END;
        l_cols(i).col_norm := clamp01(l_cols(i).col_norm);
      END LOOP;
    END IF;

    FOR i IN 1 .. l_cols.COUNT LOOP
      DECLARE 
        obj_idx PLS_INTEGER; 
        tmp     t_col_rec;
      BEGIN
        obj_idx := l_obj_map(TO_CHAR(l_cols(i).object_id));
        IF obj_idx IS NULL THEN CONTINUE; END IF;
        tmp := l_cols(i);
        IF l_counts(obj_idx) < p_cols_per_obj THEN
          l_counts(obj_idx) := l_counts(obj_idx) + 1;
          l_best(obj_idx)(l_counts(obj_idx)) := tmp;
        ELSE
          IF tmp.col_norm > l_best(obj_idx)(l_counts(obj_idx)).col_norm THEN
            l_best(obj_idx)(l_counts(obj_idx)) := tmp;
          ELSE 
            CONTINUE;
          END IF;
        END IF;
        FOR j IN REVERSE 2 .. l_counts(obj_idx) LOOP
          IF l_best(obj_idx)(j).col_norm > l_best(obj_idx)(j-1).col_norm THEN
            tmp := l_best(obj_idx)(j-1);
            l_best(obj_idx)(j-1) := l_best(obj_idx)(j);
            l_best(obj_idx)(j) := tmp;
          END IF;
        END LOOP;
      END;
    END LOOP;

    FOR i IN 1 .. l_objs.COUNT LOOP
      IF l_counts(i) IS NULL OR l_counts(i) = 0 THEN
        l_objs(i).col_support := 0;
      ELSE
        DECLARE 
          s NUMBER := 0; 
          m PLS_INTEGER := l_counts(i);
        BEGIN
          FOR j IN 1 .. m LOOP 
            s := s + l_best(i)(j).col_norm; 
          END LOOP;
          l_objs(i).col_support := s / m;
        END;
      END IF;
      l_objs(i).final_score := 
        clamp01(p_alpha * l_objs(i).obj_norm + (1 - p_alpha) * l_objs(i).col_support);
    END LOOP;

    DECLARE
      TYPE t_used_tab IS TABLE OF BOOLEAN INDEX BY PLS_INTEGER;
      l_used t_used_tab;
      out_arr JSON_ARRAY_T := JSON_ARRAY_T();
      best_i  PLS_INTEGER; 
      best_s  NUMBER;
    BEGIN
      FOR pick IN 1 .. LEAST(l_k, l_objs.COUNT) LOOP
        best_i := NULL; 
        best_s := -1;
        FOR i IN 1 .. l_objs.COUNT LOOP
          IF l_used.EXISTS(i) AND l_used(i) THEN CONTINUE; END IF;
          IF l_objs(i).final_score > best_s THEN 
            best_s := l_objs(i).final_score; 
            best_i := i; 
          END IF;
        END LOOP;
        EXIT WHEN best_i IS NULL;
        l_used(best_i) := TRUE;
        DECLARE 
          o JSON_OBJECT_T := JSON_OBJECT_T(); 
          cols JSON_ARRAY_T := JSON_ARRAY_T();
        BEGIN
          o.put('objectName', l_objs(best_i).object_name);
          o.put('objectType', l_objs(best_i).object_type);
          o.put('schema',     l_objs(best_i).owner);
          o.put('score',      ROUND(l_objs(best_i).final_score, 6));
          IF l_counts(best_i) IS NOT NULL AND l_counts(best_i) > 0 THEN
            FOR j IN 1 .. l_counts(best_i) LOOP
              DECLARE 
                c JSON_OBJECT_T := JSON_OBJECT_T();
              BEGIN
                c.put('name',     l_best(best_i)(j).column_name);
                c.put('dataType', l_best(best_i)(j).data_type);
                c.put('score',    ROUND(l_best(best_i)(j).col_norm, 6));
                cols.append(c);
              END;
            END LOOP;
            o.put('columns', cols);
          END IF;
          out_arr.append(o);
        END;
      END LOOP;
      p_result_json := out_arr.to_json;
    END;
  END discover_objects_parallel;

  /* ======================================================================== */
  /* DISCOVER_OBJECTS_UNIFIED   ★ NEW — single-pass on denormalized table ★   */
  /* ======================================================================== */
  PROCEDURE discover_objects_unified(
    p_query            IN  CLOB,
    p_k                IN  PLS_INTEGER DEFAULT NULL,
    p_m                IN  PLS_INTEGER DEFAULT 10,
    p_cols_per_obj     IN  PLS_INTEGER DEFAULT 10,
    p_score_threshold  IN  NUMBER      DEFAULT 0.6,
    p_search_scorer IN  VARCHAR2    DEFAULT 'RSF',
    p_search_fusion IN  VARCHAR2    DEFAULT 'UNION',
    p_vector_search_mode  IN VARCHAR2 DEFAULT 'DOCUMENT',
    p_vector_aggregator   IN VARCHAR2 DEFAULT 'MAX',
    p_vector_score_weight IN NUMBER   DEFAULT 1,
    p_vector_rank_penalty IN NUMBER   DEFAULT 5,
    p_text_contains       IN CLOB     DEFAULT NULL,
    p_text_score_weight   IN NUMBER   DEFAULT 10,
    p_text_rank_penalty   IN NUMBER   DEFAULT 1,
    p_result_json      OUT JSON
  ) IS
    c_uni_index CONSTANT VARCHAR2(128) := 'UNI_DISCOVERY_HVIX';

    l_n PLS_INTEGER := GREATEST(1, NVL(p_m, p_k * 10));
    l_threshold NUMBER := GREATEST(0, LEAST(1, NVL(p_score_threshold, 0.6)));

    l_res CLOB;

    l_min_score NUMBER := NULL;
    l_max_score NUMBER := NULL;

    /* ----- Per-hit record (one row = one column hit) ----- */
    TYPE t_hit_rec IS RECORD (
      owner       VARCHAR2(128),
      table_name  VARCHAR2(128),
      column_name VARCHAR2(128),
      object_type VARCHAR2(23),
      data_type   VARCHAR2(128),
      score_raw   NUMBER,
      score_norm  NUMBER
    );
    TYPE t_hit_tab IS TABLE OF t_hit_rec;
    l_hits t_hit_tab := t_hit_tab();

    /* ----- Per-object aggregation ----- */
    TYPE t_obj_key IS RECORD (
      owner       VARCHAR2(128),
      table_name  VARCHAR2(128),
      object_type VARCHAR2(23)
    );
    TYPE t_col_info IS RECORD (
      column_name VARCHAR2(128),
      data_type   VARCHAR2(128),
      score_norm  NUMBER
    );
    TYPE t_col_list IS TABLE OF t_col_info INDEX BY PLS_INTEGER;

    TYPE t_obj_agg IS RECORD (
      key         t_obj_key,
      col_count   PLS_INTEGER,
      cols        t_col_list,
      agg_score   NUMBER          -- average of top-N column normalized scores
    );
    TYPE t_obj_agg_tab IS TABLE OF t_obj_agg INDEX BY VARCHAR2(512);  -- key = owner||chr(0)||table_name
    l_agg t_obj_agg_tab;

    l_map_key VARCHAR2(512);

    FUNCTION clamp01(p_x NUMBER) RETURN NUMBER IS
    BEGIN
      IF p_x < 0 THEN RETURN 0; END IF;
      IF p_x > 1 THEN RETURN 1; END IF;
      RETURN p_x;
    END;
  BEGIN
    p_result_json := JSON('[]');
    IF p_query IS NULL OR DBMS_LOB.getlength(p_query) = 0 THEN RETURN; END IF;

    /* ---- Single hybrid search on unified table ---- */
    DECLARE
      req  JSON_OBJECT_T := JSON_OBJECT_T();
      ret  JSON_OBJECT_T := JSON_OBJECT_T();
      vals JSON_ARRAY_T  := JSON_ARRAY_T();
    BEGIN
      vals.append('rowid');
      vals.append('score');
      ret.put('topN', l_n);
      ret.put('values', vals);

      req.put('hybrid_index_name', c_uni_index);
      apply_hybrid_search_params(
        req, p_query, p_search_scorer, p_search_fusion,
        p_vector_search_mode, p_vector_aggregator,
        p_vector_score_weight, p_vector_rank_penalty,
        p_text_contains, p_text_score_weight, p_text_rank_penalty
      );
      req.put('return', ret);

      l_res := DBMS_HYBRID_VECTOR.SEARCH(req.to_json);
    END;

    /* ---- Materialise hits ---- */
    FOR r IN (
      SELECT
        u.owner,
        u.table_name,
        u.column_name,
        u.object_type,
        u.data_type,
        jt.score AS score_raw
      FROM JSON_TABLE(
             l_res, '$[*]'
             COLUMNS (
               rowid_txt VARCHAR2(200) PATH '$.rowid',
               score     NUMBER        PATH '$.score'
             )
           ) jt
      JOIN all_unified_search_text u
        ON u.rowid = CHARTOROWID(jt.rowid_txt)
    ) LOOP
      l_hits.EXTEND;
      l_hits(l_hits.COUNT).owner       := r.owner;
      l_hits(l_hits.COUNT).table_name  := r.table_name;
      l_hits(l_hits.COUNT).column_name := r.column_name;
      l_hits(l_hits.COUNT).object_type := r.object_type;
      l_hits(l_hits.COUNT).data_type   := r.data_type;
      l_hits(l_hits.COUNT).score_raw   := r.score_raw;

      IF l_min_score IS NULL OR r.score_raw < l_min_score THEN l_min_score := r.score_raw; END IF;
      IF l_max_score IS NULL OR r.score_raw > l_max_score THEN l_max_score := r.score_raw; END IF;
    END LOOP;

    IF l_hits.COUNT = 0 THEN RETURN; END IF;

    /* ---- Normalize scores to [0,1] ---- */
    FOR i IN 1 .. l_hits.COUNT LOOP
      l_hits(i).score_norm := CASE
        WHEN l_max_score = l_min_score THEN 1
        ELSE (l_hits(i).score_raw - l_min_score) / (l_max_score - l_min_score)
      END;
      l_hits(i).score_norm := clamp01(l_hits(i).score_norm);
    END LOOP;

    /* ---- Group by (owner, table_name), keep top p_cols_per_obj per object ---- */
    /* ---- Only include columns whose normalized score >= l_threshold   ---- */
    FOR i IN 1 .. l_hits.COUNT LOOP

      -- ★ Score threshold gate: discard low-relevance column hits
      IF l_hits(i).score_norm < l_threshold THEN
        CONTINUE;
      END IF;

      l_map_key := l_hits(i).owner || CHR(0) || l_hits(i).table_name;

      IF NOT l_agg.EXISTS(l_map_key) THEN
        l_agg(l_map_key).key.owner       := l_hits(i).owner;
        l_agg(l_map_key).key.table_name  := l_hits(i).table_name;
        l_agg(l_map_key).key.object_type := l_hits(i).object_type;
        l_agg(l_map_key).col_count       := 0;
      END IF;

      DECLARE
        c   PLS_INTEGER := l_agg(l_map_key).col_count;
        tmp t_col_info;
      BEGIN
        tmp.column_name := l_hits(i).column_name;
        tmp.data_type   := l_hits(i).data_type;
        tmp.score_norm  := l_hits(i).score_norm;

        IF c < p_cols_per_obj THEN
          -- Still have room; just add
          c := c + 1;
          l_agg(l_map_key).cols(c) := tmp;
          l_agg(l_map_key).col_count := c;
        ELSE
          -- Replace the weakest if this hit is stronger
          IF tmp.score_norm > l_agg(l_map_key).cols(c).score_norm THEN
            l_agg(l_map_key).cols(c) := tmp;
          ELSE
            CONTINUE;
          END IF;
        END IF;

        -- Insertion-sort descending (keep best-first)
        FOR j IN REVERSE 2 .. l_agg(l_map_key).col_count LOOP
          IF l_agg(l_map_key).cols(j).score_norm > l_agg(l_map_key).cols(j-1).score_norm THEN
            tmp := l_agg(l_map_key).cols(j-1);
            l_agg(l_map_key).cols(j-1) := l_agg(l_map_key).cols(j);
            l_agg(l_map_key).cols(j)   := tmp;
          END IF;
        END LOOP;
      END;
    END LOOP;

    /* ---- Compute per-object aggregate score = avg(top column scores) ---- */
    DECLARE
      k VARCHAR2(512) := l_agg.FIRST;
    BEGIN
      WHILE k IS NOT NULL LOOP
        DECLARE
          s NUMBER := 0;
          m PLS_INTEGER := l_agg(k).col_count;
        BEGIN
          FOR j IN 1 .. m LOOP
            s := s + l_agg(k).cols(j).score_norm;
          END LOOP;
          l_agg(k).agg_score := CASE WHEN m > 0 THEN s / m ELSE 0 END;
        END;
        k := l_agg.NEXT(k);
      END LOOP;
    END;

    /* ---- Select top p_k objects by agg_score, emit JSON ---- */
    DECLARE
      TYPE t_used_keys IS TABLE OF BOOLEAN INDEX BY VARCHAR2(512);
      l_used  t_used_keys;
      out_arr JSON_ARRAY_T := JSON_ARRAY_T();
      best_k  VARCHAR2(512);
      best_s  NUMBER;
      k       VARCHAR2(512);
    BEGIN
      FOR pick IN 1 .. LEAST(p_k, l_agg.COUNT) LOOP
        best_k := NULL;
        best_s := -1;

        k := l_agg.FIRST;
        WHILE k IS NOT NULL LOOP
          IF NOT (l_used.EXISTS(k) AND l_used(k)) THEN
            IF l_agg(k).agg_score > best_s THEN
              best_s := l_agg(k).agg_score;
              best_k := k;
            END IF;
          END IF;
          k := l_agg.NEXT(k);
        END LOOP;

        EXIT WHEN best_k IS NULL;
        l_used(best_k) := TRUE;

        DECLARE
          o    JSON_OBJECT_T := JSON_OBJECT_T();
          cols JSON_ARRAY_T  := JSON_ARRAY_T();
        BEGIN
          o.put('objectName', l_agg(best_k).key.table_name);
          o.put('objectType', l_agg(best_k).key.object_type);
          o.put('schema',     l_agg(best_k).key.owner);
          o.put('score',      ROUND(l_agg(best_k).agg_score, 6));

          FOR j IN 1 .. l_agg(best_k).col_count LOOP
            DECLARE
              c JSON_OBJECT_T := JSON_OBJECT_T();
            BEGIN
              c.put('name',     l_agg(best_k).cols(j).column_name);
              c.put('dataType', l_agg(best_k).cols(j).data_type);
              c.put('score',    ROUND(l_agg(best_k).cols(j).score_norm, 6));
              cols.append(c);
            END;
          END LOOP;
          o.put('columns', cols);

          out_arr.append(o);
        END;
      END LOOP;

      p_result_json := out_arr.to_json;
    END;
  END discover_objects_unified;
END developer;
/

-- Grant access to package to public
GRANT EXECUTE ON developer TO PUBLIC;

CREATE PUBLIC SYNONYM developer FOR SYS.developer;

/* ============================================================================ */
/*  3) OPTIONAL: Example execution (uncomment to run)                           */
/* ============================================================================ */

-- 1) Refresh all three metadata tables
-- BEGIN
--   developer.refresh_data(NULL);
-- END;
-- /

-- 2) Setup model + vectorizer + datastores + section groups + all 3 hybrid indexes
-- BEGIN
--   developer.setup_hybrid_search(
--     p_model_dir  => 'ONNX_IMPORT',
--     p_model_file => 'MiniLM.onnx',
--     p_model_name => 'ALL_MINILM_L6',
--     p_vectorizer => 'VEC_MINILM_IVF'
--   );
-- END;
-- /

-- 3a) Sequential discovery
-- DECLARE
--   j JSON;
-- BEGIN
--   developer.discover_objects(
--     p_query       => 'Real-time stock level logs',
--     p_k           => 5,
--     p_k0          => 20,
--     p_cols_per_obj=> 3,
--     p_result_json => j
--   );
--   DBMS_OUTPUT.put_line(JSON_SERIALIZE(j RETURNING CLOB PRETTY));
-- END;
-- /

-- 3b) Parallel discovery
-- DECLARE
--   j JSON;
-- BEGIN
--   developer.discover_objects_parallel(
--     p_query       => 'Real-time stock level logs',
--     p_k           => 5,
--     p_result_json => j
--   );
--   DBMS_OUTPUT.put_line(JSON_SERIALIZE(j RETURNING CLOB PRETTY));
-- END;
-- /

-- 3c) ★ Unified single-pass discovery ★
-- DECLARE
--   j JSON;
-- BEGIN
--   developer.discover_objects_unified(
--     p_query           => 'Real-time stock level logs',
--     p_k               => 5,
--     p_n               => 50,
--     p_cols_per_obj    => 3,
--     p_score_threshold => 0.6,
--     p_result_json     => j
--   );
--   DBMS_OUTPUT.put_line(JSON_SERIALIZE(j RETURNING CLOB PRETTY));
-- END;
/

/* ============================================================================ */
