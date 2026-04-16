CREATE TABLE "LANGS"(LID    INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                            LANG   VARCHAR2(255) UNIQUE,
                            LOCALE VARCHAR2(255) UNIQUE,
                            PAGES  INTEGER DEFAULT 0,  
                            WORDS  INTEGER DEFAULT 0);

CREATE TABLE "PAGES"(PID INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                            LID INTEGER REFERENCES "LANGS"(LID)   ON DELETE CASCADE,
                            PAGE INTEGER DEFAULT NULL, 
                            REVISION INTEGER DEFAULT NULL, 
                            TITLE VARCHAR2(255),
                            WORDS INTEGER DEFAULT 0, 
                            UNIQUE(LID,PAGE,TITLE));

CREATE TABLE "WORDS"(WID INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                            WORD        VARCHAR2(255) UNIQUE,
                            OCCURRENCES INTEGER DEFAULT 0);

CREATE TABLE "LANGS_WORDS"(LID INTEGER REFERENCES "LANGS"(LID)   ON DELETE CASCADE,
                                        WID INTEGER REFERENCES "WORDS"(WID)   ON DELETE CASCADE,
                                        OCCURRENCES INTEGER, 
                                        PRIMARY KEY(LID,WID));

CREATE TABLE "PAGES_WORDS"(PID INTEGER REFERENCES "PAGES"(PID)   ON DELETE CASCADE,
                                        WID INTEGER REFERENCES "WORDS"(WID)   ON DELETE CASCADE,
                                        OCCURRENCES INTEGER DEFAULT 0, 
                                        PRIMARY KEY(PID,WID));

CREATE TABLE "BIWORDS"(LID    INTEGER REFERENCES "LANGS"(LID)   ON DELETE CASCADE,
                                W1ST   INTEGER REFERENCES "WORDS"(WID)   ON DELETE CASCADE,
                                W2ND   INTEGER REFERENCES "WORDS"(WID)   ON DELETE CASCADE,
                                OCCURRENCES INTEGER DEFAULT 0,                                 PRIMARY KEY(LID,W1ST,W2ND));

