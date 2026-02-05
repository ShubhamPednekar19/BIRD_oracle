-- Oracle DDL for financial.sqlite
-- Converted from SQLite schema

CREATE TABLE "account"
(
    account_id NUMBER DEFAULT 0 NOT NULL,
    district_id NUMBER DEFAULT 0 NOT NULL,
    frequency VARCHAR2(4000) NOT NULL,
    "date" DATE NOT NULL,
    PRIMARY KEY (account_id)
);

CREATE TABLE card
(
    card_id NUMBER DEFAULT 0 NOT NULL,
    disp_id NUMBER NOT NULL,
    "type" VARCHAR2(4000) NOT NULL,
    issued DATE NOT NULL,
    PRIMARY KEY (card_id)
);

CREATE TABLE client
(
    client_id NUMBER NOT NULL,
    gender VARCHAR2(4000) NOT NULL,
    birth_date DATE NOT NULL,
    district_id NUMBER NOT NULL,
    PRIMARY KEY (client_id)
);

CREATE TABLE disp
(
    disp_id NUMBER NOT NULL,
    client_id NUMBER NOT NULL,
    account_id NUMBER NOT NULL,
    "type" VARCHAR2(4000) NOT NULL,
    PRIMARY KEY (disp_id)
);

CREATE TABLE district
(
    district_id NUMBER DEFAULT 0 NOT NULL,
    A2 VARCHAR2(4000) NOT NULL,
    A3 VARCHAR2(4000) NOT NULL,
    A4 VARCHAR2(4000) NOT NULL,
    A5 VARCHAR2(4000) NOT NULL,
    A6 VARCHAR2(4000) NOT NULL,
    A7 VARCHAR2(4000) NOT NULL,
    A8 NUMBER NOT NULL,
    A9 NUMBER NOT NULL,
    A10 NUMBER NOT NULL,
    A11 NUMBER NOT NULL,
    A12 NUMBER,
    A13 NUMBER NOT NULL,
    A14 NUMBER NOT NULL,
    A15 NUMBER,
    A16 NUMBER NOT NULL,
    PRIMARY KEY (district_id)
);

CREATE TABLE loan
(
    loan_id NUMBER DEFAULT 0 NOT NULL,
    account_id NUMBER NOT NULL,
    "date" DATE NOT NULL,
    amount NUMBER NOT NULL,
    duration NUMBER NOT NULL,
    payments NUMBER NOT NULL,
    "status" VARCHAR2(4000) NOT NULL,
    PRIMARY KEY (loan_id)
);

CREATE TABLE "order"
(
    order_id NUMBER DEFAULT 0 NOT NULL,
    account_id NUMBER NOT NULL,
    bank_to VARCHAR2(4000) NOT NULL,
    account_to NUMBER NOT NULL,
    amount NUMBER NOT NULL,
    k_symbol VARCHAR2(4000) NOT NULL,
    PRIMARY KEY (order_id)
);

CREATE TABLE trans
(
    trans_id NUMBER DEFAULT 0 NOT NULL,
    account_id NUMBER DEFAULT 0 NOT NULL,
    "date" DATE NOT NULL,
    "type" VARCHAR2(4000) NOT NULL,
    operation VARCHAR2(4000),
    amount NUMBER NOT NULL,
    balance NUMBER NOT NULL,
    k_symbol VARCHAR2(4000),
    bank VARCHAR2(4000),
    "account" NUMBER,
    PRIMARY KEY (trans_id)
);

-- Deferred foreign key constraints
ALTER TABLE "account" ADD CONSTRAINT FK_ACCOUNT_1 FOREIGN KEY (district_id) REFERENCES district (district_id);
ALTER TABLE card ADD CONSTRAINT FK_CARD_1 FOREIGN KEY (disp_id) REFERENCES disp (disp_id);
ALTER TABLE client ADD CONSTRAINT FK_CLIENT_1 FOREIGN KEY (district_id) REFERENCES district (district_id);
ALTER TABLE disp ADD CONSTRAINT FK_DISP_1 FOREIGN KEY (account_id) REFERENCES "account" (account_id);
ALTER TABLE disp ADD CONSTRAINT FK_DISP_2 FOREIGN KEY (client_id) REFERENCES client (client_id);
ALTER TABLE loan ADD CONSTRAINT FK_LOAN_1 FOREIGN KEY (account_id) REFERENCES "account" (account_id);
ALTER TABLE "order" ADD CONSTRAINT FK_ORDER_1 FOREIGN KEY (account_id) REFERENCES "account" (account_id);
ALTER TABLE trans ADD CONSTRAINT FK_TRANS_1 FOREIGN KEY (account_id) REFERENCES "account" (account_id);
