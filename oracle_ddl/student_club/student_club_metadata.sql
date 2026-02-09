COMMENT ON COLUMN attendance.link_to_event IS 'The unique identifier of the event which was attended';
ALTER TABLE attendance MODIFY (link_to_event ANNOTATIONS (ADD value_description 'References the Event table'));
COMMENT ON COLUMN attendance.link_to_member IS 'The unique identifier of the member who attended the event';
ALTER TABLE attendance MODIFY (link_to_member ANNOTATIONS (ADD value_description 'References the Member table'));

COMMENT ON COLUMN budget.budget_id IS 'A unique identifier for the budget entry';
COMMENT ON COLUMN budget.category IS 'The area for which the amount is budgeted, such as, advertisement, food, parking';
COMMENT ON COLUMN budget.spent IS 'The total amount spent in the budgeted category for an event.';
ALTER TABLE budget MODIFY (spent ANNOTATIONS (ADD value_description 'the unit is dollar. This is summarized from the Expense table'));
COMMENT ON COLUMN budget.remaining IS 'A value calculated as the amount budgeted minus the amount spent';
ALTER TABLE budget MODIFY (remaining ANNOTATIONS (ADD value_description 'the unit is dollar commonsense evidence: If the remaining < 0, it means that the cost has exceeded the budget.'));
COMMENT ON COLUMN budget.amount IS 'The amount budgeted for the specified category and event';
ALTER TABLE budget MODIFY (amount ANNOTATIONS (ADD value_description 'the unit is dollar commonsense evidence:some computation like: amount = spent + remaining'));
COMMENT ON COLUMN budget.event_status IS 'the status of the event';
ALTER TABLE budget MODIFY (event_status ANNOTATIONS (ADD value_description 'Closed / Open/ Planning commonsense evidence:  Closed: It means that the event is closed. The spent and the remaining won''t change anymore. Open: It means that the event is already opened. The spent and the remaining will change with new expenses. Planning: The event is not started yet but is planning. The spent and the remaining won''t change at this stage.'));
COMMENT ON COLUMN budget.link_to_event IS 'The unique identifier of the event to which the budget line applies.';
ALTER TABLE budget MODIFY (link_to_event ANNOTATIONS (ADD value_description 'References the Event table'));

COMMENT ON COLUMN event.event_id IS 'A unique identifier for the event';
COMMENT ON COLUMN event.event_name IS 'event name';
COMMENT ON COLUMN event.event_date IS 'The date the event took place or is scheduled to take place';
ALTER TABLE event MODIFY (event_date ANNOTATIONS (ADD value_description 'e.g. 2020-03-10T12:00:00'));
COMMENT ON COLUMN event."type" IS 'The kind of event, such as game, social, election';
COMMENT ON COLUMN event.notes IS 'A free text field for any notes about the event';
COMMENT ON COLUMN event."location" IS 'Address where the event was held or is to be held or the name of such a location';
COMMENT ON COLUMN event."status" IS 'One of three values indicating if the event is in planning, is opened, or is closed';
ALTER TABLE event MODIFY ("status" ANNOTATIONS (ADD value_description 'Open/ Closed/ Planning'));

COMMENT ON COLUMN expense.expense_id IS 'unique id of income';
COMMENT ON COLUMN expense.expense_description IS 'A textual description of what the money was spend for';
COMMENT ON COLUMN expense.expense_date IS 'The date the expense was incurred';
ALTER TABLE expense MODIFY (expense_date ANNOTATIONS (ADD value_description 'e.g. YYYY-MM-DD'));
COMMENT ON COLUMN expense.cost IS 'The dollar amount of the expense';
ALTER TABLE expense MODIFY (cost ANNOTATIONS (ADD value_description 'the unit is dollar'));
COMMENT ON COLUMN expense.approved IS 'A true or false value indicating if the expense was approved';
ALTER TABLE expense MODIFY (approved ANNOTATIONS (ADD value_description 'true/ false'));
COMMENT ON COLUMN expense.link_to_member IS 'The member who incurred the expense';
COMMENT ON COLUMN expense.link_to_budget IS 'The unique identifier of the record in the Budget table that indicates the expected total expenditure for a given category and event.';
ALTER TABLE expense MODIFY (link_to_budget ANNOTATIONS (ADD value_description 'References the Budget table'));

COMMENT ON COLUMN income.income_id IS 'A unique identifier for each record of income';
COMMENT ON COLUMN income.date_received IS 'the date that the fund received';
COMMENT ON COLUMN income.amount IS 'amount of funds';
ALTER TABLE income MODIFY (amount ANNOTATIONS (ADD value_description 'the unit is dollar'));
COMMENT ON COLUMN income.source IS 'A value indicating where the funds come from such as dues, or the annual university allocation';
COMMENT ON COLUMN income.notes IS 'A free-text value giving any needed details about the receipt of funds';
COMMENT ON COLUMN income.link_to_member IS 'link to member';

COMMENT ON COLUMN major.major_id IS 'A unique identifier for each major';
COMMENT ON COLUMN major.major_name IS 'major name';
COMMENT ON COLUMN major.department IS 'The name of the department that offers the major';
COMMENT ON COLUMN major.college IS 'The name college that houses the department that offers the major';

COMMENT ON COLUMN member.member_id IS 'unique id of member';
COMMENT ON COLUMN member.first_name IS 'member''s first name';
COMMENT ON COLUMN member.last_name IS 'member''s last name';
ALTER TABLE member MODIFY (last_name ANNOTATIONS (ADD value_description 'commonsense evidence: full name is first_name + last_name. e.g. A member''s first name is Angela and last name is Sanders. Thus, his/her full name is Angela Sanders.'));
COMMENT ON COLUMN member.email IS 'member''s email';
COMMENT ON COLUMN member."position" IS 'The position the member holds in the club';
COMMENT ON COLUMN member.t_shirt_size IS 'The size of tee shirt that member wants when shirts are ordered';
ALTER TABLE member MODIFY (t_shirt_size ANNOTATIONS (ADD value_description 'commonsense evidence: usually the student ordered t-shirt with lager size has bigger body shape'));
COMMENT ON COLUMN member.phone IS 'The best telephone at which to contact the member';
COMMENT ON COLUMN member.zip IS 'the zip code of the member''s hometown';
COMMENT ON COLUMN member.link_to_major IS 'The unique identifier of the major of the member. References the Major table';

COMMENT ON COLUMN zip_code.zip_code IS 'The ZIP code itself. A five-digit number identifying a US post office.';
COMMENT ON COLUMN zip_code."type" IS 'The kind of ZIP code';
ALTER TABLE zip_code MODIFY ("type" ANNOTATIONS (ADD value_description 'commonsense evidence: � Standard: the normal codes with which most people are familiar � PO Box: zip codes have post office boxes � Unique: zip codes that are assigned to individual organizations.'));
COMMENT ON COLUMN zip_code.city IS 'The city to which the ZIP pertains';
COMMENT ON COLUMN zip_code.county IS 'The county to which the ZIP pertains';
COMMENT ON COLUMN zip_code.state IS 'The name of the state to which the ZIP pertains';
COMMENT ON COLUMN zip_code.short_state IS 'The abbreviation of the state to which the ZIP pertains';
