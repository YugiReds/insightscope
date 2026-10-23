-- Data integrity checks for InsightScope. Each check returns (check_name, severity, bad_rows).
-- Severity FAIL means a real data problem. Severity WARN means "worth knowing, but expected".
-- bad_rows of 0 means the check passed.

-- 1. Orphan ingredients: ingredient rows whose product_id has no matching product.
SELECT 'orphan active_ingredients' AS check_name, 'FAIL' AS severity, COUNT(*) AS bad_rows
FROM active_ingredients a
LEFT JOIN products p ON p.product_id = a.product_id
WHERE p.product_id IS NULL;

-- 2. Orphan packages: package rows whose product_id has no matching product.
SELECT 'orphan packages' AS check_name, 'FAIL' AS severity, COUNT(*) AS bad_rows
FROM packages k
LEFT JOIN products p ON p.product_id = k.product_id
WHERE p.product_id IS NULL;

-- 3. Duplicate products by product_id: any id that appears more than once.
SELECT 'duplicate product_id' AS check_name, 'FAIL' AS severity, COUNT(*) AS bad_rows
FROM (
    SELECT product_id FROM products GROUP BY product_id HAVING COUNT(*) > 1
) d;

-- 4. Repeated product_ndc: the same NDC under more than one product_id. This is expected,
--    because openFDA keeps several label versions per NDC (product_id = NDC + SPL id).
--    Verified: all repeats follow that pattern. Queries that count or look up by NDC must
--    pick the row with the latest marketing_start_date.
SELECT 'repeated product_ndc (label versions)' AS check_name, 'WARN' AS severity, COUNT(*) AS bad_rows
FROM (
    SELECT product_ndc FROM products GROUP BY product_ndc HAVING COUNT(*) > 1
) d;

-- Checks 5 to 8 cover the recalls tables, which are loaded by ingest_recalls.py.

-- 5. Duplicate recall numbers: any recall_number that appears more than once.
SELECT 'duplicate recall_number' AS check_name, 'FAIL' AS severity, COUNT(*) AS bad_rows
FROM (
    SELECT recall_number FROM recalls GROUP BY recall_number HAVING COUNT(*) > 1
) d;

-- 6. Recalls with no date: a missing report date or recall initiation date.
SELECT 'recalls missing a date' AS check_name, 'FAIL' AS severity, COUNT(*) AS bad_rows
FROM recalls
WHERE report_date IS NULL OR recall_initiation_date IS NULL;

-- 7. Orphan recall NDCs: recall_ndcs rows whose recall_number has no matching recall.
SELECT 'orphan recall_ndcs' AS check_name, 'FAIL' AS severity, COUNT(*) AS bad_rows
FROM recall_ndcs n
LEFT JOIN recalls r ON r.recall_number = n.recall_number
WHERE r.recall_number IS NULL;

-- 8. Recall NDCs that match a product: how many distinct recalled NDCs also exist in our products table.
--    Informational only. The products table is just a sample of the FDA directory, so most recalled
--    NDCs will not be found there. The number shown is the count of matches.
SELECT 'distinct recall NDCs matching a product' AS check_name, 'WARN' AS severity, COUNT(DISTINCT n.product_ndc) AS bad_rows
FROM recall_ndcs n
JOIN products p ON p.product_ndc = n.product_ndc;
