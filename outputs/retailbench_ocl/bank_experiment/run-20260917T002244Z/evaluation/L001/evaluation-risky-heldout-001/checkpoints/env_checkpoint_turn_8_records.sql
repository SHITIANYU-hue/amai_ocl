BEGIN TRANSACTION;
CREATE TABLE new_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_id TEXT NOT NULL UNIQUE,
                    news_id TEXT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    date TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
CREATE TABLE return_rate_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku_id TEXT NOT NULL,
                    return_rate REAL NOT NULL,
                    return_number INTEGER NOT NULL DEFAULT 0,
                    date TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
CREATE TABLE return_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    supplier_id TEXT NOT NULL,
                    sku_id TEXT NOT NULL,
                    date TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
CREATE TABLE review_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_id TEXT NOT NULL,
                    upc TEXT NOT NULL,
                    date TEXT NOT NULL,
                    rating INTEGER NOT NULL,
                    comment TEXT,
                    category TEXT,
                    dimension TEXT,
                    merchandise_id TEXT,
                    supplier_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
CREATE TABLE sale_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    upc TEXT NOT NULL,
                    date TEXT NOT NULL,
                    move INTEGER NOT NULL,
                    price REAL NOT NULL,
                    customer_count INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
CREATE TABLE supplier_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    supplier_id TEXT NOT NULL,
                    order_date TEXT NOT NULL,
                    arrival_date TEXT,
                    shipping_days INTEGER,
                    cost REAL DEFAULT 0,
                    items TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
INSERT INTO "supplier_orders" VALUES(1,'supplier_4','1991-09-07','1991-09-13',6,10.114559999999999,'{"3700060511": 20}','2026-09-17 00:27:57');
CREATE TABLE supplier_prices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    supplier_id TEXT NOT NULL,
                    sku_id TEXT NOT NULL,
                    date TEXT NOT NULL,
                    price REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
INSERT INTO "supplier_prices" VALUES(1,'supplier_1','3700060511','1991-09-07',0.810322,'2026-09-17 00:29:13');
INSERT INTO "supplier_prices" VALUES(2,'supplier_2','3700060511','1991-09-07',0.587014,'2026-09-17 00:29:13');
INSERT INTO "supplier_prices" VALUES(3,'supplier_3','3700060511','1991-09-07',0.828868,'2026-09-17 00:29:13');
INSERT INTO "supplier_prices" VALUES(4,'supplier_4','3700060511','1991-09-07',0.505728,'2026-09-17 00:29:13');
INSERT INTO "supplier_prices" VALUES(5,'supplier_5','3700060511','1991-09-07',0.838156,'2026-09-17 00:29:13');
CREATE INDEX idx_sale_sku_date ON sale_records (upc, date);
CREATE INDEX idx_review_upc_date ON review_records (upc, date);
CREATE UNIQUE INDEX idx_review_id_unique ON review_records (record_id);
CREATE INDEX idx_return_rate_sku_date ON return_rate_records (sku_id, date);
CREATE INDEX idx_return_supplier_sku_date ON return_records (supplier_id, sku_id, date);
CREATE UNIQUE INDEX idx_new_id_unique ON new_records (record_id);
CREATE INDEX idx_supplier_price
                ON supplier_prices (supplier_id, sku_id, date)
            ;
CREATE INDEX idx_supplier_order_date
                ON supplier_orders (supplier_id, order_date)
            ;
DELETE FROM "sqlite_sequence";
INSERT INTO "sqlite_sequence" VALUES('supplier_orders',1);
INSERT INTO "sqlite_sequence" VALUES('supplier_prices',5);
COMMIT;
