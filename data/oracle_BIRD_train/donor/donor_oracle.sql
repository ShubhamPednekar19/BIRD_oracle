CREATE TABLE "ESSAYS"
(PROJECTID         VARCHAR2(255),
    TEACHER_ACCTID    VARCHAR2(255),
    TITLE             VARCHAR2(255),
    SHORT_DESCRIPTION VARCHAR2(255),
    NEED_STATEMENT    VARCHAR2(255),
    ESSAY             VARCHAR2(255)
);

CREATE TABLE "PROJECTS"
(PROJECTID                              VARCHAR2(255)   
        PRIMARY KEY,
    TEACHER_ACCTID                         VARCHAR2(255),
    SCHOOLID                               VARCHAR2(255),
    SCHOOL_NCESID                          VARCHAR2(255),
    SCHOOL_LATITUDE                        FLOAT,
    SCHOOL_LONGITUDE                       FLOAT,
    SCHOOL_CITY                            VARCHAR2(255),
    SCHOOL_STATE                           VARCHAR2(255),
    SCHOOL_ZIP                             INTEGER,
    SCHOOL_METRO                           VARCHAR2(255),
    SCHOOL_DISTRICT                        VARCHAR2(255),
    SCHOOL_COUNTY                          VARCHAR2(255),
    SCHOOL_CHARTER                         VARCHAR2(255),
    SCHOOL_MAGNET                          VARCHAR2(255),
    SCHOOL_YEAR_ROUND                      VARCHAR2(255),
    SCHOOL_NLNS                            VARCHAR2(255),
    SCHOOL_KIPP                            VARCHAR2(255),
    SCHOOL_CHARTER_READY_PROMISE           VARCHAR2(255),
    TEACHER_PREFIX                         VARCHAR2(255),
    TEACHER_TEACH_FOR_AMERICA              VARCHAR2(255),
    TEACHER_NY_TEACHING_FELLOW             VARCHAR2(255),
    PRIMARY_FOCUS_SUBJECT                  VARCHAR2(255),
    PRIMARY_FOCUS_AREA                     VARCHAR2(255),
    SECONDARY_FOCUS_SUBJECT                VARCHAR2(255),
    SECONDARY_FOCUS_AREA                   VARCHAR2(255),
    RESOURCE_TYPE                          VARCHAR2(255),
    POVERTY_LEVEL                          VARCHAR2(255),
    GRADE_LEVEL                            VARCHAR2(255),
    FULFILLMENT_LABOR_MATERIALS            FLOAT,
    TOTAL_PRICE_EXCLUDING_OPTIONAL_SUPPORT FLOAT,
    TOTAL_PRICE_INCLUDING_OPTIONAL_SUPPORT FLOAT,
    STUDENTS_REACHED                       INTEGER,
    ELIGIBLE_DOUBLE_YOUR_IMPACT_MATCH      VARCHAR2(255),
    ELIGIBLE_ALMOST_HOME_MATCH             VARCHAR2(255),
    DATE_POSTED                            DATE
);

CREATE TABLE "DONATIONS"
(DONATIONID                               VARCHAR2(255)   
            PRIMARY KEY,
    PROJECTID                               VARCHAR2(255),
    DONOR_ACCTID                             VARCHAR2(255),
    DONOR_CITY                               VARCHAR2(255),
    DONOR_STATE                              VARCHAR2(255),
    DONOR_ZIP                                VARCHAR2(255),
    IS_TEACHER_ACCT                          VARCHAR2(255),
    DONATION_TIMESTAMP                       TIMESTAMP,
    DONATION_TO_PROJECT                      FLOAT,
    DONATION_OPTIONAL_SUPPORT                FLOAT,
    DONATION_TOTAL                           FLOAT,
    DOLLAR_AMOUNT                            VARCHAR2(255),
    DONATION_INCLUDED_OPTIONAL_SUPPORT       VARCHAR2(255),
    PAYMENT_METHOD                           VARCHAR2(255),
    PAYMENT_INCLUDED_ACCT_CREDIT             VARCHAR2(255),
    PAYMENT_INCLUDED_CAMPAIGN_GIFT_CARD      VARCHAR2(255),
    PAYMENT_INCLUDED_WEB_PURCHASED_GIFT_CARD VARCHAR2(255),
    PAYMENT_WAS_PROMO_MATCHED                VARCHAR2(255),
    VIA_GIVING_PAGE                          VARCHAR2(255),
    FOR_HONOREE                              VARCHAR2(255),
    DONATION_MESSAGE                         VARCHAR2(255),
    FOREIGN KEY (PROJECTID) REFERENCES "PROJECTS"(PROJECTID)
);

CREATE TABLE "RESOURCES"
(RESOURCEID            VARCHAR2(255)   
            PRIMARY KEY,
    PROJECTID             VARCHAR2(255),
    VENDORID              INTEGER,
    VENDOR_NAME           VARCHAR2(255),
    PROJECT_RESOURCE_TYPE VARCHAR2(255),
    ITEM_NAME             VARCHAR2(255),
    ITEM_NUMBER           VARCHAR2(255),
    ITEM_UNIT_PRICE       FLOAT,
    ITEM_QUANTITY         INTEGER,
    FOREIGN KEY (PROJECTID) REFERENCES "PROJECTS"(PROJECTID)
);

