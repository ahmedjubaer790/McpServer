ALTER SESSION SET CONTAINER = FREEPDB1;

-- ১. রিসোর্স প্রোফাইল (CPU: 60s, সেশন: সর্বোচ্চ ৪টি)
CREATE PROFILE CLAUDE_GUARD LIMIT
    CPU_PER_CALL 6000
    SESSIONS_PER_USER 4
    IDLE_TIME 30
    FAILED_LOGIN_ATTEMPTS 5;

-- ২. আপনার মূল স্কিমা (AI) যদি ইতিমধ্যে তৈরি না থাকে
CREATE USER AI IDENTIFIED BY "AiSecurePass2026#"
    DEFAULT TABLESPACE USERS QUOTA UNLIMITED ON USERS;
GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW TO AI;

-- ৩. ভিউ ওনার স্কিমা (AI_RPT)
CREATE USER AI_RPT IDENTIFIED BY "AiRptSecurePass2026#"
    DEFAULT TABLESPACE USERS QUOTA UNLIMITED ON USERS;
GRANT CREATE SESSION, CREATE VIEW, CREATE SYNONYM, CREATE TABLE TO AI_RPT;

-- ৪. রিড-অনলি লগইন ইউজার (CLAUDE_RO)
CREATE USER CLAUDE_RO IDENTIFIED BY "ClaudeSecurePass2026#"
    PROFILE CLAUDE_GUARD
    DEFAULT TABLESPACE USERS;
GRANT CREATE SESSION TO CLAUDE_RO;

------------------------------
-- Connect as AI / AiSecurePass2026#@localhost:1521/FREEPDB1

---------------------------------------------------------
-- ১. OUTLETS (আউটলেট/স্টোর টেবিল)
---------------------------------------------------------
CREATE TABLE AI.OUTLETS (
    outlet_id    NUMBER PRIMARY KEY,
    outlet_name  VARCHAR2(100) NOT NULL,
    city         VARCHAR2(50),
    status       VARCHAR2(1) DEFAULT 'A'
);

INSERT INTO AI.OUTLETS VALUES (101, 'SmartStore Banani', 'Dhaka', 'A');
INSERT INTO AI.OUTLETS VALUES (102, 'SmartStore Gulshan', 'Dhaka', 'A');
INSERT INTO AI.OUTLETS VALUES (103, 'SmartStore Agrabad', 'Chittagong', 'A');
INSERT INTO AI.OUTLETS VALUES (104, 'SmartStore Zindabazar', 'Sylhet', 'A');

---------------------------------------------------------
-- ২. TRANSACTIONS (সেলস ও রেভিনিউ)
---------------------------------------------------------
CREATE TABLE AI.TRANSACTIONS (
    txn_id         NUMBER PRIMARY KEY,
    outlet_id      NUMBER REFERENCES AI.OUTLETS(outlet_id),
    txn_date       DATE DEFAULT SYSDATE,
    item_amount    NUMBER(10,2),
    tax_amount     NUMBER(10,2),
    status         VARCHAR2(1) DEFAULT 'A'  -- 'A' = Active, 'C' = Cancelled
);

-- Banani Sales
INSERT INTO AI.TRANSACTIONS VALUES (1, 101, SYSDATE, 1500.00, 112.50, 'A');
INSERT INTO AI.TRANSACTIONS VALUES (2, 101, SYSDATE, 3200.00, 240.00, 'A');
INSERT INTO AI.TRANSACTIONS VALUES (3, 101, SYSDATE - 1, 4500.00, 337.50, 'A');

-- Gulshan Sales
INSERT INTO AI.TRANSACTIONS VALUES (4, 102, SYSDATE, 5500.00, 412.50, 'A');
INSERT INTO AI.TRANSACTIONS VALUES (5, 102, SYSDATE, 2000.00, 150.00, 'A');
INSERT INTO AI.TRANSACTIONS VALUES (6, 102, SYSDATE, 1200.00, 90.00, 'C'); -- বাতিল ট্রানজেকশন

-- Agrabad & Sylhet Sales
INSERT INTO AI.TRANSACTIONS VALUES (7, 103, SYSDATE, 6800.00, 510.00, 'A');
INSERT INTO AI.TRANSACTIONS VALUES (8, 104, SYSDATE - 1, 3100.00, 232.50, 'A');

---------------------------------------------------------
-- ৩. REGISTER_RECON (ক্যাশ শর্টেজ ও এক্সেস)
---------------------------------------------------------
CREATE TABLE AI.REGISTER_RECON (
    recon_id         NUMBER PRIMARY KEY,
    outlet_id        NUMBER REFERENCES AI.OUTLETS(outlet_id),
    recon_date       DATE DEFAULT TRUNC(SYSDATE),
    system_balance   NUMBER(10,2),
    drawer_balance   NUMBER(10,2)
);

-- Banani: Balanced
INSERT INTO AI.REGISTER_RECON VALUES (501, 101, TRUNC(SYSDATE), 40000.00, 40000.00);

-- Gulshan: High Excess (+3,500 ৳)
INSERT INTO AI.REGISTER_RECON VALUES (502, 102, TRUNC(SYSDATE), 50000.00, 53500.00);

-- Agrabad: High Shortage (-3,000 ৳)
INSERT INTO AI.REGISTER_RECON VALUES (503, 103, TRUNC(SYSDATE), 35000.00, 32000.00);

-- Sylhet: High Shortage (-2,500 ৳)
INSERT INTO AI.REGISTER_RECON VALUES (504, 104, TRUNC(SYSDATE - 1), 28000.00, 25500.00);

