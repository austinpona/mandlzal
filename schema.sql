-- Reference PostgreSQL schema for Mandlzi subscription management.
-- The application uses SQLAlchemy to manage this automatically; this file
-- exists for documentation and manual provisioning purposes.

CREATE TYPE customer_status AS ENUM ('active', 'lapsed', 'cancelled');
CREATE TYPE policy_type     AS ENUM ('individual', 'group_scheme');
CREATE TYPE policy_status   AS ENUM ('active', 'lapsed', 'cancelled');
CREATE TYPE billing_cycle   AS ENUM ('monthly');
CREATE TYPE member_status   AS ENUM ('active', 'lapsed', 'removed');
CREATE TYPE payment_method  AS ENUM ('debit_order', 'cash', 'eft');
CREATE TYPE payment_status  AS ENUM ('paid', 'pending', 'failed');

CREATE TABLE users (
    id              SERIAL PRIMARY KEY,
    email           VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name       VARCHAR(255),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    is_admin        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE customers (
    id          SERIAL PRIMARY KEY,
    full_name   VARCHAR(255) NOT NULL,
    id_number   VARCHAR(64) UNIQUE NOT NULL,
    phone       VARCHAR(32),
    email       VARCHAR(255),
    status      customer_status NOT NULL DEFAULT 'active',
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_customers_email ON customers(email);

CREATE TABLE policies (
    id                      SERIAL PRIMARY KEY,
    customer_id             INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    policy_type             policy_type NOT NULL DEFAULT 'individual',
    premium_amount          NUMERIC(12,2) NOT NULL,
    billing_cycle           billing_cycle NOT NULL DEFAULT 'monthly',
    start_date              DATE NOT NULL,
    status                  policy_status NOT NULL DEFAULT 'active',
    grace_period_days       INTEGER,
    lapse_threshold_months  INTEGER,
    created_at              TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_policies_customer ON policies(customer_id);

CREATE TABLE members (
    id                      SERIAL PRIMARY KEY,
    policy_id               INTEGER NOT NULL REFERENCES policies(id) ON DELETE CASCADE,
    full_name               VARCHAR(255) NOT NULL,
    id_number               VARCHAR(64),
    relationship_to_holder  VARCHAR(64),
    contribution_amount     NUMERIC(12,2),
    status                  member_status NOT NULL DEFAULT 'active',
    created_at              TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_members_policy ON members(policy_id);

CREATE TABLE payments (
    id              SERIAL PRIMARY KEY,
    customer_id     INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    policy_id       INTEGER NOT NULL REFERENCES policies(id) ON DELETE CASCADE,
    member_id       INTEGER REFERENCES members(id) ON DELETE SET NULL,
    amount_paid     NUMERIC(12,2) NOT NULL,
    payment_date    DATE NOT NULL,
    payment_method  payment_method NOT NULL DEFAULT 'debit_order',
    status          payment_status NOT NULL DEFAULT 'paid',
    reference       VARCHAR(128),
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_payments_customer ON payments(customer_id);
CREATE INDEX idx_payments_policy   ON payments(policy_id);
CREATE INDEX idx_payments_date     ON payments(payment_date);

CREATE TABLE audit_logs (
    id           SERIAL PRIMARY KEY,
    actor        VARCHAR(255),
    action       VARCHAR(64)  NOT NULL,
    entity_type  VARCHAR(64)  NOT NULL,
    entity_id    VARCHAR(64),
    details      TEXT,
    created_at   TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_audit_created ON audit_logs(created_at);

CREATE TABLE notifications (
    id           SERIAL PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    policy_id    INTEGER REFERENCES policies(id) ON DELETE CASCADE,
    type         VARCHAR(64) NOT NULL,
    message      TEXT NOT NULL,
    is_sent      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_notifications_created ON notifications(created_at);
