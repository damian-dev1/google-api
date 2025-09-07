PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

DROP VIEW IF EXISTS vw_ps_product_info;
DROP VIEW IF EXISTS vw_product_catalog;

CREATE TABLE IF NOT EXISTS attribute_groups (
  group_id   INTEGER PRIMARY KEY,
  name       TEXT NOT NULL,
  sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS attributes (
  attribute_id INTEGER PRIMARY KEY,
  code         TEXT NOT NULL UNIQUE,
  label        TEXT NOT NULL,
  data_type    TEXT NOT NULL CHECK (data_type IN ('text','int','decimal','bool','date','enum','json')),
  unit_code    TEXT,
  is_variant   INTEGER NOT NULL DEFAULT 0 CHECK (is_variant IN (0,1)),
  is_required  INTEGER NOT NULL DEFAULT 0 CHECK (is_required IN (0,1)),
  is_facet     INTEGER NOT NULL DEFAULT 1 CHECK (is_facet IN (0,1)),
  group_id     INTEGER REFERENCES attribute_groups(group_id) ON UPDATE CASCADE ON DELETE SET NULL,
  sort_order   INTEGER DEFAULT 0,
  created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS attribute_options (
  option_id    INTEGER PRIMARY KEY,
  attribute_id INTEGER NOT NULL REFERENCES attributes(attribute_id) ON UPDATE CASCADE ON DELETE CASCADE,
  value        TEXT NOT NULL,
  label        TEXT,
  sort_order   INTEGER DEFAULT 0,
  UNIQUE(attribute_id, value)
);

CREATE TABLE IF NOT EXISTS brands (
  brand_id   INTEGER PRIMARY KEY,
  brand_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS categories (
  category_id INTEGER PRIMARY KEY,
  code        TEXT UNIQUE,
  name        TEXT NOT NULL,
  parent_id   INTEGER REFERENCES categories(category_id) ON UPDATE CASCADE ON DELETE SET NULL,
  gcc_code    TEXT,
  created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS category_attributes (
  category_id  INTEGER NOT NULL REFERENCES categories(category_id) ON UPDATE CASCADE ON DELETE CASCADE,
  attribute_id INTEGER NOT NULL REFERENCES attributes(attribute_id) ON UPDATE CASCADE ON DELETE CASCADE,
  is_required  INTEGER NOT NULL DEFAULT 0 CHECK (is_required IN (0,1)),
  sort_order   INTEGER DEFAULT 0,
  PRIMARY KEY (category_id, attribute_id)
);

CREATE TABLE IF NOT EXISTS dimensions (
  dimension_id            INTEGER PRIMARY KEY,
  product_height_cm       REAL NOT NULL CHECK (product_height_cm >= 0),
  product_width_cm        REAL NOT NULL CHECK (product_width_cm  >= 0),
  product_depth_cm        REAL NOT NULL CHECK (product_depth_cm  >= 0),
  package_height_cm       REAL CHECK (package_height_cm  >= 0),
  package_width_cm        REAL CHECK (package_width_cm   >= 0),
  package_depth_cm        REAL CHECK (package_depth_cm   >= 0),
  package_gross_weight_kg REAL CHECK (package_gross_weight_kg >= 0)
);

CREATE TABLE IF NOT EXISTS warranty (
  warranty_id     INTEGER PRIMARY KEY,
  duration_months INTEGER NOT NULL CHECK (duration_months >= 0),
  warranty_type_code TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vendors (
  vendor_id               INTEGER PRIMARY KEY AUTOINCREMENT,
  legal_entity_name       TEXT NOT NULL,
  trading_name            TEXT,
  account_reference       TEXT,
  sap_supplier_id         TEXT,
  vendor_status           TEXT,
  product_category        TEXT,
  contact_person_name     TEXT,
  contact_email           TEXT,
  contact_phone           TEXT,
  website_url             TEXT,
  street_address          TEXT,
  postal_code             TEXT,
  city                    TEXT,
  state_province_region   TEXT,
  country_code            CHAR(2),
  abn                     TEXT,
  acn                     TEXT,
  vat_number              TEXT,
  eori_number             TEXT,
  tax_residency_country   CHAR(2),
  payment_terms           TEXT,
  incoterms               TEXT,
  freight_matrix          TEXT,
  currency_code           CHAR(3),
  platform_name           TEXT,
  api_integration_status  TEXT,
  vendor_manager_name     TEXT,
  onboarding_source       TEXT,
  created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products (
  part_number                 TEXT PRIMARY KEY,
  sap_article_id              INTEGER UNIQUE,
  barcode                     TEXT UNIQUE,
  model_code                  TEXT,
  brand_id                    INTEGER NOT NULL REFERENCES brands(brand_id) ON UPDATE CASCADE ON DELETE RESTRICT,
  other_brand_name            TEXT,
  short_description           TEXT,
  secondary_short_description TEXT,
  full_description            TEXT,
  main_colour_name            TEXT,
  suitable_age_range          TEXT,
  sports_size_code            TEXT,
  country_of_origin_code      CHAR(2),
  supplier_comments           TEXT,
  primary_category_id         INTEGER REFERENCES categories(category_id) ON UPDATE CASCADE ON DELETE SET NULL,
  warranty_id                 INTEGER REFERENCES warranty(warranty_id) ON UPDATE CASCADE ON DELETE SET NULL,
  dimension_id                INTEGER REFERENCES dimensions(dimension_id) ON UPDATE CASCADE ON DELETE SET NULL,
  vendor_id                   INTEGER REFERENCES vendors(vendor_id) ON UPDATE CASCADE ON DELETE SET NULL,
  created_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CHECK (length(part_number) > 0)
);

CREATE TABLE IF NOT EXISTS product_media (
  media_id    INTEGER PRIMARY KEY,
  part_number TEXT NOT NULL REFERENCES products(part_number) ON UPDATE CASCADE ON DELETE CASCADE,
  media_type  TEXT NOT NULL CHECK (media_type IN ('image','video','youtube')),
  url         TEXT NOT NULL,
  alt_text    TEXT,
  position    INTEGER DEFAULT 0,
  created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS prices (
  price_id           INTEGER PRIMARY KEY AUTOINCREMENT,
  part_number        TEXT NOT NULL REFERENCES products(part_number) ON UPDATE CASCADE ON DELETE CASCADE,
  currency_code      CHAR(3) DEFAULT 'AUD',
  msrp               NUMERIC,
  rrp                NUMERIC,
  retail_price       NUMERIC NOT NULL CHECK (retail_price >= 0),
  discount_price     NUMERIC,
  cost_price_ex_tax  NUMERIC,
  effective_date     DATE NOT NULL,
  created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (part_number, effective_date)
);

CREATE TABLE IF NOT EXISTS pack_contents (
  pack_content_id  INTEGER PRIMARY KEY AUTOINCREMENT,
  part_number      TEXT NOT NULL REFERENCES products(part_number) ON UPDATE CASCADE ON DELETE CASCADE,
  item_description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS product_attribute_values (
  part_number   TEXT NOT NULL REFERENCES products(part_number) ON UPDATE CASCADE ON DELETE CASCADE,
  attribute_id  INTEGER NOT NULL REFERENCES attributes(attribute_id) ON UPDATE CASCADE ON DELETE CASCADE,
  value_text    TEXT,
  value_int     INTEGER,
  value_decimal NUMERIC,
  value_bool    INTEGER CHECK (value_bool IN (0,1)),
  value_date    DATE,
  value_json    TEXT,
  option_id     INTEGER REFERENCES attribute_options(option_id) ON UPDATE CASCADE ON DELETE SET NULL,
  unit_code     TEXT,
  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (part_number, attribute_id),
  CHECK (
    (value_text IS NOT NULL) +
    (value_int IS NOT NULL) +
    (value_decimal IS NOT NULL) +
    (value_bool IS NOT NULL) +
    (value_date IS NOT NULL) +
    (value_json IS NOT NULL) +
    (option_id IS NOT NULL) = 1
  )
);

CREATE TABLE IF NOT EXISTS product_categories (
  part_number TEXT NOT NULL REFERENCES products(part_number) ON UPDATE CASCADE ON DELETE CASCADE,
  category_id INTEGER NOT NULL REFERENCES categories(category_id) ON UPDATE CASCADE ON DELETE CASCADE,
  PRIMARY KEY (part_number, category_id)
);

CREATE TABLE IF NOT EXISTS product_variants (
  variant_part_number TEXT PRIMARY KEY REFERENCES products(part_number) ON UPDATE CASCADE ON DELETE CASCADE,
  parent_part_number  TEXT NOT NULL REFERENCES products(part_number) ON UPDATE CASCADE ON DELETE CASCADE,
  UNIQUE (variant_part_number, parent_part_number)
);

CREATE TABLE IF NOT EXISTS purchase_orders (
  po_id                   INTEGER PRIMARY KEY AUTOINCREMENT,
  vendor_id               INTEGER NOT NULL REFERENCES vendors(vendor_id) ON UPDATE CASCADE ON DELETE RESTRICT,
  po_number               TEXT UNIQUE NOT NULL,
  order_date              DATE NOT NULL,
  expected_delivery_date  DATE,
  incoterms               TEXT,
  currency_code           CHAR(3),
  total_amount            NUMERIC NOT NULL,
  payment_terms           TEXT,
  shipping_method         TEXT,
  shipping_address        TEXT,
  billing_address         TEXT,
  status                  TEXT DEFAULT 'Pending',
  created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS shipments (
  shipment_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  po_id             INTEGER NOT NULL REFERENCES purchase_orders(po_id) ON UPDATE CASCADE ON DELETE CASCADE,
  shipment_date     DATE NOT NULL,
  carrier_name      TEXT,
  tracking_number   TEXT,
  incoterms         TEXT,
  shipment_status   TEXT DEFAULT 'In Transit',
  estimated_arrival DATE,
  actual_arrival    DATE
);

CREATE TABLE IF NOT EXISTS shipment_tracking (
  tracking_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
  shipment_id       INTEGER NOT NULL REFERENCES shipments(shipment_id) ON UPDATE CASCADE ON DELETE CASCADE,
  event_timestamp   TIMESTAMP NOT NULL,
  location          TEXT,
  status_update     TEXT
);

CREATE TABLE IF NOT EXISTS invoices (
  invoice_id          INTEGER PRIMARY KEY AUTOINCREMENT,
  vendor_id           INTEGER NOT NULL REFERENCES vendors(vendor_id) ON UPDATE CASCADE ON DELETE RESTRICT,
  po_id               INTEGER REFERENCES purchase_orders(po_id) ON UPDATE CASCADE ON DELETE SET NULL,
  invoice_number      TEXT UNIQUE NOT NULL,
  invoice_date        DATE NOT NULL,
  due_date            DATE,
  currency_code       CHAR(3),
  subtotal_amount     NUMERIC NOT NULL,
  tax_amount          NUMERIC,
  vat_number          TEXT,
  total_amount        NUMERIC NOT NULL,
  payment_status      TEXT DEFAULT 'Unpaid',
  payment_method      TEXT,
  remittance_reference TEXT,
  created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS po_line_items (
  line_item_id     INTEGER PRIMARY KEY AUTOINCREMENT,
  po_id            INTEGER NOT NULL REFERENCES purchase_orders(po_id) ON UPDATE CASCADE ON DELETE CASCADE,
  product_sku      TEXT NOT NULL,
  description      TEXT,
  quantity_ordered INTEGER NOT NULL CHECK (quantity_ordered >= 0),
  unit_price       NUMERIC NOT NULL CHECK (unit_price >= 0),
  currency_code    CHAR(3),
  total_price      NUMERIC GENERATED ALWAYS AS (quantity_ordered * unit_price) STORED
);

CREATE TABLE IF NOT EXISTS invoice_line_items (
  line_item_id     INTEGER PRIMARY KEY AUTOINCREMENT,
  invoice_id       INTEGER NOT NULL REFERENCES invoices(invoice_id) ON UPDATE CASCADE ON DELETE CASCADE,
  product_sku      TEXT NOT NULL,
  description      TEXT,
  quantity_billed  INTEGER NOT NULL CHECK (quantity_billed >= 0),
  unit_price       NUMERIC NOT NULL CHECK (unit_price >= 0),
  currency_code    CHAR(3),
  total_price      NUMERIC GENERATED ALWAYS AS (quantity_billed * unit_price) STORED
);

CREATE TABLE IF NOT EXISTS payments (
  payment_id           INTEGER PRIMARY KEY AUTOINCREMENT,
  invoice_id           INTEGER NOT NULL REFERENCES invoices(invoice_id) ON UPDATE CASCADE ON DELETE CASCADE,
  payment_date         DATE NOT NULL,
  amount_paid          NUMERIC NOT NULL CHECK (amount_paid >= 0),
  currency_code        CHAR(3),
  payment_method       TEXT,
  transaction_reference TEXT,
  payer_account        TEXT,
  payment_status       TEXT DEFAULT 'Completed'
);

CREATE TABLE IF NOT EXISTS records (
  record_id   INTEGER PRIMARY KEY,
  file_name   TEXT NOT NULL,
  row_data    TEXT NOT NULL,
  processed_at TEXT,
  created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ai_text_suggestions (
  id                           INTEGER PRIMARY KEY AUTOINCREMENT,
  part_number                  TEXT NOT NULL REFERENCES products(part_number) ON DELETE CASCADE,
  workflow_id                  TEXT NOT NULL CHECK (workflow_id IN ('title','description','tide')),
  tone                         TEXT CHECK (tone IN ('default','playful','formal','persuasive','conversational')),
  target_language              TEXT DEFAULT 'en',
  attribute_separator          TEXT DEFAULT ' - ',
  attribute_order_json         TEXT,
  request_product_info         TEXT NOT NULL,
  request_raw_json             TEXT,
  response_title_text          TEXT,
  response_title_score         REAL,
  response_title_change_summary TEXT,
  response_desc_text           TEXT,
  response_desc_score          REAL,
  response_desc_change_summary TEXT,
  response_attributes_json     TEXT,
  response_metadata_json       TEXT,
  status                       TEXT DEFAULT 'ok',
  error_message                TEXT,
  created_at                   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ai_title_examples (
  id                       INTEGER PRIMARY KEY AUTOINCREMENT,
  category                 TEXT NOT NULL,
  title_format             TEXT NOT NULL,
  product_info_json        TEXT NOT NULL,
  final_product_info_json  TEXT NOT NULL,
  UNIQUE (category, title_format, product_info_json)
);

INSERT OR IGNORE INTO attribute_groups (group_id, name, sort_order) VALUES
 (1,'General',10),(2,'Apparel',20),(3,'Electronics',30),(4,'Dimensions',40);

INSERT OR IGNORE INTO attributes (attribute_id, code, label, data_type, unit_code, is_variant, is_required, is_facet, group_id, sort_order) VALUES
 (1,'color','Color','enum',NULL,1,0,1,1,10),
 (2,'size','Size','enum',NULL,1,0,1,2,20),
 (3,'material','Material','enum',NULL,0,0,1,1,30),
 (4,'age_range','Age Range','enum',NULL,0,0,1,1,40),
 (5,'gender','Gender','enum',NULL,0,0,1,2,50),
 (6,'capacity_l','Capacity (L)','decimal','L',0,0,1,3,10),
 (7,'capacity_gb','Capacity (GB)','int','GB',0,0,1,3,20),
 (8,'weight_kg','Weight (kg)','decimal','kg',0,0,1,3,30),
 (9,'height_cm','Height (cm)','decimal','cm',0,0,0,4,10),
 (10,'width_cm','Width (cm)','decimal','cm',0,0,0,4,20),
 (11,'depth_cm','Depth (cm)','decimal','cm',0,0,0,4,30);

INSERT OR IGNORE INTO categories (category_id, code, name) VALUES
 (1,'APPAREL','Apparel'),
 (2,'ELECTRONICS','Electronics'),
 (3,'HOME_APPLIANCE','Home Appliance');

INSERT OR IGNORE INTO attribute_options (option_id,attribute_id,value,label,sort_order) VALUES
 (1,1,'Black','Black',1),(2,1,'White','White',2),(3,1,'Grey','Grey',3),(4,1,'Silver','Silver',4),(5,1,'Gold','Gold',5),
 (6,1,'Red','Red',6),(7,1,'Blue','Blue',7),(8,1,'Green','Green',8),(9,1,'Yellow','Yellow',9),(10,1,'Orange','Orange',10),
 (11,1,'Purple','Purple',11),(12,1,'Pink','Pink',12),(13,1,'Brown','Brown',13),(14,1,'Beige','Beige',14),(15,1,'Multi','Multi',99),
 (16,2,'XXS','XXS',1),(17,2,'XS','XS',2),(18,2,'S','S',3),(19,2,'M','M',4),(20,2,'L','L',5),(21,2,'XL','XL',6),(22,2,'XXL','XXL',7),
 (23,2,'3XL','3XL',8),(24,2,'4XL','4XL',9),(25,2,'6','6',20),(26,2,'8','8',21),(27,2,'10','10',22),(28,2,'12','12',23),
 (29,2,'14','14',24),(30,2,'16','16',25),(31,2,'18','18',26),(32,2,'20','20',27),
 (33,3,'Cotton','Cotton',1),(34,3,'Polyester','Polyester',2),(35,3,'Leather','Leather',3),(36,3,'Wool','Wool',4),(37,3,'Silk','Silk',5),
 (38,3,'Nylon','Nylon',6),(39,3,'Linen','Linen',7),(40,3,'Acrylic','Acrylic',8),(41,3,'Rubber','Rubber',9),(42,3,'Plastic','Plastic',10),
 (43,3,'Wood','Wood',11),(44,3,'Glass','Glass',12),(45,3,'Stainless Steel','Stainless Steel',13),(46,3,'Aluminium','Aluminium',14),
 (47,4,'0-3','0–3 years',1),(48,4,'3-5','3–5 years',2),(49,4,'5-7','5–7 years',3),(50,4,'8-12','8–12 years',4),(51,4,'13+','13+ years',5),
 (52,4,'Adult','Adult',6),(53,4,'All Ages','All Ages',7),
 (54,5,'Unisex','Unisex',1),(55,5,'Men','Men',2),(56,5,'Women','Women',3),(57,5,'Kids','Kids',4);

INSERT OR IGNORE INTO category_attributes (category_id, attribute_id, is_required, sort_order)
SELECT c.category_id, a.attribute_id, 0, s.sort_order
FROM categories c
JOIN attributes a ON a.code IN ('color','size','material','gender')
JOIN (SELECT 'color' AS code,10 AS sort_order UNION ALL SELECT 'size',20 UNION ALL SELECT 'material',30 UNION ALL SELECT 'gender',40) s
  ON s.code = a.code
WHERE c.code = 'APPAREL';

INSERT OR IGNORE INTO category_attributes (category_id, attribute_id, is_required, sort_order)
SELECT c.category_id, a.attribute_id, 0, s.sort_order
FROM categories c
JOIN attributes a ON a.code IN ('color','capacity_gb','weight_kg')
JOIN (SELECT 'color' AS code,10 AS sort_order UNION ALL SELECT 'capacity_gb',20 UNION ALL SELECT 'weight_kg',30) s
  ON s.code = a.code
WHERE c.code = 'ELECTRONICS';

INSERT OR IGNORE INTO category_attributes (category_id, attribute_id, is_required, sort_order)
SELECT c.category_id, a.attribute_id, 0, s.sort_order
FROM categories c
JOIN attributes a ON a.code IN ('color','capacity_l','weight_kg','height_cm','width_cm','depth_cm')
JOIN (SELECT 'color' AS code,10 AS sort_order UNION ALL SELECT 'capacity_l',20 UNION ALL SELECT 'weight_kg',30 UNION ALL SELECT 'height_cm',40 UNION ALL SELECT 'width_cm',50 UNION ALL SELECT 'depth_cm',60) s
  ON s.code = a.code
WHERE c.code = 'HOME_APPLIANCE';

CREATE VIEW IF NOT EXISTS vw_product_catalog AS
SELECT
  p.part_number, p.model_code, p.barcode, p.sap_article_id,
  p.short_description, p.secondary_short_description, p.full_description,
  p.country_of_origin_code, p.supplier_comments,
  b.brand_name,
  c.code AS category_code, c.name AS category_name, c.gcc_code AS category_gcc_code,
  v.legal_entity_name AS vendor_name, v.country_code AS vendor_country,
  w.warranty_type_code, w.duration_months,
  d.product_height_cm, d.product_width_cm, d.product_depth_cm,
  d.package_height_cm, d.package_width_cm, d.package_depth_cm, d.package_gross_weight_kg,
  (SELECT pm.url FROM product_media pm WHERE pm.part_number=p.part_number AND pm.media_type='image' ORDER BY COALESCE(pm.position,999999) ASC, pm.created_at DESC LIMIT 1) AS image_main_url,
  (SELECT pm.url FROM product_media pm WHERE pm.part_number=p.part_number AND pm.media_type='youtube' ORDER BY COALESCE(pm.position,999999) ASC, pm.created_at DESC LIMIT 1) AS youtube_url,
  pr.currency_code, pr.msrp, pr.rrp, pr.retail_price, pr.discount_price, pr.cost_price_ex_tax, pr.effective_date,
  p.created_at AS product_created_at, p.updated_at AS product_updated_at
FROM products p
LEFT JOIN brands     b ON p.brand_id = b.brand_id
LEFT JOIN categories c ON p.primary_category_id = c.category_id
LEFT JOIN vendors    v ON p.vendor_id = v.vendor_id
LEFT JOIN warranty   w ON p.warranty_id = w.warranty_id
LEFT JOIN dimensions d ON p.dimension_id = d.dimension_id
LEFT JOIN (SELECT part_number, MAX(effective_date) AS latest_date FROM prices GROUP BY part_number) latest_price
  ON p.part_number = latest_price.part_number
LEFT JOIN prices pr ON p.part_number = pr.part_number AND pr.effective_date = latest_price.latest_date;

CREATE VIEW IF NOT EXISTS vw_ps_product_info AS
WITH color AS (
  SELECT pav.part_number, COALESCE(ao.label, ao.value) AS color
  FROM product_attribute_values pav
  JOIN attributes a ON a.attribute_id = pav.attribute_id AND a.code='color'
  LEFT JOIN attribute_options ao ON ao.option_id = pav.option_id
),
size AS (
  SELECT pav.part_number, COALESCE(ao.label, ao.value) AS size
  FROM product_attribute_values pav
  JOIN attributes a ON a.attribute_id = pav.attribute_id AND a.code='size'
  LEFT JOIN attribute_options ao ON ao.option_id = pav.option_id
),
material AS (
  SELECT pav.part_number, COALESCE(ao.label, ao.value, pav.value_text) AS material
  FROM product_attribute_values pav
  JOIN attributes a ON a.attribute_id = pav.attribute_id AND a.code='material'
  LEFT JOIN attribute_options ao ON ao.option_id = pav.option_id
),
img AS (
  SELECT p.part_number,
         (SELECT pm.url FROM product_media pm WHERE pm.part_number=p.part_number AND pm.media_type='image'
          ORDER BY COALESCE(pm.position,999999) ASC, pm.created_at DESC LIMIT 1) AS image_uri
  FROM products p
)
SELECT
  p.part_number,
  b.brand_name AS brand,
  p.model_code AS model,
  p.short_description AS title,
  p.full_description AS description,
  c.code AS category_code,
  color.color, size.size, material.material,
  img.image_uri
FROM products p
LEFT JOIN brands     b ON b.brand_id = p.brand_id
LEFT JOIN categories c ON c.category_id = p.primary_category_id
LEFT JOIN color      ON color.part_number = p.part_number
LEFT JOIN size       ON size.part_number  = p.part_number
LEFT JOIN material   ON material.part_number = p.part_number
LEFT JOIN img        ON img.part_number = p.part_number;

CREATE INDEX IF NOT EXISTS idx_attr_code ON attributes(code);
CREATE INDEX IF NOT EXISTS idx_categories_parent ON categories(parent_id);
CREATE INDEX IF NOT EXISTS idx_attr_category ON category_attributes(category_id, attribute_id);

CREATE INDEX IF NOT EXISTS idx_products_barcode ON products(barcode);
CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand_id);
CREATE INDEX IF NOT EXISTS idx_products_model_code ON products(model_code);
CREATE INDEX IF NOT EXISTS idx_products_primary_category ON products(primary_category_id);
CREATE INDEX IF NOT EXISTS idx_products_sap_article_id ON products(sap_article_id);

CREATE INDEX IF NOT EXISTS idx_product_media_pick ON product_media(part_number, media_type, position, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_media_product ON product_media(part_number);
CREATE INDEX IF NOT EXISTS idx_media_type_pos ON product_media(media_type, position);

CREATE INDEX IF NOT EXISTS idx_price_lookup ON prices(part_number, currency_code, effective_date);
CREATE INDEX IF NOT EXISTS idx_prices_product_date ON prices(part_number, effective_date DESC);

CREATE INDEX IF NOT EXISTS idx_pav_attr_text    ON product_attribute_values(attribute_id, value_text);
CREATE INDEX IF NOT EXISTS idx_pav_attr_int     ON product_attribute_values(attribute_id, value_int);
CREATE INDEX IF NOT EXISTS idx_pav_attr_decimal ON product_attribute_values(attribute_id, value_decimal);
CREATE INDEX IF NOT EXISTS idx_pav_attr_bool    ON product_attribute_values(attribute_id, value_bool);
CREATE INDEX IF NOT EXISTS idx_pav_attr_date    ON product_attribute_values(attribute_id, value_date);
CREATE INDEX IF NOT EXISTS idx_pav_attr_option  ON product_attribute_values(attribute_id, option_id);
CREATE INDEX IF NOT EXISTS idx_pav_product      ON product_attribute_values(part_number);

CREATE INDEX IF NOT EXISTS idx_product_categories_cat ON product_categories(category_id);
CREATE INDEX IF NOT EXISTS idx_variant_parent ON product_variants(parent_part_number);

CREATE UNIQUE INDEX IF NOT EXISTS uq_attr_option_value_nocase ON attribute_options(attribute_id, value COLLATE NOCASE);

CREATE TRIGGER IF NOT EXISTS trg_products_updated_at AFTER UPDATE ON products FOR EACH ROW BEGIN UPDATE products SET updated_at=CURRENT_TIMESTAMP WHERE part_number=NEW.part_number; END;
CREATE TRIGGER IF NOT EXISTS trg_prices_updated_at   AFTER UPDATE ON prices   FOR EACH ROW BEGIN UPDATE prices   SET updated_at=CURRENT_TIMESTAMP WHERE price_id=NEW.price_id; END;
CREATE TRIGGER IF NOT EXISTS trg_categories_updated_at AFTER UPDATE ON categories FOR EACH ROW BEGIN UPDATE categories SET updated_at=CURRENT_TIMESTAMP WHERE category_id=NEW.category_id; END;
CREATE TRIGGER IF NOT EXISTS trg_vendors_updated_at   AFTER UPDATE ON vendors    FOR EACH ROW BEGIN UPDATE vendors    SET updated_at=CURRENT_TIMESTAMP WHERE vendor_id=NEW.vendor_id; END;
CREATE TRIGGER IF NOT EXISTS trg_attributes_updated_at AFTER UPDATE ON attributes FOR EACH ROW BEGIN UPDATE attributes SET updated_at=CURRENT_TIMESTAMP WHERE attribute_id=NEW.attribute_id; END;
CREATE TRIGGER IF NOT EXISTS trg_media_updated_at      AFTER UPDATE ON product_media FOR EACH ROW BEGIN UPDATE product_media SET updated_at=CURRENT_TIMESTAMP WHERE media_id=NEW.media_id; END;
CREATE TRIGGER IF NOT EXISTS trg_pav_updated_at        AFTER UPDATE ON product_attribute_values FOR EACH ROW BEGIN UPDATE product_attribute_values SET updated_at=CURRENT_TIMESTAMP WHERE part_number=NEW.part_number AND attribute_id=NEW.attribute_id; END;

COMMIT;
