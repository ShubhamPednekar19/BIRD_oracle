-- Oracle DDL for codebase_community.sqlite
-- Converted from SQLite schema

CREATE TABLE badges
(
    Id NUMBER NOT NULL,
    UserId NUMBER,
    "Name" VARCHAR2(4000),
    "Date" TIMESTAMP,
    PRIMARY KEY (Id),
    FOREIGN KEY (UserId) REFERENCES users (Id) ON DELETE CASCADE
);

CREATE TABLE comments
(
    Id NUMBER NOT NULL,
    PostId NUMBER,
    Score NUMBER,
    "Text" VARCHAR2(4000),
    CreationDate TIMESTAMP,
    UserId NUMBER,
    UserDisplayName VARCHAR2(4000),
    PRIMARY KEY (Id),
    FOREIGN KEY (PostId) REFERENCES posts (Id) ON DELETE CASCADE,
    FOREIGN KEY (UserId) REFERENCES users (Id) ON DELETE CASCADE
);

CREATE TABLE postHistory
(
    Id NUMBER NOT NULL,
    PostHistoryTypeId NUMBER,
    PostId NUMBER,
    RevisionGUID VARCHAR2(4000),
    CreationDate TIMESTAMP,
    UserId NUMBER,
    "Text" VARCHAR2(4000),
    "Comment" VARCHAR2(4000),
    UserDisplayName VARCHAR2(4000),
    PRIMARY KEY (Id),
    FOREIGN KEY (PostId) REFERENCES posts (Id) ON DELETE CASCADE,
    FOREIGN KEY (UserId) REFERENCES users (Id) ON DELETE CASCADE
);

CREATE TABLE postLinks
(
    Id NUMBER NOT NULL,
    CreationDate TIMESTAMP,
    PostId NUMBER,
    RelatedPostId NUMBER,
    LinkTypeId NUMBER,
    PRIMARY KEY (Id),
    FOREIGN KEY (PostId) REFERENCES posts (Id) ON DELETE CASCADE,
    FOREIGN KEY (RelatedPostId) REFERENCES posts (Id) ON DELETE CASCADE
);

CREATE TABLE posts
(
    Id NUMBER NOT NULL,
    PostTypeId NUMBER,
    AcceptedAnswerId NUMBER,
    CreaionDate TIMESTAMP,
    Score NUMBER,
    ViewCount NUMBER,
    "Body" VARCHAR2(4000),
    OwnerUserId NUMBER,
    LasActivityDate TIMESTAMP,
    Title VARCHAR2(4000),
    Tags VARCHAR2(4000),
    AnswerCount NUMBER,
    CommentCount NUMBER,
    FavoriteCount NUMBER,
    LastEditorUserId NUMBER,
    LastEditDate TIMESTAMP,
    CommunityOwnedDate TIMESTAMP,
    ParentId NUMBER,
    ClosedDate TIMESTAMP,
    OwnerDisplayName VARCHAR2(4000),
    LastEditorDisplayName VARCHAR2(4000),
    PRIMARY KEY (Id),
    FOREIGN KEY (LastEditorUserId) REFERENCES users (Id) ON DELETE CASCADE,
    FOREIGN KEY (OwnerUserId) REFERENCES users (Id) ON DELETE CASCADE,
    FOREIGN KEY (ParentId) REFERENCES posts (Id) ON DELETE CASCADE
);

CREATE TABLE tags
(
    Id NUMBER NOT NULL,
    TagName VARCHAR2(4000),
    "Count" NUMBER,
    ExcerptPostId NUMBER,
    WikiPostId NUMBER,
    PRIMARY KEY (Id),
    FOREIGN KEY (ExcerptPostId) REFERENCES posts (Id) ON DELETE CASCADE
);

CREATE TABLE users
(
    Id NUMBER NOT NULL,
    Reputation NUMBER,
    CreationDate TIMESTAMP,
    DisplayName VARCHAR2(4000),
    LastAccessDate TIMESTAMP,
    WebsiteUrl VARCHAR2(4000),
    "Location" VARCHAR2(4000),
    AboutMe VARCHAR2(4000),
    Views NUMBER,
    UpVotes NUMBER,
    DownVotes NUMBER,
    AccountId NUMBER,
    Age NUMBER,
    ProfileImageUrl VARCHAR2(4000),
    PRIMARY KEY (Id)
);

CREATE TABLE votes
(
    Id NUMBER NOT NULL,
    PostId NUMBER,
    VoteTypeId NUMBER,
    CreationDate DATE,
    UserId NUMBER,
    BountyAmount NUMBER,
    PRIMARY KEY (Id),
    FOREIGN KEY (PostId) REFERENCES posts (Id) ON DELETE CASCADE,
    FOREIGN KEY (UserId) REFERENCES users (Id) ON DELETE CASCADE
);
