COMMENT ON COLUMN alignment.id IS 'the unique identifier of the alignment';
COMMENT ON COLUMN alignment.alignment IS 'the alignment of the superhero';
ALTER TABLE alignment MODIFY (alignment ANNOTATIONS (ADD value_description 'commonsense evidence:Alignment refers to a character''s moral and ethical stance and can be used to describe the overall attitude or behavior of a superhero. Some common alignments for superheroes include:Good: These superheroes are typically kind, selfless, and dedicated to protecting others and upholding justice. Examples of good alignments include Superman, Wonder Woman, and Spider-Man.Neutral: These superheroes may not always prioritize the greater good, but they are not necessarily evil either. They may act in their own self-interest or make decisions based on their own moral code. Examples of neutral alignments include the Hulk and Deadpool. Bad: These superheroes are typically selfish, manipulative, and willing to harm others in pursuit of their own goals. Examples of evil alignments include Lex Luthor and the Joker.'));

-- Table: attribute
COMMENT ON COLUMN "attribute".id IS 'the unique identifier of the attribute';
COMMENT ON COLUMN "attribute".attribute_name IS 'the attribute';
ALTER TABLE "attribute" MODIFY (attribute_name ANNOTATIONS (ADD value_description 'commonsense evidence:A superhero''s attribute is a characteristic or quality that defines who they are and what they are capable of. This could be a physical trait, such as superhuman strength or the ability to fly, or a personal trait, such as extraordinary intelligence or exceptional bravery.'));

COMMENT ON COLUMN colour.id IS 'the unique identifier of the color';
COMMENT ON COLUMN colour.colour IS 'the color of the superhero''s skin/eye/hair/etc';

COMMENT ON COLUMN gender.id IS 'the unique identifier of the gender';
COMMENT ON COLUMN gender.gender IS 'the gender of the superhero';

COMMENT ON COLUMN hero_attribute.hero_id IS 'the id of the heroMaps to superhero(id)';
COMMENT ON COLUMN hero_attribute.attribute_id IS 'the id of the attributeMaps to attribute(id)';
COMMENT ON COLUMN hero_attribute.attribute_value IS 'the attribute value';
ALTER TABLE hero_attribute MODIFY (attribute_value ANNOTATIONS (ADD value_description 'commonsense evidence:If a superhero has a higher attribute value on a particular attribute, it means that they are more skilled or powerful in that area compared to other superheroes. For example, if a superhero has a higher attribute value for strength, they may be able to lift heavier objects or deliver more powerful punches than other superheroes.'));

COMMENT ON COLUMN hero_power.hero_id IS 'the id of the heroMaps to superhero(id)';
COMMENT ON COLUMN hero_power.power_id IS 'the id of the powerMaps to superpower(id)';
ALTER TABLE hero_power MODIFY (power_id ANNOTATIONS (ADD value_description 'commonsense evidence:In general, a superhero''s attributes provide the foundation for their abilities and help to define who they are, while their powers are the specific abilities that they use to fight crime and protect others.'));

COMMENT ON COLUMN publisher.id IS 'the unique identifier of the publisher';
COMMENT ON COLUMN publisher.publisher_name IS 'the name of the publisher';

COMMENT ON COLUMN race.id IS 'the unique identifier of the race';
COMMENT ON COLUMN race.race IS 'the race of the superhero';
ALTER TABLE race MODIFY (race ANNOTATIONS (ADD value_description 'commonsense evidence:In the context of superheroes, a superhero''s race would refer to the particular group of people that the superhero belongs to base on these physical characteristics'));

COMMENT ON COLUMN superhero.id IS 'the unique identifier of the superhero';
COMMENT ON COLUMN superhero.superhero_name IS 'the name of the superhero';
COMMENT ON COLUMN superhero.full_name IS 'the full name of the superhero';
ALTER TABLE superhero MODIFY (full_name ANNOTATIONS (ADD value_description 'commonsense evidence:The full name of a person typically consists of their given name, also known as their first name or personal name, and their surname, also known as their last name or family name. For example, if someone''s given name is "John" and their surname is "Smith," their full name would be "John Smith."'));
COMMENT ON COLUMN superhero.gender_id IS 'the id of the superhero''s gender';
COMMENT ON COLUMN superhero.eye_colour_id IS 'the id of the superhero''s eye color';
COMMENT ON COLUMN superhero.hair_colour_id IS 'the id of the superhero''s hair color';
COMMENT ON COLUMN superhero.skin_colour_id IS 'the id of the superhero''s skin color';
COMMENT ON COLUMN superhero.race_id IS 'the id of the superhero''s race';
COMMENT ON COLUMN superhero.publisher_id IS 'the id of the publisher';
COMMENT ON COLUMN superhero.alignment_id IS 'the id of the superhero''s alignment';
COMMENT ON COLUMN superhero.height_cm IS 'the height of the superhero';
ALTER TABLE superhero MODIFY (height_cm ANNOTATIONS (ADD value_description 'commonsense evidence:The unit of height is centimeter. If the height_cm is NULL or 0, it means the height of the superhero is missing.'));
COMMENT ON COLUMN superhero.weight_kg IS 'the weight of the superhero';
ALTER TABLE superhero MODIFY (weight_kg ANNOTATIONS (ADD value_description 'commonsense evidence:The unit of weight is kilogram. If the weight_kg is NULL or 0, it means the weight of the superhero is missing.'));

COMMENT ON COLUMN superpower.id IS 'the unique identifier of the superpower';
COMMENT ON COLUMN superpower.power_name IS 'the superpower name';
