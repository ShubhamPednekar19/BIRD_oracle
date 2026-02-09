CREATE TABLE alignment
(
    id NUMBER NOT NULL,
    alignment VARCHAR2(4000) DEFAULT NULL,
    PRIMARY KEY (id)
);

CREATE TABLE "attribute"
(
    id NUMBER NOT NULL,
    attribute_name VARCHAR2(4000) DEFAULT NULL,
    PRIMARY KEY (id)
);

CREATE TABLE colour
(
    id NUMBER NOT NULL,
    colour VARCHAR2(4000) DEFAULT NULL,
    PRIMARY KEY (id)
);

CREATE TABLE gender
(
    id NUMBER NOT NULL,
    gender VARCHAR2(4000) DEFAULT NULL,
    PRIMARY KEY (id)
);

CREATE TABLE hero_attribute
(
    hero_id NUMBER DEFAULT NULL,
    attribute_id NUMBER DEFAULT NULL,
    attribute_value NUMBER DEFAULT NULL
);

CREATE TABLE hero_power
(
    hero_id NUMBER DEFAULT NULL,
    power_id NUMBER DEFAULT NULL
);

CREATE TABLE publisher
(
    id NUMBER NOT NULL,
    publisher_name VARCHAR2(4000) DEFAULT NULL,
    PRIMARY KEY (id)
);

CREATE TABLE race
(
    id NUMBER NOT NULL,
    race VARCHAR2(4000) DEFAULT NULL,
    PRIMARY KEY (id)
);

CREATE TABLE superhero
(
    id NUMBER NOT NULL,
    superhero_name VARCHAR2(4000) DEFAULT NULL,
    full_name VARCHAR2(4000) DEFAULT NULL,
    gender_id NUMBER DEFAULT NULL,
    eye_colour_id NUMBER DEFAULT NULL,
    hair_colour_id NUMBER DEFAULT NULL,
    skin_colour_id NUMBER DEFAULT NULL,
    race_id NUMBER DEFAULT NULL,
    publisher_id NUMBER DEFAULT NULL,
    alignment_id NUMBER DEFAULT NULL,
    height_cm NUMBER DEFAULT NULL,
    weight_kg NUMBER DEFAULT NULL,
    PRIMARY KEY (id)
);

CREATE TABLE superpower
(
    id NUMBER NOT NULL,
    power_name VARCHAR2(4000) DEFAULT NULL,
    PRIMARY KEY (id)
);

ALTER TABLE hero_attribute ADD CONSTRAINT FK_HERO_ATTRIBUTE_1 FOREIGN KEY (attribute_id) REFERENCES "attribute" (id);
ALTER TABLE hero_attribute ADD CONSTRAINT FK_HERO_ATTRIBUTE_2 FOREIGN KEY (hero_id) REFERENCES superhero (id);
ALTER TABLE hero_power ADD CONSTRAINT FK_HERO_POWER_1 FOREIGN KEY (hero_id) REFERENCES superhero (id);
ALTER TABLE hero_power ADD CONSTRAINT FK_HERO_POWER_2 FOREIGN KEY (power_id) REFERENCES superpower (id);
ALTER TABLE superhero ADD CONSTRAINT FK_SUPERHERO_1 FOREIGN KEY (alignment_id) REFERENCES alignment (id);
ALTER TABLE superhero ADD CONSTRAINT FK_SUPERHERO_2 FOREIGN KEY (eye_colour_id) REFERENCES colour (id);
ALTER TABLE superhero ADD CONSTRAINT FK_SUPERHERO_3 FOREIGN KEY (gender_id) REFERENCES gender (id);
ALTER TABLE superhero ADD CONSTRAINT FK_SUPERHERO_4 FOREIGN KEY (hair_colour_id) REFERENCES colour (id);
ALTER TABLE superhero ADD CONSTRAINT FK_SUPERHERO_5 FOREIGN KEY (publisher_id) REFERENCES publisher (id);
ALTER TABLE superhero ADD CONSTRAINT FK_SUPERHERO_6 FOREIGN KEY (race_id) REFERENCES race (id);
ALTER TABLE superhero ADD CONSTRAINT FK_SUPERHERO_7 FOREIGN KEY (skin_colour_id) REFERENCES colour (id);
