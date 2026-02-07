/* ============================================================================

  FILE  : developer_metadata_discovery.sql
  PURPOSE
  -------
  End-to-end setup for NL metadata discovery using Hybrid Vector Search in Oracle 23ai.

  WHAT THIS SCRIPT DOES
  ---------------------
  1) Creates two metadata search tables:
       - ALL_OBJECTS_SEARCH_TEXT  (object-level)
       - ALL_COLS_SEARCH_TEXT     (column-level)
     Includes:
       - DUMMY (text anchor column for hybrid index creation)
       - ANNOTATION (native JSON)
       - ANNOTATION_TEXT (generated CLOB projection for Oracle Text indexing)

  2) Creates package DEVELOPER (AUTHID CURRENT_USER) with 3 procedures:
       - REFRESH_DATA        : refresh metadata tables from DBMS_DEVELOPER.GET_METADATA
       - SETUP_HYBRID_SEARCH : load ONNX model, create vectorizer, datastores, section groups, hybrid indexes
       - DISCOVER_OBJECTS    : two-phase hybrid search + rerank + return OUT JSON

  NOTES
  -----
  - DBMS_HYBRID_VECTOR.SEARCH returns a CLOB (JSON array) in your environment.
  - Multi-column datastore cannot include native JSON columns directly (DRG-12605),
    so we index ANNOTATION_TEXT instead of ANNOTATION.
  - Hybrid index base column must be text -> we use DUMMY CHAR(1).

============================================================================ */

/* ----- optional: make re-runs easier ----- */
SET SERVEROUTPUT ON
WHENEVER SQLERROR EXIT SQL.SQLCODE

/* ============================================================================ */
/*  0) DROP objects (ignore if missing)                                           */
/* ============================================================================ */
BEGIN EXECUTE IMMEDIATE 'DROP INDEX obj_discovery_hvix'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP INDEX col_discovery_hvix'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP PACKAGE developer'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP TABLE all_cols_search_text PURGE'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP TABLE all_objects_search_text PURGE'; EXCEPTION WHEN OTHERS THEN NULL; END;
/

/* ============================================================================ */
/*  1) TABLES                                                                     */
/* ============================================================================ */

CREATE TABLE all_objects_search_text (
  object_id      NUMBER PRIMARY KEY,
  object_name    VARCHAR2(128) NOT NULL,
  owner          VARCHAR2(128) NOT NULL,
  object_type    VARCHAR2(23)  NOT NULL,
  comment_text   CLOB,
  annotation     CLOB,
  -- Oracle Text / hybrid index cannot index JSON type directly in multi-column datastore.
  -- So we add a generated text projection:
  column_summary CLOB,
  dummy          CHAR(1) DEFAULT 'X' NOT NULL
);

CREATE TABLE all_cols_search_text (
  object_id      NUMBER NOT NULL,
  owner          VARCHAR2(128) NOT NULL,
  table_name     VARCHAR2(128) NOT NULL,
  column_name    VARCHAR2(128) NOT NULL,
  data_type      VARCHAR2(128),
  comment_text   CLOB,
  annotation     CLOB,
  dummy          CHAR(1) DEFAULT 'X' NOT NULL,
  CONSTRAINT all_cols_search_pk PRIMARY KEY (owner, table_name, column_name),
  CONSTRAINT all_cols_search_fk FOREIGN KEY (object_id)
    REFERENCES all_objects_search_text(object_id)
);

/* ============================================================================ */
/*  2) PACKAGE: DEVELOPER                                                         */
/* ============================================================================ */

CREATE OR REPLACE PACKAGE developer AUTHID CURRENT_USER AS
-------------------------------------------------------------------------------
-- PACKAGE: DEVELOPER
--
-- PURPOSE:
--   Metadata discovery utilities for Hybrid Vector Search.
--   Maintains object/column metadata search tables and exposes NL discovery API.
--
-- TABLES USED:
--   ALL_OBJECTS_SEARCH_TEXT  - Object-level metadata corpus
--   ALL_COLS_SEARCH_TEXT     - Column-level metadata corpus
--
-- INDEXES USED:
--   OBJ_DISCOVERY_HVIX       - Hybrid vector index (objects)
--   COL_DISCOVERY_HVIX       - Hybrid vector index (columns)
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
    p_result_json   OUT JSON
  );
END developer;
/
SHOW ERRORS

