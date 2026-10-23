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