---------------------------------------------------------
-- ৪. CUSTOMERS (ডেমো PII ডেটা সহ)
---------------------------------------------------------
CREATE TABLE AI.CUSTOMERS (
    customer_id    NUMBER PRIMARY KEY,
    customer_name  VARCHAR2(100),
    phone_number   VARCHAR2(20),  -- Masked in view
    nid_number     VARCHAR2(20),  -- PII (Blocked from Claude)
    birth_date     DATE           -- PII (Blocked from Claude)
);

CREATE TABLE AI.CUSTOMER_VISITS (
    visit_id       NUMBER PRIMARY KEY,
    customer_id    NUMBER REFERENCES AI.CUSTOMERS(customer_id),
    outlet_id      NUMBER REFERENCES AI.OUTLETS(outlet_id),
    visit_date     DATE
);

INSERT INTO AI.CUSTOMERS VALUES (1, 'Tanvir Hasan', '01711223344', '19902692510001', TO_DATE('1990-05-12','YYYY-MM-DD'));
INSERT INTO AI.CUSTOMERS VALUES (2, 'Sadia Rahman', '01819334455', '19942692510002', TO_DATE('1994-08-20','YYYY-MM-DD'));

INSERT INTO AI.CUSTOMER_VISITS VALUES (101, 1, 101, SYSDATE - 5);
INSERT INTO AI.CUSTOMER_VISITS VALUES (102, 1, 101, SYSDATE - 1);
INSERT INTO AI.CUSTOMER_VISITS VALUES (103, 2, 102, SYSDATE);

COMMIT;

-- AI_RPT ইউজারকে রিড গ্রান্ট প্রদান
GRANT SELECT ON AI.OUTLETS TO AI_RPT;
GRANT SELECT ON AI.TRANSACTIONS TO AI_RPT;
GRANT SELECT ON AI.REGISTER_RECON TO AI_RPT;
GRANT SELECT ON AI.CUSTOMERS TO AI_RPT;
GRANT SELECT ON AI.CUSTOMER_VISITS TO AI_RPT;

--------------------------------------------------

-- Connect as AI_RPT 

-- ১. অডিট টেবিল
CREATE TABLE AI_RPT.CLAUDE_QUERY_LOG (
    log_id          NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    query_time      TIMESTAMP DEFAULT SYSTIMESTAMP,
    client_id       VARCHAR2(100),
    executed_sql    VARCHAR2(4000),
    outcome         VARCHAR2(20),
    row_count       NUMBER,
    error_message   VARCHAR2(4000)
);

GRANT INSERT ON AI_RPT.CLAUDE_QUERY_LOG TO CLAUDE_RO;

-- ২. View 1: Daily Sales
CREATE OR REPLACE VIEW AI_RPT.V_SMART_DAILY_SALES AS
SELECT 
    o.outlet_id,
    o.outlet_name,
    TRUNC(t.txn_date) AS sale_date,
    SUM(t.item_amount) AS total_gross_sales,
    SUM(t.tax_amount) AS total_tax,
    COUNT(t.txn_id) AS total_transactions
FROM AI.TRANSACTIONS t
JOIN AI.OUTLETS o ON t.outlet_id = o.outlet_id
WHERE t.status = 'A'
GROUP BY o.outlet_id, o.outlet_name, TRUNC(t.txn_date);

-- ৩. View 2: Cash Reconciliation (Excess / Short)
CREATE OR REPLACE VIEW AI_RPT.V_SMART_CASH_VARIANCE AS
SELECT 
    r.recon_id,
    r.outlet_id,
    o.outlet_name,
    r.recon_date,
    r.system_balance,
    r.drawer_balance,
    (r.drawer_balance - r.system_balance) AS cash_variance,
    CASE 
        WHEN (r.drawer_balance - r.system_balance) > 2000 THEN 'EXCESS_HIGH'
        WHEN (r.drawer_balance - r.system_balance) < -2000 THEN 'SHORT_HIGH'
        ELSE 'BALANCED'
    END AS status_flag
FROM AI.REGISTER_RECON r
JOIN AI.OUTLETS o ON r.outlet_id = o.outlet_id;

-- ৪. View 3: Customer Retention (SHA-256 Hashed, No PII)
CREATE OR REPLACE VIEW AI_RPT.V_SMART_CUSTOMER_RETENTION AS
SELECT 
    STANDARD_HASH(c.phone_number || 'AI_SECRET_SALT_2026', 'SHA256') AS customer_hash,
    o.outlet_name,
    COUNT(v.visit_id) AS total_visits,
    MAX(v.visit_date) AS last_visit_date
FROM AI.CUSTOMER_VISITS v
JOIN AI.CUSTOMERS1 c ON v.customer_id = c.customer_id
JOIN AI.OUTLETS o ON v.outlet_id = o.outlet_id
GROUP BY STANDARD_HASH(c.phone_number || 'AI_SECRET_SALT_2026', 'SHA256'), o.outlet_name;

-- ৫. CLAUDE_RO-permission
GRANT SELECT ON AI_RPT.V_SMART_DAILY_SALES TO CLAUDE_RO;
GRANT SELECT ON AI_RPT.V_SMART_CASH_VARIANCE TO CLAUDE_RO;
GRANT SELECT ON AI_RPT.V_SMART_CUSTOMER_RETENTION TO CLAUDE_RO;

CREATE OR REPLACE SYNONYM CLAUDE_RO.V_SMART_DAILY_SALES FOR AI_RPT.V_SMART_DAILY_SALES;
CREATE OR REPLACE SYNONYM CLAUDE_RO.V_SMART_CASH_VARIANCE FOR AI_RPT.V_SMART_CASH_VARIANCE;
CREATE OR REPLACE SYNONYM CLAUDE_RO.V_SMART_CUSTOMER_RETENTION FOR AI_RPT.V_SMART_CUSTOMER_RETENTION;
---------------------------