# SQL Warehouse Scripts

This folder contains the reproducible MySQL warehouse build scripts.

## What To Run

Run these in MySQL Workbench when rebuilding the warehouse:

1. `build/01_create_portugal_rental_warehouse_lean.sql`
2. `build/02_load_portugal_rental_warehouse_lean_v3.sql`
3. `validation/03_validate_portugal_rental_warehouse_lean.sql`
4. `build/04_build_gold_bi_extensions_v14.sql`
5. `validation/05_validate_gold_bi_extensions_v14.sql`

## Folder Purpose

- `build`: required schema, data-load, and BI/gold-layer build scripts.
- `validation`: row-count and BI-layer QA checks.
- `maintenance`: destructive reset scripts. Use only when intentionally rebuilding from scratch.

## Notes

- The large `02_load...sql` file is needed only if we want to recreate/populate MySQL from the exported package.
- The `00_drop...sql` file is intentionally isolated in `maintenance` because it drops the database.
- The old install markdown was removed because this README now contains the run order.
- `v14` is the current BI/gold extension version. It adds five financing scenarios per market type and a financial distribution mart for median, percentile, and top-performer dashboard analysis.
- If MySQL Workbench returns `Error Code: 2013` after exactly 30 seconds, increase `Edit > Preferences > SQL Editor > DBMS connection read timeout interval` to `600`, reconnect, and rerun `v14`.