CREATE OR REPLACE PACKAGE BODY developer AS

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
    l_owner          VARCHAR2(128) := USER;
    l_target_name    VARCHAR2(128) := CASE
                                       WHEN p_table_name IS NULL THEN NULL
                                       ELSE UPPER(TRIM(p_table_name))
                                     END;

    l_obj_annotation JSON;
    l_col_summary    CLOB;
  BEGIN
    FOR r IN (
      SELECT object_id, object_name, object_type
      FROM   user_objects
      WHERE  object_type IN ('TABLE','VIEW')
      AND    (l_target_name IS NULL OR object_name = l_target_name)
      AND    object_name NOT IN ('ALL_OBJECTS_SEARCH_TEXT','ALL_COLS_SEARCH_TEXT')
      AND    object_name NOT LIKE 'DM$%'   -- exclude vector/mining model internals
      AND    object_name NOT LIKE 'BIN$%'  -- exclude recyclebin objects
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

      -- Upsert object row (comment may be NULL)
      MERGE INTO all_objects_search_text dst
      USING (
        SELECT
          r.object_id      AS object_id,
          r.object_name    AS object_name,
          l_owner          AS owner,
          r.object_type    AS object_type,
          utc.comments     AS comment_text,
          l_obj_annotation AS annotation,
          l_col_summary    AS column_summary
        FROM dual
        LEFT JOIN user_tab_comments utc
          ON utc.table_name = r.object_name
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
  BEGIN
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

    /* Optional wordlists (basic) */
    BEGIN ctx_ddl.drop_preference('OBJ_DISCOVERY_WL'); EXCEPTION WHEN OTHERS THEN NULL; END;
    ctx_ddl.create_preference('OBJ_DISCOVERY_WL', 'BASIC_WORDLIST');

    BEGIN ctx_ddl.drop_preference('COL_DISCOVERY_WL'); EXCEPTION WHEN OTHERS THEN NULL; END;
    ctx_ddl.create_preference('COL_DISCOVERY_WL', 'BASIC_WORDLIST');

    /* 5) Hybrid vector indexes (base column must be text -> DUMMY) */
    safe_exec('DROP INDEX obj_discovery_hvix');
    safe_exec('DROP INDEX col_discovery_hvix');

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
    p_result_json   OUT JSON
  ) IS
    c_obj_index CONSTANT VARCHAR2(128) := 'OBJ_DISCOVERY_HVIX';
    c_col_index CONSTANT VARCHAR2(128) := 'COL_DISCOVERY_HVIX';

    l_n       PLS_INTEGER := NVL(p_n, p_k0 * 5);

    -- SEARCH returns CLOB JSON text (array) in your environment
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
      req.put('search_text', p_query);
      req.put('return', ret);

      l_obj_res := DBMS_HYBRID_VECTOR.SEARCH(req.to_json);
    END;

    -- DBMS_HYBRID_VECTOR.SEARCH output is a JSON ARRAY: $[*]
    FOR r IN (
      SELECT
        o.object_id, o.object_name, o.owner, o.object_type,
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
          WHEN l_min_obj IS NULL OR l_max_obj IS NULL OR l_max_obj = l_min_obj THEN 1
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
      req.put('search_text', p_query);
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
               score     NUMBER        PATH '$.score'
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
            WHEN l_min_col IS NULL OR l_max_col IS NULL OR l_max_col = l_min_col THEN 1
            ELSE (l_cols(i).col_score_raw - l_min_col) / (l_max_col - l_min_col)
          END;
        l_cols(i).col_norm := clamp01(l_cols(i).col_norm);
      END LOOP;
    END IF;

    /* ---- Group top columns per object (top p_cols_per_obj) ---- */
    FOR i IN 1 .. l_objs.COUNT LOOP
      l_counts(i) := 0;
    END LOOP;

    FOR i IN 1 .. l_cols.COUNT LOOP
      DECLARE
        obj_idx PLS_INTEGER;
        tmp     t_col_rec;
        j       PLS_INTEGER;
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

    /* ---- Rerank: final_score = alpha*object + (1-alpha)*avg(cols) ---- */
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

    /* ---- Emit top K JSON array ---- */
    DECLARE
      TYPE t_used_tab IS TABLE OF BOOLEAN INDEX BY PLS_INTEGER;
      l_used t_used_tab;

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
                cols.append(c);
              END;
            END LOOP;
            o.put('column', cols);
          END IF;

          out_arr.append(o);
        END;
      END LOOP;

      p_result_json := out_arr.to_json;
    END;

  END discover_objects;

END developer;
/
SHOW ERRORS

/* ============================================================================ */
/*  3) OPTIONAL: Example execution (uncomment to run)                            */
/* ============================================================================ */

-- 1) Refresh metadata tables
-- BEGIN
--   developer.refresh_data(NULL);
-- END;
-- /

-- 2) Setup model + vectorizer + datastores + section groups + hybrid indexes
-- BEGIN
--   developer.setup_hybrid_search(
--     p_model_dir  => 'ONNX_IMPORT',
--     p_model_file => 'MiniLM.onnx',
--     p_model_name => 'ALL_MINILM_L6',
--     p_vectorizer => 'VEC_MINILM_IVF'
--   );
-- END;
-- /

-- 3) NL discovery query
-- SET SERVEROUTPUT ON
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

/* ============================================================================ */
