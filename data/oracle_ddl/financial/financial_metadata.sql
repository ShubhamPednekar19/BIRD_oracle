COMMENT ON COLUMN "account".account_id IS 'the id of the account';
COMMENT ON COLUMN "account".district_id IS 'location of branch';
COMMENT ON COLUMN "account".frequency IS 'frequency of the acount';
COMMENT ON COLUMN "account"."date" IS 'the creation date of the account';
ALTER TABLE "account" MODIFY ("date" ANNOTATIONS (ADD value_description 'in the form YYMMDD'));

COMMENT ON COLUMN card.card_id IS 'id number of credit card';
COMMENT ON COLUMN card.disp_id IS 'disposition id';
COMMENT ON COLUMN card."type" IS 'type of credit card';
ALTER TABLE card MODIFY ("type" ANNOTATIONS (ADD value_description '"junior": junior class of credit card; "classic": standard class of credit card; "gold": high-level credit card'));
COMMENT ON COLUMN card.issued IS 'the date when the credit card issued';
ALTER TABLE card MODIFY (issued ANNOTATIONS (ADD value_description 'in the form YYMMDD'));

COMMENT ON COLUMN client.client_id IS 'the unique number';
ALTER TABLE client MODIFY (gender ANNOTATIONS (ADD value_description 'F：female M：male'));
COMMENT ON COLUMN client.birth_date IS 'birth date';
COMMENT ON COLUMN client.district_id IS 'location of branch';

COMMENT ON COLUMN disp.disp_id IS 'unique number of identifying this row of record';
COMMENT ON COLUMN disp.client_id IS 'id number of client';
COMMENT ON COLUMN disp.account_id IS 'id number of account';
COMMENT ON COLUMN disp."type" IS 'type of disposition';
ALTER TABLE disp MODIFY ("type" ANNOTATIONS (ADD value_description '"OWNER" : "USER" : "DISPONENT"commonsense evidence:the account can only have the right to issue permanent orders or apply for loans'));

COMMENT ON COLUMN district.district_id IS 'location of branch';
COMMENT ON COLUMN district.A2 IS 'district_name';
COMMENT ON COLUMN district.A3 IS 'region';
COMMENT ON COLUMN district.A5 IS 'municipality < district < region';
COMMENT ON COLUMN district.A6 IS 'municipality < district < region';
COMMENT ON COLUMN district.A7 IS 'municipality < district < region';
COMMENT ON COLUMN district.A8 IS 'municipality < district < region';
ALTER TABLE district MODIFY (A9 ANNOTATIONS (ADD value_description 'not useful'));
COMMENT ON COLUMN district.A10 IS 'ratio of urban inhabitants';
COMMENT ON COLUMN district.A11 IS 'average salary';
COMMENT ON COLUMN district.A12 IS 'unemployment rate 1995';
COMMENT ON COLUMN district.A13 IS 'unemployment rate 1996';
COMMENT ON COLUMN district.A14 IS 'no. of entrepreneurs per 1000 inhabitants';
COMMENT ON COLUMN district.A15 IS 'no. of committed crimes 1995';
COMMENT ON COLUMN district.A16 IS 'no. of committed crimes 1996';

COMMENT ON COLUMN loan.loan_id IS 'the id number identifying the loan data';
COMMENT ON COLUMN loan.account_id IS 'the id number identifying the account';
COMMENT ON COLUMN loan."date" IS 'the date when the loan is approved';
COMMENT ON COLUMN loan.amount IS 'approved amount';
ALTER TABLE loan MODIFY (amount ANNOTATIONS (ADD value_description 'unit：US dollar'));
COMMENT ON COLUMN loan.duration IS 'loan duration';
ALTER TABLE loan MODIFY (duration ANNOTATIONS (ADD value_description 'unit：month'));
COMMENT ON COLUMN loan.payments IS 'monthly payments';
ALTER TABLE loan MODIFY (payments ANNOTATIONS (ADD value_description 'unit：month'));
COMMENT ON COLUMN loan."status" IS 'repayment status';
ALTER TABLE loan MODIFY ("status" ANNOTATIONS (ADD value_description '''A'' stands for contract finished, no problems;''B'' stands for contract finished, loan not paid;''C'' stands for running contract, OK so far;''D'' stands for running contract, client in debt'));

COMMENT ON COLUMN "order".order_id IS 'identifying the unique order';
COMMENT ON COLUMN "order".account_id IS 'id number of account';
COMMENT ON COLUMN "order".bank_to IS 'bank of the recipient';
COMMENT ON COLUMN "order".account_to IS 'account of the recipient';
ALTER TABLE "order" MODIFY (account_to ANNOTATIONS (ADD value_description 'each bank has unique two-letter code'));
COMMENT ON COLUMN "order".amount IS 'debited amount';
COMMENT ON COLUMN "order".k_symbol IS 'purpose of the payment';
ALTER TABLE "order" MODIFY (k_symbol ANNOTATIONS (ADD value_description '"POJISTNE" stands for insurance payment"SIPO" stands for household payment"LEASING" stands for leasing"UVER" stands for loan payment'));

COMMENT ON COLUMN trans.trans_id IS 'transaction id';
COMMENT ON COLUMN trans."date" IS 'date of transaction';
COMMENT ON COLUMN trans."type" IS '+/- transaction';
ALTER TABLE trans MODIFY ("type" ANNOTATIONS (ADD value_description '"PRIJEM" stands for credit"VYDAJ" stands for withdrawal'));
COMMENT ON COLUMN trans.operation IS 'mode of transaction';
ALTER TABLE trans MODIFY (operation ANNOTATIONS (ADD value_description '"VYBER KARTOU": credit card withdrawal"VKLAD": credit in cash"PREVOD Z UCTU" :collection from another bank"VYBER": withdrawal in cash"PREVOD NA UCET": remittance to another bank'));
COMMENT ON COLUMN trans.amount IS 'amount of money';
ALTER TABLE trans MODIFY (amount ANNOTATIONS (ADD value_description 'Unit：USD'));
COMMENT ON COLUMN trans.balance IS 'balance after transaction';
ALTER TABLE trans MODIFY (balance ANNOTATIONS (ADD value_description 'Unit：USD'));
ALTER TABLE trans MODIFY (k_symbol ANNOTATIONS (ADD value_description '"POJISTNE": stands for insurrance payment"SLUZBY": stands for payment for statement"UROK": stands for interest credited"SANKC. UROK": sanction interest if negative balance"SIPO": stands for household"DUCHOD": stands for old-age pension"UVER": stands for loan payment'));
ALTER TABLE trans MODIFY (bank ANNOTATIONS (ADD value_description 'each bank has unique two-letter code'));
