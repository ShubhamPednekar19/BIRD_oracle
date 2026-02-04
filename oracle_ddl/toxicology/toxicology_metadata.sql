-- Oracle Metadata for toxicology
-- Generated from BIRD benchmark database_description CSVs

-- Table: atom
COMMENT ON COLUMN atom.atom_id IS 'the unique id of atoms';
COMMENT ON COLUMN atom.molecule_id IS 'identifying the molecule to which the atom belongs';
ALTER TABLE atom MODIFY (molecule_id ANNOTATIONS (ADD value_description 'commonsense evidence:TRXXX_i represents ith atom of molecule TRXXX'));
COMMENT ON COLUMN atom."element" IS 'the element of the toxicology';
ALTER TABLE atom MODIFY ("element" ANNOTATIONS (ADD value_description ' cl: chlorine c: carbon h: hydrogen o: oxygen s: sulfur n: nitrogen p: phosphorus na: sodium br: bromine f: fluorine i: iodine sn: Tin pb: lead te: tellurium ca: Calcium'));

-- Table: bond
COMMENT ON COLUMN bond.bond_id IS 'unique id representing bonds';
ALTER TABLE bond MODIFY (bond_id ANNOTATIONS (ADD value_description 'TRxxx_A1_A2:TRXXX refers to which moleculeA1 and A2 refers to which atom'));
COMMENT ON COLUMN bond.molecule_id IS 'identifying the molecule in which the bond appears';
COMMENT ON COLUMN bond.bond_type IS 'type of the bond';
ALTER TABLE bond MODIFY (bond_type ANNOTATIONS (ADD value_description 'commonsense evidence:-: single bond''='': double bond''#'': triple bond'));

-- Table: connected
COMMENT ON COLUMN connected.atom_id IS 'id of the first atom';
COMMENT ON COLUMN connected.atom_id2 IS 'id of the second atom';
COMMENT ON COLUMN connected.bond_id IS 'bond id representing bond between two atoms';

-- Table: molecule
COMMENT ON COLUMN molecule.molecule_id IS 'unique id of molecule';
ALTER TABLE molecule MODIFY (molecule_id ANNOTATIONS (ADD value_description '"+" --> this molecule / compound is carcinogenic''-'' this molecule is not / compound carcinogenic'));
COMMENT ON COLUMN molecule.label IS 'whether this molecule is carcinogenic or not';
