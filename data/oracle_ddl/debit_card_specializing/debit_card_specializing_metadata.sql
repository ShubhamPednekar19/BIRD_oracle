COMMENT ON COLUMN customers.CustomerID IS 'identification of the customer';
COMMENT ON COLUMN customers."Segment" IS 'client segment';
COMMENT ON COLUMN customers.Currency IS 'Currency';

COMMENT ON COLUMN gasstations.GasStationID IS 'Gas Station ID';
COMMENT ON COLUMN gasstations.ChainID IS 'Chain ID';
COMMENT ON COLUMN gasstations."Segment" IS 'chain segment';

COMMENT ON COLUMN products.ProductID IS 'Product ID';
COMMENT ON COLUMN products.Description IS 'Description';

COMMENT ON COLUMN transactions_1k.TransactionID IS 'Transaction ID';
COMMENT ON COLUMN transactions_1k."Date" IS 'Date';
COMMENT ON COLUMN transactions_1k."Time" IS 'Time';
COMMENT ON COLUMN transactions_1k.CustomerID IS 'Customer ID';
COMMENT ON COLUMN transactions_1k.CardID IS 'Card ID';
COMMENT ON COLUMN transactions_1k.GasStationID IS 'Gas Station ID';
COMMENT ON COLUMN transactions_1k.ProductID IS 'Product ID';
COMMENT ON COLUMN transactions_1k.Amount IS 'Amount';
COMMENT ON COLUMN transactions_1k.Price IS 'Price';
ALTER TABLE transactions_1k MODIFY (Price ANNOTATIONS (ADD value_description 'commonsense evidence:total price = Amount x Price'));

COMMENT ON COLUMN yearmonth.CustomerID IS 'Customer ID';
COMMENT ON COLUMN yearmonth."Date" IS 'Date';
COMMENT ON COLUMN yearmonth.Consumption IS 'consumption';
