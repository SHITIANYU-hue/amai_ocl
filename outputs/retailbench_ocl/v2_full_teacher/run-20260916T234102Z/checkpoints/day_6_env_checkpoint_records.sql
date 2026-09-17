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
INSERT INTO "supplier_orders" VALUES(1,'supplier_4','1991-09-08','1991-09-14',6,5045.859,'{"3828111129": 5000, "3700060511": 3000, "4200013000": 2000}','2026-09-16 23:44:12');
CREATE TABLE supplier_prices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    supplier_id TEXT NOT NULL,
                    sku_id TEXT NOT NULL,
                    date TEXT NOT NULL,
                    price REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
INSERT INTO "supplier_prices" VALUES(1,'supplier_1','3700060511','1991-09-07',0.810322,'2026-09-16 23:42:16');
INSERT INTO "supplier_prices" VALUES(2,'supplier_2','3700060511','1991-09-07',0.587014,'2026-09-16 23:42:16');
INSERT INTO "supplier_prices" VALUES(3,'supplier_3','3700060511','1991-09-07',0.828868,'2026-09-16 23:42:16');
INSERT INTO "supplier_prices" VALUES(4,'supplier_4','3700060511','1991-09-07',0.505728,'2026-09-16 23:42:16');
INSERT INTO "supplier_prices" VALUES(5,'supplier_5','3700060511','1991-09-07',0.838156,'2026-09-16 23:42:16');
INSERT INTO "supplier_prices" VALUES(6,'supplier_1','3828111129','1991-09-07',0.684598,'2026-09-16 23:42:16');
INSERT INTO "supplier_prices" VALUES(7,'supplier_2','3828111129','1991-09-07',0.758691,'2026-09-16 23:42:16');
INSERT INTO "supplier_prices" VALUES(8,'supplier_3','3828111129','1991-09-07',0.485311,'2026-09-16 23:42:16');
INSERT INTO "supplier_prices" VALUES(9,'supplier_4','3828111129','1991-09-07',0.50598,'2026-09-16 23:42:16');
INSERT INTO "supplier_prices" VALUES(10,'supplier_5','3828111129','1991-09-07',0.761008,'2026-09-16 23:42:16');
INSERT INTO "supplier_prices" VALUES(11,'supplier_1','4200013000','1991-09-07',0.976901,'2026-09-16 23:42:16');
INSERT INTO "supplier_prices" VALUES(12,'supplier_2','4200013000','1991-09-07',1.007643,'2026-09-16 23:42:16');
INSERT INTO "supplier_prices" VALUES(13,'supplier_3','4200013000','1991-09-07',0.754891,'2026-09-16 23:42:16');
INSERT INTO "supplier_prices" VALUES(14,'supplier_4','4200013000','1991-09-07',0.579904,'2026-09-16 23:42:16');
INSERT INTO "supplier_prices" VALUES(15,'supplier_5','4200013000','1991-09-07',0.917356,'2026-09-16 23:42:16');
INSERT INTO "supplier_prices" VALUES(16,'supplier_1','3700060511','1991-09-08',0.733803,'2026-09-16 23:44:17');
INSERT INTO "supplier_prices" VALUES(17,'supplier_2','3700060511','1991-09-08',0.584743,'2026-09-16 23:44:17');
INSERT INTO "supplier_prices" VALUES(18,'supplier_3','3700060511','1991-09-08',0.820929,'2026-09-16 23:44:17');
INSERT INTO "supplier_prices" VALUES(19,'supplier_4','3700060511','1991-09-08',0.528409,'2026-09-16 23:44:17');
INSERT INTO "supplier_prices" VALUES(20,'supplier_5','3700060511','1991-09-08',0.823529,'2026-09-16 23:44:17');
INSERT INTO "supplier_prices" VALUES(21,'supplier_1','3828111129','1991-09-08',0.691592,'2026-09-16 23:44:17');
INSERT INTO "supplier_prices" VALUES(22,'supplier_2','3828111129','1991-09-08',0.755779,'2026-09-16 23:44:17');
INSERT INTO "supplier_prices" VALUES(23,'supplier_3','3828111129','1991-09-08',0.456274,'2026-09-16 23:44:17');
INSERT INTO "supplier_prices" VALUES(24,'supplier_4','3828111129','1991-09-08',0.44785,'2026-09-16 23:44:17');
INSERT INTO "supplier_prices" VALUES(25,'supplier_5','3828111129','1991-09-08',0.746842,'2026-09-16 23:44:17');
INSERT INTO "supplier_prices" VALUES(26,'supplier_1','4200013000','1991-09-08',0.964878,'2026-09-16 23:44:17');
INSERT INTO "supplier_prices" VALUES(27,'supplier_2','4200013000','1991-09-08',0.983338,'2026-09-16 23:44:17');
INSERT INTO "supplier_prices" VALUES(28,'supplier_3','4200013000','1991-09-08',0.713489,'2026-09-16 23:44:17');
INSERT INTO "supplier_prices" VALUES(29,'supplier_4','4200013000','1991-09-08',0.610691,'2026-09-16 23:44:17');
INSERT INTO "supplier_prices" VALUES(30,'supplier_5','4200013000','1991-09-08',0.901095,'2026-09-16 23:44:17');
INSERT INTO "supplier_prices" VALUES(31,'supplier_1','3700060511','1991-09-09',0.796556,'2026-09-16 23:45:54');
INSERT INTO "supplier_prices" VALUES(32,'supplier_2','3700060511','1991-09-09',0.593954,'2026-09-16 23:45:54');
INSERT INTO "supplier_prices" VALUES(33,'supplier_3','3700060511','1991-09-09',0.811284,'2026-09-16 23:45:54');
INSERT INTO "supplier_prices" VALUES(34,'supplier_4','3700060511','1991-09-09',0.534076,'2026-09-16 23:45:54');
INSERT INTO "supplier_prices" VALUES(35,'supplier_5','3700060511','1991-09-09',0.84267,'2026-09-16 23:45:54');
INSERT INTO "supplier_prices" VALUES(36,'supplier_1','3828111129','1991-09-09',0.682314,'2026-09-16 23:45:54');
INSERT INTO "supplier_prices" VALUES(37,'supplier_2','3828111129','1991-09-09',0.750874,'2026-09-16 23:45:54');
INSERT INTO "supplier_prices" VALUES(38,'supplier_3','3828111129','1991-09-09',0.513303,'2026-09-16 23:45:54');
INSERT INTO "supplier_prices" VALUES(39,'supplier_4','3828111129','1991-09-09',0.482195,'2026-09-16 23:45:54');
INSERT INTO "supplier_prices" VALUES(40,'supplier_5','3828111129','1991-09-09',0.760036,'2026-09-16 23:45:54');
INSERT INTO "supplier_prices" VALUES(41,'supplier_1','4200013000','1991-09-09',0.998913,'2026-09-16 23:45:54');
INSERT INTO "supplier_prices" VALUES(42,'supplier_2','4200013000','1991-09-09',0.997673,'2026-09-16 23:45:54');
INSERT INTO "supplier_prices" VALUES(43,'supplier_3','4200013000','1991-09-09',0.673038,'2026-09-16 23:45:54');
INSERT INTO "supplier_prices" VALUES(44,'supplier_4','4200013000','1991-09-09',0.593191,'2026-09-16 23:45:54');
INSERT INTO "supplier_prices" VALUES(45,'supplier_5','4200013000','1991-09-09',0.904034,'2026-09-16 23:45:54');
INSERT INTO "supplier_prices" VALUES(46,'supplier_1','3700060511','1991-09-10',0.772227,'2026-09-16 23:47:41');
INSERT INTO "supplier_prices" VALUES(47,'supplier_2','3700060511','1991-09-10',0.565391,'2026-09-16 23:47:41');
INSERT INTO "supplier_prices" VALUES(48,'supplier_3','3700060511','1991-09-10',0.816648,'2026-09-16 23:47:41');
INSERT INTO "supplier_prices" VALUES(49,'supplier_4','3700060511','1991-09-10',0.481839,'2026-09-16 23:47:41');
INSERT INTO "supplier_prices" VALUES(50,'supplier_5','3700060511','1991-09-10',0.826039,'2026-09-16 23:47:41');
INSERT INTO "supplier_prices" VALUES(51,'supplier_1','3828111129','1991-09-10',0.682455,'2026-09-16 23:47:41');
INSERT INTO "supplier_prices" VALUES(52,'supplier_2','3828111129','1991-09-10',0.743279,'2026-09-16 23:47:41');
INSERT INTO "supplier_prices" VALUES(53,'supplier_3','3828111129','1991-09-10',0.499399,'2026-09-16 23:47:41');
INSERT INTO "supplier_prices" VALUES(54,'supplier_4','3828111129','1991-09-10',0.447297,'2026-09-16 23:47:41');
INSERT INTO "supplier_prices" VALUES(55,'supplier_5','3828111129','1991-09-10',0.768231,'2026-09-16 23:47:41');
INSERT INTO "supplier_prices" VALUES(56,'supplier_1','4200013000','1991-09-10',0.975098,'2026-09-16 23:47:41');
INSERT INTO "supplier_prices" VALUES(57,'supplier_2','4200013000','1991-09-10',0.994054,'2026-09-16 23:47:41');
INSERT INTO "supplier_prices" VALUES(58,'supplier_3','4200013000','1991-09-10',0.694048,'2026-09-16 23:47:41');
INSERT INTO "supplier_prices" VALUES(59,'supplier_4','4200013000','1991-09-10',0.612785,'2026-09-16 23:47:41');
INSERT INTO "supplier_prices" VALUES(60,'supplier_5','4200013000','1991-09-10',0.895944,'2026-09-16 23:47:41');
INSERT INTO "supplier_prices" VALUES(61,'supplier_1','3700060511','1991-09-11',0.758225,'2026-09-16 23:48:53');
INSERT INTO "supplier_prices" VALUES(62,'supplier_2','3700060511','1991-09-11',0.612539,'2026-09-16 23:48:53');
INSERT INTO "supplier_prices" VALUES(63,'supplier_3','3700060511','1991-09-11',0.804971,'2026-09-16 23:48:53');
INSERT INTO "supplier_prices" VALUES(64,'supplier_4','3700060511','1991-09-11',0.495256,'2026-09-16 23:48:53');
INSERT INTO "supplier_prices" VALUES(65,'supplier_5','3700060511','1991-09-11',0.811559,'2026-09-16 23:48:53');
INSERT INTO "supplier_prices" VALUES(66,'supplier_1','3828111129','1991-09-11',0.707447,'2026-09-16 23:48:53');
INSERT INTO "supplier_prices" VALUES(67,'supplier_2','3828111129','1991-09-11',0.747815,'2026-09-16 23:48:53');
INSERT INTO "supplier_prices" VALUES(68,'supplier_3','3828111129','1991-09-11',0.509006,'2026-09-16 23:48:53');
INSERT INTO "supplier_prices" VALUES(69,'supplier_4','3828111129','1991-09-11',0.492521,'2026-09-16 23:48:53');
INSERT INTO "supplier_prices" VALUES(70,'supplier_5','3828111129','1991-09-11',0.762428,'2026-09-16 23:48:53');
INSERT INTO "supplier_prices" VALUES(71,'supplier_1','4200013000','1991-09-11',0.989251,'2026-09-16 23:48:53');
INSERT INTO "supplier_prices" VALUES(72,'supplier_2','4200013000','1991-09-11',0.97353,'2026-09-16 23:48:53');
INSERT INTO "supplier_prices" VALUES(73,'supplier_3','4200013000','1991-09-11',0.711409,'2026-09-16 23:48:53');
INSERT INTO "supplier_prices" VALUES(74,'supplier_4','4200013000','1991-09-11',0.570645,'2026-09-16 23:48:53');
INSERT INTO "supplier_prices" VALUES(75,'supplier_5','4200013000','1991-09-11',0.914633,'2026-09-16 23:48:53');
INSERT INTO "supplier_prices" VALUES(76,'supplier_1','3700060511','1991-09-12',0.730619,'2026-09-16 23:50:07');
INSERT INTO "supplier_prices" VALUES(77,'supplier_2','3700060511','1991-09-12',0.604324,'2026-09-16 23:50:07');
INSERT INTO "supplier_prices" VALUES(78,'supplier_3','3700060511','1991-09-12',0.787769,'2026-09-16 23:50:07');
INSERT INTO "supplier_prices" VALUES(79,'supplier_4','3700060511','1991-09-12',0.515778,'2026-09-16 23:50:07');
INSERT INTO "supplier_prices" VALUES(80,'supplier_5','3700060511','1991-09-12',0.781593,'2026-09-16 23:50:07');
INSERT INTO "supplier_prices" VALUES(81,'supplier_1','3828111129','1991-09-12',0.734725,'2026-09-16 23:50:07');
INSERT INTO "supplier_prices" VALUES(82,'supplier_2','3828111129','1991-09-12',0.764611,'2026-09-16 23:50:07');
INSERT INTO "supplier_prices" VALUES(83,'supplier_3','3828111129','1991-09-12',0.4967,'2026-09-16 23:50:07');
INSERT INTO "supplier_prices" VALUES(84,'supplier_4','3828111129','1991-09-12',0.496126,'2026-09-16 23:50:07');
INSERT INTO "supplier_prices" VALUES(85,'supplier_5','3828111129','1991-09-12',0.744109,'2026-09-16 23:50:07');
INSERT INTO "supplier_prices" VALUES(86,'supplier_1','4200013000','1991-09-12',0.954161,'2026-09-16 23:50:07');
INSERT INTO "supplier_prices" VALUES(87,'supplier_2','4200013000','1991-09-12',0.974262,'2026-09-16 23:50:07');
INSERT INTO "supplier_prices" VALUES(88,'supplier_3','4200013000','1991-09-12',0.741024,'2026-09-16 23:50:07');
INSERT INTO "supplier_prices" VALUES(89,'supplier_4','4200013000','1991-09-12',0.633646,'2026-09-16 23:50:07');
INSERT INTO "supplier_prices" VALUES(90,'supplier_5','4200013000','1991-09-12',0.915542,'2026-09-16 23:50:07');
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
INSERT INTO "sqlite_sequence" VALUES('supplier_prices',90);
INSERT INTO "sqlite_sequence" VALUES('supplier_orders',1);
COMMIT;
