-- Oracle DDL for student_club.sqlite
-- Converted from SQLite schema

CREATE TABLE attendance
(
    link_to_event VARCHAR2(4000),
    link_to_member VARCHAR2(4000),
    PRIMARY KEY (link_to_event, link_to_member),
    FOREIGN KEY (link_to_event) REFERENCES "event" (event_id),
    FOREIGN KEY (link_to_member) REFERENCES "member" (member_id)
);

CREATE TABLE budget
(
    budget_id VARCHAR2(4000),
    category VARCHAR2(4000),
    spent NUMBER,
    remaining NUMBER,
    amount NUMBER,
    event_status VARCHAR2(4000),
    link_to_event VARCHAR2(4000),
    PRIMARY KEY (budget_id),
    FOREIGN KEY (link_to_event) REFERENCES "event" (event_id)
);

CREATE TABLE "event"
(
    event_id VARCHAR2(4000),
    event_name VARCHAR2(4000),
    event_date VARCHAR2(4000),
    "type" VARCHAR2(4000),
    notes VARCHAR2(4000),
    "location" VARCHAR2(4000),
    "status" VARCHAR2(4000),
    PRIMARY KEY (event_id)
);

CREATE TABLE expense
(
    expense_id VARCHAR2(4000),
    expense_description VARCHAR2(4000),
    expense_date VARCHAR2(4000),
    cost NUMBER,
    approved VARCHAR2(4000),
    link_to_member VARCHAR2(4000),
    link_to_budget VARCHAR2(4000),
    PRIMARY KEY (expense_id),
    FOREIGN KEY (link_to_budget) REFERENCES budget (budget_id),
    FOREIGN KEY (link_to_member) REFERENCES "member" (member_id)
);

CREATE TABLE income
(
    income_id VARCHAR2(4000),
    date_received VARCHAR2(4000),
    amount NUMBER,
    source VARCHAR2(4000),
    notes VARCHAR2(4000),
    link_to_member VARCHAR2(4000),
    PRIMARY KEY (income_id),
    FOREIGN KEY (link_to_member) REFERENCES "member" (member_id)
);

CREATE TABLE major
(
    major_id VARCHAR2(4000),
    major_name VARCHAR2(4000),
    department VARCHAR2(4000),
    college VARCHAR2(4000),
    PRIMARY KEY (major_id)
);

CREATE TABLE "member"
(
    member_id VARCHAR2(4000),
    first_name VARCHAR2(4000),
    last_name VARCHAR2(4000),
    email VARCHAR2(4000),
    "position" VARCHAR2(4000),
    t_shirt_size VARCHAR2(4000),
    phone VARCHAR2(4000),
    zip NUMBER,
    link_to_major VARCHAR2(4000),
    PRIMARY KEY (member_id),
    FOREIGN KEY (link_to_major) REFERENCES major (major_id),
    FOREIGN KEY (zip) REFERENCES zip_code (zip_code)
);

CREATE TABLE zip_code
(
    zip_code NUMBER,
    "type" VARCHAR2(4000),
    city VARCHAR2(4000),
    county VARCHAR2(4000),
    state VARCHAR2(4000),
    short_state VARCHAR2(4000),
    PRIMARY KEY (zip_code)
);
