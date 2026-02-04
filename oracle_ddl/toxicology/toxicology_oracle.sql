-- Oracle DDL for toxicology.sqlite
-- Converted from SQLite schema

CREATE TABLE atom
(
    atom_id VARCHAR2(4000) NOT NULL,
    molecule_id VARCHAR2(4000) DEFAULT NULL,
    "element" VARCHAR2(4000) DEFAULT NULL,
    PRIMARY KEY (atom_id),
    FOREIGN KEY (molecule_id) REFERENCES molecule (molecule_id)
);

CREATE TABLE bond
(
    bond_id VARCHAR2(4000) NOT NULL,
    molecule_id VARCHAR2(4000) DEFAULT NULL,
    bond_type VARCHAR2(4000) DEFAULT NULL,
    PRIMARY KEY (bond_id),
    FOREIGN KEY (molecule_id) REFERENCES molecule (molecule_id)
);

CREATE TABLE connected
(
    atom_id VARCHAR2(4000) NOT NULL,
    atom_id2 VARCHAR2(4000) NOT NULL,
    bond_id VARCHAR2(4000) DEFAULT NULL,
    PRIMARY KEY (atom_id, atom_id2),
    FOREIGN KEY (atom_id) REFERENCES atom (atom_id) ON DELETE CASCADE,
    FOREIGN KEY (atom_id2) REFERENCES atom (atom_id) ON DELETE CASCADE,
    FOREIGN KEY (bond_id) REFERENCES bond (bond_id) ON DELETE CASCADE
);

CREATE TABLE molecule
(
    molecule_id VARCHAR2(4000) NOT NULL,
    label VARCHAR2(4000) DEFAULT NULL,
    PRIMARY KEY (molecule_id)
);
