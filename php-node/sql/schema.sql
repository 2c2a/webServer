-- ============================================================
-- 2c2a Project PostgreSQL Schema
-- Rewritten from Django models
-- ============================================================

BEGIN;

-- ============================================================
-- Utility: auto-update updated_at trigger
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- 1. users
-- ============================================================
CREATE TABLE users (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(150) UNIQUE NOT NULL,
    password        VARCHAR(255) NOT NULL,
    email           VARCHAR(254) UNIQUE NOT NULL,
    first_name      VARCHAR(150) DEFAULT '',
    last_name       VARCHAR(150) DEFAULT '',
    phone           VARCHAR(20) DEFAULT NULL,
    avatar          VARCHAR(500) DEFAULT NULL,
    is_verified     BOOLEAN DEFAULT FALSE,
    last_login_ip   INET DEFAULT NULL,
    is_active       BOOLEAN DEFAULT TRUE,
    is_staff        BOOLEAN DEFAULT FALSE,
    is_superuser    BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_phone ON users(phone);
CREATE INDEX idx_users_is_active ON users(is_active);

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- 2. user_profiles
-- ============================================================
CREATE TABLE user_profiles (
    id                  SERIAL PRIMARY KEY,
    user_id             INT REFERENCES users(id) ON DELETE CASCADE UNIQUE,
    nickname            VARCHAR(50) DEFAULT '',
    gender              VARCHAR(10) DEFAULT '',
    birthday            DATE DEFAULT NULL,
    location            VARCHAR(100) DEFAULT '',
    bio                 TEXT DEFAULT '',
    email_notification  BOOLEAN DEFAULT TRUE,
    system_notification BOOLEAN DEFAULT TRUE,
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW()
);

CREATE TRIGGER trg_user_profiles_updated_at
    BEFORE UPDATE ON user_profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- 3. login_logs
-- ============================================================
CREATE TABLE login_logs (
    id              SERIAL PRIMARY KEY,
    user_id         INT REFERENCES users(id) ON DELETE SET NULL,
    ip_address      INET NOT NULL,
    user_agent      TEXT DEFAULT '',
    login_type      VARCHAR(20) DEFAULT 'web',
    status          VARCHAR(20) NOT NULL,
    failure_reason  VARCHAR(200) DEFAULT '',
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_login_logs_user_id ON login_logs(user_id);
CREATE INDEX idx_login_logs_ip_address ON login_logs(ip_address);
CREATE INDEX idx_login_logs_status ON login_logs(status);
CREATE INDEX idx_login_logs_created_at ON login_logs(created_at);

-- ============================================================
-- 4. auth_groups
-- ============================================================
CREATE TABLE auth_groups (
    id      SERIAL PRIMARY KEY,
    name    VARCHAR(150) UNIQUE NOT NULL
);

-- ============================================================
-- 5. group_profiles
-- ============================================================
CREATE TABLE group_profiles (
    id              SERIAL PRIMARY KEY,
    group_id        INT REFERENCES auth_groups(id) ON DELETE CASCADE UNIQUE,
    is_default      BOOLEAN DEFAULT FALSE,
    description     TEXT DEFAULT '',
    auto_staff      BOOLEAN DEFAULT FALSE,
    sort_order      INT DEFAULT 0
);

-- ============================================================
-- 6. user_groups (M2M user-group)
-- ============================================================
CREATE TABLE user_groups (
    id      SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    group_id INT REFERENCES auth_groups(id) ON DELETE CASCADE,
    UNIQUE(user_id, group_id)
);

-- ============================================================
-- 7. registration_links
-- ============================================================
CREATE TABLE registration_links (
    id              SERIAL PRIMARY KEY,
    token           VARCHAR(64) UNIQUE NOT NULL,
    group_id        INT REFERENCES auth_groups(id) ON DELETE CASCADE NOT NULL,
    created_by_id   INT REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMP DEFAULT NOW(),
    max_uses        INT DEFAULT 1,
    used_count      INT DEFAULT 0,
    used            BOOLEAN DEFAULT FALSE,
    used_by_id      INT REFERENCES users(id) ON DELETE SET NULL,
    used_at         TIMESTAMP DEFAULT NULL,
    expires_at      TIMESTAMP DEFAULT NULL,
    note            VARCHAR(200) DEFAULT ''
);

-- ============================================================
-- 8. site_groups
-- ============================================================
CREATE TABLE site_groups (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    slug        VARCHAR(100) UNIQUE NOT NULL,
    description TEXT DEFAULT '',
    site_name   VARCHAR(100) DEFAULT '',
    site_icon   VARCHAR(500) DEFAULT '',
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
);

CREATE TRIGGER trg_site_groups_updated_at
    BEFORE UPDATE ON site_groups
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- 9. site_group_hostnames
-- ============================================================
CREATE TABLE site_group_hostnames (
    id              SERIAL PRIMARY KEY,
    hostname        VARCHAR(255) UNIQUE NOT NULL,
    site_group_id   INT REFERENCES site_groups(id) ON DELETE CASCADE NOT NULL
);

-- ============================================================
-- 10. site_group_admins (M2M)
-- ============================================================
CREATE TABLE site_group_admins (
    id              SERIAL PRIMARY KEY,
    site_group_id   INT REFERENCES site_groups(id) ON DELETE CASCADE,
    user_id         INT REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(site_group_id, user_id)
);

-- ============================================================
-- 11. user_site_groups (M2M user-sitegroup)
-- ============================================================
CREATE TABLE user_site_groups (
    id              SERIAL PRIMARY KEY,
    user_id         INT REFERENCES users(id) ON DELETE CASCADE,
    site_group_id   INT REFERENCES site_groups(id) ON DELETE CASCADE,
    UNIQUE(user_id, site_group_id)
);

-- ============================================================
-- 12. hosts
-- ============================================================
CREATE TABLE hosts (
    id                      SERIAL PRIMARY KEY,
    name                    VARCHAR(100) NOT NULL,
    os_type                 VARCHAR(20) DEFAULT 'windows',
    hostname                VARCHAR(255) NOT NULL,
    connection_type         VARCHAR(20) DEFAULT 'winrm',
    auth_method             VARCHAR(20) DEFAULT 'ntlm',
    port                    INT DEFAULT 5985,
    rdp_port                INT DEFAULT 3389,
    use_ssl                 BOOLEAN DEFAULT FALSE,
    username                VARCHAR(100) DEFAULT '',
    password                VARCHAR(255) NOT NULL,
    cert_pem_path           VARCHAR(512) DEFAULT '',
    cert_key_path           VARCHAR(512) DEFAULT '',
    os_version              VARCHAR(100) DEFAULT '',
    status                  VARCHAR(20) DEFAULT 'offline',
    description             TEXT DEFAULT '',
    created_by_id           INT REFERENCES users(id) ON DELETE SET NULL,
    site_group_id           INT REFERENCES site_groups(id) ON DELETE SET NULL,
    tunnel_token            VARCHAR(64) UNIQUE DEFAULT NULL,
    tunnel_status           VARCHAR(20) DEFAULT 'no_tunnel',
    tunnel_connected_at     TIMESTAMP DEFAULT NULL,
    tunnel_last_seen_at     TIMESTAMP DEFAULT NULL,
    tunnel_client_version   VARCHAR(50) DEFAULT '',
    tunnel_client_ip        INET DEFAULT NULL,
    tunnel_public_key       TEXT DEFAULT '',
    cert_root               VARCHAR(2) DEFAULT '',
    cert_sub                VARCHAR(2) DEFAULT '',
    pfx_password            VARCHAR(255) DEFAULT '',
    ntlm_fallback_user      VARCHAR(100) DEFAULT '',
    ntlm_fallback_password  VARCHAR(255) DEFAULT '',
    cert_activated_at       TIMESTAMP DEFAULT NULL,
    cert_provision_status   VARCHAR(20) DEFAULT 'not_started',
    created_at              TIMESTAMP DEFAULT NOW(),
    updated_at              TIMESTAMP DEFAULT NOW()
);

CREATE TRIGGER trg_hosts_updated_at
    BEFORE UPDATE ON hosts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- 13. host_administrators (M2M host-admins)
-- ============================================================
CREATE TABLE host_administrators (
    id      SERIAL PRIMARY KEY,
    host_id INT REFERENCES hosts(id) ON DELETE CASCADE,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(host_id, user_id)
);

-- ============================================================
-- 14. host_providers (M2M host-providers)
-- ============================================================
CREATE TABLE host_providers (
    id      SERIAL PRIMARY KEY,
    host_id INT REFERENCES hosts(id) ON DELETE CASCADE,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(host_id, user_id)
);

-- ============================================================
-- 15. host_groups
-- ============================================================
CREATE TABLE host_groups (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    description     TEXT DEFAULT '',
    created_by_id   INT REFERENCES users(id) ON DELETE SET NULL,
    site_group_id   INT REFERENCES site_groups(id) ON DELETE SET NULL,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE TRIGGER trg_host_groups_updated_at
    BEFORE UPDATE ON host_groups
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- 16. host_group_hosts (M2M)
-- ============================================================
CREATE TABLE host_group_hosts (
    id          SERIAL PRIMARY KEY,
    hostgroup_id INT REFERENCES host_groups(id) ON DELETE CASCADE,
    host_id     INT REFERENCES hosts(id) ON DELETE CASCADE,
    UNIQUE(hostgroup_id, host_id)
);

-- ============================================================
-- 17. host_group_providers (M2M)
-- ============================================================
CREATE TABLE host_group_providers (
    id          SERIAL PRIMARY KEY,
    hostgroup_id INT REFERENCES host_groups(id) ON DELETE CASCADE,
    user_id     INT REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(hostgroup_id, user_id)
);

-- ============================================================
-- 18. system_configs (singleton)
-- ============================================================
CREATE TABLE system_configs (
    id                          SERIAL PRIMARY KEY,
    smtp_host                   VARCHAR(255) DEFAULT NULL,
    smtp_port                   INT DEFAULT NULL,
    smtp_use_tls                BOOLEAN DEFAULT TRUE,
    smtp_username               VARCHAR(255) DEFAULT NULL,
    smtp_password               VARCHAR(255) DEFAULT NULL,
    smtp_from_email             VARCHAR(254) DEFAULT NULL,
    captcha_provider            VARCHAR(32) DEFAULT 'none',
    captcha_type                VARCHAR(32) DEFAULT 'SLIDER',
    login_captcha_type          VARCHAR(32) DEFAULT NULL,
    register_captcha_type       VARCHAR(32) DEFAULT NULL,
    email_captcha_type          VARCHAR(32) DEFAULT NULL,
    site_name                   VARCHAR(100) DEFAULT '2c2a',
    enable_registration         BOOLEAN DEFAULT FALSE,
    icp_number                  VARCHAR(100) DEFAULT NULL,
    police_number               VARCHAR(100) DEFAULT NULL,
    email_suffix_whitelist      TEXT DEFAULT NULL,
    email_suffix_blacklist      TEXT DEFAULT NULL,
    local_access_locked         BOOLEAN DEFAULT FALSE,
    hostname_branding           JSONB DEFAULT '{}',
    created_at                  TIMESTAMP DEFAULT NOW(),
    updated_at                  TIMESTAMP DEFAULT NOW()
);

CREATE TRIGGER trg_system_configs_updated_at
    BEFORE UPDATE ON system_configs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- 19. dashboard_widgets
-- ============================================================
CREATE TABLE dashboard_widgets (
    id              SERIAL PRIMARY KEY,
    widget_type     VARCHAR(50) NOT NULL,
    title           VARCHAR(200) NOT NULL,
    display_order   INT DEFAULT 0,
    is_enabled      BOOLEAN DEFAULT TRUE,
    widget_config   JSONB DEFAULT '{}',
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE TRIGGER trg_dashboard_widgets_updated_at
    BEFORE UPDATE ON dashboard_widgets
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- 20. product_groups
-- ============================================================
CREATE TABLE product_groups (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(200) NOT NULL,
    description     TEXT DEFAULT '',
    display_order   INT DEFAULT 0,
    is_active       BOOLEAN DEFAULT TRUE,
    visibility      VARCHAR(20) DEFAULT 'public',
    site_group_id   INT REFERENCES site_groups(id) ON DELETE SET NULL,
    created_by_id   INT REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE TRIGGER trg_product_groups_updated_at
    BEFORE UPDATE ON product_groups
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- 21. product_group_auto_providers (M2M)
-- ============================================================
CREATE TABLE product_group_auto_providers (
    id              SERIAL PRIMARY KEY,
    productgroup_id INT REFERENCES product_groups(id) ON DELETE CASCADE,
    user_id         INT REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(productgroup_id, user_id)
);

-- ============================================================
-- 22. products
-- ============================================================
CREATE TABLE products (
    id                      SERIAL PRIMARY KEY,
    name                    VARCHAR(200) NOT NULL,
    description             TEXT DEFAULT '',
    display_name            VARCHAR(200) NOT NULL,
    display_description     TEXT DEFAULT '',
    product_group_id        INT REFERENCES product_groups(id) ON DELETE SET NULL,
    host_id                 INT REFERENCES hosts(id) ON DELETE CASCADE NOT NULL,
    site_group_id           INT REFERENCES site_groups(id) ON DELETE SET NULL,
    rdp_port                INT DEFAULT 3389,
    display_hostname        VARCHAR(255) NOT NULL,
    is_available            BOOLEAN DEFAULT TRUE,
    auto_approval           BOOLEAN DEFAULT FALSE,
    visibility              VARCHAR(20) DEFAULT 'public',
    limit_one_per_user      BOOLEAN DEFAULT FALSE,
    enable_disk_quota       BOOLEAN DEFAULT FALSE,
    enable_host_protection  BOOLEAN DEFAULT FALSE,
    default_disk_quota      JSONB DEFAULT '{}',
    allow_extra_quota_disks JSONB DEFAULT '[]',
    created_by_id           INT REFERENCES users(id) ON DELETE SET NULL,
    created_at              TIMESTAMP DEFAULT NOW(),
    updated_at              TIMESTAMP DEFAULT NOW()
);

CREATE TRIGGER trg_products_updated_at
    BEFORE UPDATE ON products
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- 23. account_opening_requests
-- ============================================================
CREATE TABLE account_opening_requests (
    id                      SERIAL PRIMARY KEY,
    applicant_id            INT REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    contact_email           VARCHAR(254) NOT NULL,
    contact_phone           VARCHAR(20) DEFAULT NULL,
    username                VARCHAR(150) NOT NULL,
    user_fullname           VARCHAR(200) NOT NULL,
    user_email              VARCHAR(254) NOT NULL,
    user_description        TEXT DEFAULT '',
    target_product_id       INT REFERENCES products(id) ON DELETE CASCADE,
    requested_disk_capacity JSONB DEFAULT '{}',
    status                  VARCHAR(20) DEFAULT 'pending',
    approved_by_id          INT REFERENCES users(id) ON DELETE SET NULL,
    approval_date           TIMESTAMP DEFAULT NULL,
    approval_notes          TEXT DEFAULT '',
    cloud_user_id           VARCHAR(255) DEFAULT '',
    cloud_user_password     VARCHAR(255) DEFAULT '',
    result_message          TEXT DEFAULT '',
    retry_count             INT DEFAULT 0,
    created_at              TIMESTAMP DEFAULT NOW(),
    updated_at              TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_aor_applicant_id ON account_opening_requests(applicant_id);
CREATE INDEX idx_aor_status ON account_opening_requests(status);
CREATE INDEX idx_aor_target_product_id ON account_opening_requests(target_product_id);
CREATE INDEX idx_aor_created_at ON account_opening_requests(created_at);

CREATE TRIGGER trg_account_opening_requests_updated_at
    BEFORE UPDATE ON account_opening_requests
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- 24. cloud_computer_users
-- ============================================================
CREATE TABLE cloud_computer_users (
    id                      SERIAL PRIMARY KEY,
    username                VARCHAR(150) NOT NULL,
    fullname                VARCHAR(200) NOT NULL,
    email                   VARCHAR(254) NOT NULL,
    description             TEXT DEFAULT '',
    product_id              INT REFERENCES products(id) ON DELETE CASCADE NOT NULL,
    status                  VARCHAR(20) DEFAULT 'active',
    is_admin                BOOLEAN DEFAULT FALSE,
    groups                  TEXT DEFAULT '',
    disk_quota              JSONB DEFAULT '{}',
    created_from_request_id INT REFERENCES account_opening_requests(id) ON DELETE SET NULL,
    owner_id                INT REFERENCES users(id) ON DELETE SET NULL,
    initial_password        VARCHAR(512) DEFAULT '',
    password_viewed         BOOLEAN DEFAULT FALSE,
    password_viewed_at      TIMESTAMP DEFAULT NULL,
    created_at              TIMESTAMP DEFAULT NOW(),
    updated_at              TIMESTAMP DEFAULT NOW(),
    UNIQUE(product_id, username)
);

CREATE INDEX idx_ccu_product_id ON cloud_computer_users(product_id);
CREATE INDEX idx_ccu_username ON cloud_computer_users(username);
CREATE INDEX idx_ccu_status ON cloud_computer_users(status);
CREATE INDEX idx_ccu_created_at ON cloud_computer_users(created_at);

CREATE TRIGGER trg_cloud_computer_users_updated_at
    BEFORE UPDATE ON cloud_computer_users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- 25. rdp_domain_routes
-- ============================================================
CREATE TABLE rdp_domain_routes (
    id              SERIAL PRIMARY KEY,
    domain          VARCHAR(255) UNIQUE NOT NULL,
    product_id      INT REFERENCES products(id) ON DELETE CASCADE NOT NULL,
    assigned_to_id  INT REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    tunnel_token    VARCHAR(64) DEFAULT '',
    is_active       BOOLEAN DEFAULT TRUE,
    expires_at      TIMESTAMP NOT NULL,
    last_activity_at TIMESTAMP DEFAULT NOW(),
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_rdr_domain ON rdp_domain_routes(domain);
CREATE INDEX idx_rdr_is_active ON rdp_domain_routes(is_active);
CREATE INDEX idx_rdr_assigned_to_id ON rdp_domain_routes(assigned_to_id);
CREATE INDEX idx_rdr_expires_at ON rdp_domain_routes(expires_at);
CREATE INDEX idx_rdr_product_id ON rdp_domain_routes(product_id);

-- ============================================================
-- 26. product_invitation_tokens
-- ============================================================
CREATE TABLE product_invitation_tokens (
    id              SERIAL PRIMARY KEY,
    token           VARCHAR(64) UNIQUE NOT NULL,
    product_id      INT REFERENCES products(id) ON DELETE CASCADE,
    product_group_id INT REFERENCES product_groups(id) ON DELETE CASCADE,
    created_by_id   INT REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    max_uses        INT DEFAULT 0,
    used_count      INT DEFAULT 0,
    expires_at      TIMESTAMP DEFAULT NULL,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE TRIGGER trg_product_invitation_tokens_updated_at
    BEFORE UPDATE ON product_invitation_tokens
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- 27. product_access_grants
-- ============================================================
CREATE TABLE product_access_grants (
    id                  SERIAL PRIMARY KEY,
    user_id             INT REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    product_id          INT REFERENCES products(id) ON DELETE CASCADE,
    product_group_id    INT REFERENCES product_groups(id) ON DELETE CASCADE,
    granted_by_token_id INT REFERENCES product_invitation_tokens(id) ON DELETE SET NULL,
    granted_at          TIMESTAMP DEFAULT NOW(),
    expires_at          TIMESTAMP DEFAULT NULL,
    is_revoked          BOOLEAN DEFAULT FALSE,
    revoked_at          TIMESTAMP DEFAULT NULL,
    revoked_by_id       INT REFERENCES users(id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX idx_pag_user_product ON product_access_grants(user_id, product_id) WHERE product_id IS NOT NULL;
CREATE UNIQUE INDEX idx_pag_user_product_group ON product_access_grants(user_id, product_group_id) WHERE product_group_id IS NOT NULL;

-- ============================================================
-- 28. system_tasks
-- ============================================================
CREATE TABLE system_tasks (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(200) NOT NULL,
    task_type       VARCHAR(100) NOT NULL,
    description     TEXT DEFAULT NULL,
    status          VARCHAR(20) DEFAULT 'pending',
    progress        INT DEFAULT 0,
    result          TEXT DEFAULT NULL,
    error_message   TEXT DEFAULT NULL,
    created_by_id   INT REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMP DEFAULT NOW(),
    started_at      TIMESTAMP DEFAULT NULL,
    completed_at    TIMESTAMP DEFAULT NULL
);

CREATE INDEX idx_system_tasks_status ON system_tasks(status);
CREATE INDEX idx_system_tasks_task_type ON system_tasks(task_type);
CREATE INDEX idx_system_tasks_created_at ON system_tasks(created_at);

-- ============================================================
-- 29. async_tasks
-- ============================================================
CREATE TABLE async_tasks (
    id                      SERIAL PRIMARY KEY,
    task_id                 VARCHAR(255) UNIQUE NOT NULL,
    name                    VARCHAR(255) NOT NULL,
    status                  VARCHAR(20) DEFAULT 'pending',
    created_by_id           INT REFERENCES users(id) ON DELETE SET NULL,
    created_at              TIMESTAMP DEFAULT NOW(),
    started_at              TIMESTAMP DEFAULT NULL,
    completed_at            TIMESTAMP DEFAULT NULL,
    progress                INT DEFAULT 0,
    result                  JSONB DEFAULT NULL,
    error_message           TEXT DEFAULT NULL,
    target_object_id        INT DEFAULT NULL,
    target_content_type     VARCHAR(100) DEFAULT NULL
);

-- ============================================================
-- 30. task_progress
-- ============================================================
CREATE TABLE task_progress (
    id          SERIAL PRIMARY KEY,
    task_id     INT REFERENCES async_tasks(id) ON DELETE CASCADE,
    progress    INT NOT NULL,
    message     TEXT DEFAULT NULL,
    timestamp   TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 31. ticket_categories
-- ============================================================
CREATE TABLE ticket_categories (
    id                      SERIAL PRIMARY KEY,
    name                    VARCHAR(100) NOT NULL,
    description             TEXT DEFAULT '',
    icon                    VARCHAR(50) DEFAULT 'help_outline',
    default_priority        VARCHAR(20) DEFAULT 'medium',
    auto_assign_to_id       INT REFERENCES users(id) ON DELETE SET NULL,
    auto_assign_to_group_id INT REFERENCES auth_groups(id) ON DELETE SET NULL,
    sla_hours               INT DEFAULT 24,
    is_active               BOOLEAN DEFAULT TRUE,
    display_order           INT DEFAULT 0,
    created_by_id           INT REFERENCES users(id) ON DELETE SET NULL,
    created_at              TIMESTAMP DEFAULT NOW(),
    updated_at              TIMESTAMP DEFAULT NOW()
);

CREATE TRIGGER trg_ticket_categories_updated_at
    BEFORE UPDATE ON ticket_categories
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- 32. tickets
-- ============================================================
CREATE TABLE tickets (
    id                  SERIAL PRIMARY KEY,
    ticket_no           VARCHAR(20) UNIQUE NOT NULL,
    title               VARCHAR(200) NOT NULL,
    description         TEXT NOT NULL,
    category_id         INT REFERENCES ticket_categories(id) ON DELETE SET NULL,
    status              VARCHAR(20) DEFAULT 'pending',
    priority            VARCHAR(20) DEFAULT 'medium',
    source              VARCHAR(20) DEFAULT 'web',
    creator_id          INT REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    assignee_id         INT REFERENCES users(id) ON DELETE SET NULL,
    assigned_group_id   INT REFERENCES auth_groups(id) ON DELETE SET NULL,
    related_product_id  INT REFERENCES products(id) ON DELETE SET NULL,
    related_host_id     INT REFERENCES hosts(id) ON DELETE SET NULL,
    due_at              TIMESTAMP DEFAULT NULL,
    resolved_at         TIMESTAMP DEFAULT NULL,
    closed_at           TIMESTAMP DEFAULT NULL,
    satisfaction        SMALLINT DEFAULT NULL,
    satisfaction_comment TEXT DEFAULT '',
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_tickets_ticket_no ON tickets(ticket_no);
CREATE INDEX idx_tickets_status ON tickets(status);
CREATE INDEX idx_tickets_priority ON tickets(priority);
CREATE INDEX idx_tickets_assignee_id ON tickets(assignee_id);
CREATE INDEX idx_tickets_creator_id ON tickets(creator_id);
CREATE INDEX idx_tickets_category_id ON tickets(category_id);
CREATE INDEX idx_tickets_created_at ON tickets(created_at);
CREATE INDEX idx_tickets_due_at ON tickets(due_at);

CREATE TRIGGER trg_tickets_updated_at
    BEFORE UPDATE ON tickets
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- 33. ticket_comments
-- ============================================================
CREATE TABLE ticket_comments (
    id          SERIAL PRIMARY KEY,
    ticket_id   INT REFERENCES tickets(id) ON DELETE CASCADE NOT NULL,
    author_id   INT REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    content     TEXT NOT NULL,
    is_internal BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 34. ticket_activities
-- ============================================================
CREATE TABLE ticket_activities (
    id          SERIAL PRIMARY KEY,
    ticket_id   INT REFERENCES tickets(id) ON DELETE CASCADE NOT NULL,
    actor_id    INT REFERENCES users(id) ON DELETE SET NULL,
    action      VARCHAR(20) NOT NULL,
    old_value   VARCHAR(255) DEFAULT '',
    new_value   VARCHAR(255) DEFAULT '',
    description TEXT DEFAULT '',
    created_at  TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 35. ticket_attachments
-- ============================================================
CREATE TABLE ticket_attachments (
    id              SERIAL PRIMARY KEY,
    ticket_id       INT REFERENCES tickets(id) ON DELETE CASCADE NOT NULL,
    file_path       VARCHAR(500) NOT NULL,
    filename        VARCHAR(255) NOT NULL,
    uploaded_by_id  INT REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 36. certificate_authorities
-- ============================================================
CREATE TABLE certificate_authorities (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255) UNIQUE NOT NULL,
    cert_root   VARCHAR(2) DEFAULT '',
    cert_sub    VARCHAR(2) DEFAULT '',
    created_at  TIMESTAMP DEFAULT NOW(),
    expires_at  TIMESTAMP DEFAULT NULL,
    is_active   BOOLEAN DEFAULT TRUE,
    description TEXT DEFAULT NULL
);

-- ============================================================
-- 37. server_certificates
-- ============================================================
CREATE TABLE server_certificates (
    id              SERIAL PRIMARY KEY,
    hostname        VARCHAR(255) UNIQUE NOT NULL,
    ip_address      INET DEFAULT NULL,
    ca_id           INT REFERENCES certificate_authorities(id) ON DELETE CASCADE NOT NULL,
    thumbprint      VARCHAR(255) UNIQUE NOT NULL,
    created_at      TIMESTAMP DEFAULT NOW(),
    expires_at      TIMESTAMP DEFAULT NULL,
    is_revoked      BOOLEAN DEFAULT FALSE,
    revocation_reason VARCHAR(255) DEFAULT NULL,
    revocation_date TIMESTAMP DEFAULT NULL
);

-- ============================================================
-- 38. client_certificates
-- ============================================================
CREATE TABLE client_certificates (
    id                  SERIAL PRIMARY KEY,
    name                VARCHAR(255) NOT NULL,
    upn_value           VARCHAR(255) DEFAULT '',
    ca_id               INT REFERENCES certificate_authorities(id) ON DELETE CASCADE NOT NULL,
    thumbprint          VARCHAR(255) UNIQUE NOT NULL,
    created_at          TIMESTAMP DEFAULT NOW(),
    expires_at          TIMESTAMP DEFAULT NULL,
    assigned_to_user_id INT REFERENCES users(id) ON DELETE SET NULL,
    is_active           BOOLEAN DEFAULT TRUE,
    description         TEXT DEFAULT NULL
);

-- ============================================================
-- 39. audit_logs
-- ============================================================
CREATE TABLE audit_logs (
    id              SERIAL PRIMARY KEY,
    user_id         INT REFERENCES users(id) ON DELETE SET NULL,
    host_id         INT REFERENCES hosts(id) ON DELETE SET NULL,
    action          VARCHAR(50) NOT NULL,
    ip_address      INET DEFAULT NULL,
    user_agent      TEXT DEFAULT '',
    timestamp       TIMESTAMP DEFAULT NOW(),
    success         BOOLEAN DEFAULT TRUE,
    details         JSONB DEFAULT '{}',
    result          TEXT DEFAULT NULL,
    content_type    VARCHAR(100) DEFAULT NULL,
    object_id       INT DEFAULT NULL
);

CREATE INDEX idx_audit_logs_user_timestamp ON audit_logs(user_id, timestamp);
CREATE INDEX idx_audit_logs_host_timestamp ON audit_logs(host_id, timestamp);
CREATE INDEX idx_audit_logs_action_timestamp ON audit_logs(action, timestamp);
CREATE INDEX idx_audit_logs_timestamp ON audit_logs(timestamp);

-- ============================================================
-- 40. sensitive_operations
-- ============================================================
CREATE TABLE sensitive_operations (
    id              SERIAL PRIMARY KEY,
    operation_type  VARCHAR(50) NOT NULL,
    user_id         INT REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    target          VARCHAR(255) NOT NULL,
    timestamp       TIMESTAMP DEFAULT NOW(),
    ip_address      INET NOT NULL,
    justification   TEXT NOT NULL,
    approved_by_id  INT REFERENCES users(id) ON DELETE SET NULL,
    approved_at     TIMESTAMP DEFAULT NULL,
    result          TEXT DEFAULT NULL
);

-- ============================================================
-- 41. security_events
-- ============================================================
CREATE TABLE security_events (
    id              SERIAL PRIMARY KEY,
    event_type      VARCHAR(50) NOT NULL,
    severity        VARCHAR(10) DEFAULT 'medium',
    user_id         INT REFERENCES users(id) ON DELETE SET NULL,
    ip_address      INET NOT NULL,
    description     TEXT NOT NULL,
    timestamp       TIMESTAMP DEFAULT NOW(),
    resolved        BOOLEAN DEFAULT FALSE,
    resolved_by_id  INT REFERENCES users(id) ON DELETE SET NULL,
    resolved_at     TIMESTAMP DEFAULT NULL,
    resolution_notes TEXT DEFAULT NULL
);

-- ============================================================
-- 42. session_activities
-- ============================================================
CREATE TABLE session_activities (
    id          SERIAL PRIMARY KEY,
    user_id     INT REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    session_key VARCHAR(40) NOT NULL,
    ip_address  INET NOT NULL,
    user_agent  TEXT DEFAULT '',
    login_time  TIMESTAMP DEFAULT NOW(),
    logout_time TIMESTAMP DEFAULT NULL,
    is_active   BOOLEAN DEFAULT TRUE
);

-- ============================================================
-- 43. theme_configs (singleton)
-- ============================================================
CREATE TABLE theme_configs (
    id                          SERIAL PRIMARY KEY,
    active_theme                VARCHAR(50) DEFAULT 'material-design-3',
    branding                    JSONB DEFAULT '{}',
    custom_colors               JSONB DEFAULT '{}',
    css_overrides               TEXT DEFAULT '',
    enable_mobile_optimization  BOOLEAN DEFAULT TRUE,
    updated_at                  TIMESTAMP DEFAULT NOW()
);

CREATE TRIGGER trg_theme_configs_updated_at
    BEFORE UPDATE ON theme_configs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- 44. page_contents
-- ============================================================
CREATE TABLE page_contents (
    id          SERIAL PRIMARY KEY,
    position    VARCHAR(50) UNIQUE NOT NULL,
    title       VARCHAR(200) DEFAULT '',
    content     TEXT DEFAULT '',
    is_enabled  BOOLEAN DEFAULT TRUE,
    metadata    JSONB DEFAULT '{}',
    updated_at  TIMESTAMP DEFAULT NOW()
);

CREATE TRIGGER trg_page_contents_updated_at
    BEFORE UPDATE ON page_contents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- 45. widget_layouts
-- ============================================================
CREATE TABLE widget_layouts (
    id              SERIAL PRIMARY KEY,
    widget_type     VARCHAR(50) UNIQUE NOT NULL,
    display_order   INT DEFAULT 0,
    column_span     SMALLINT DEFAULT 1,
    row_span        SMALLINT DEFAULT 1,
    is_visible      BOOLEAN DEFAULT TRUE,
    responsive      JSONB DEFAULT '{}'
);

-- ============================================================
-- 46. plugin_records
-- ============================================================
CREATE TABLE plugin_records (
    id          SERIAL PRIMARY KEY,
    plugin_id   VARCHAR(100) UNIQUE NOT NULL,
    name        VARCHAR(200) NOT NULL,
    version     VARCHAR(50) NOT NULL,
    description TEXT DEFAULT '',
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
);

CREATE TRIGGER trg_plugin_records_updated_at
    BEFORE UPDATE ON plugin_records
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- 47. plugin_configurations
-- ============================================================
CREATE TABLE plugin_configurations (
    id          SERIAL PRIMARY KEY,
    plugin_id   INT REFERENCES plugin_records(id) ON DELETE CASCADE NOT NULL,
    key         VARCHAR(200) NOT NULL,
    value       TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW(),
    UNIQUE(plugin_id, key)
);

CREATE TRIGGER trg_plugin_configurations_updated_at
    BEFORE UPDATE ON plugin_configurations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- 48. initial_tokens
-- ============================================================
CREATE TABLE initial_tokens (
    token                       VARCHAR(255) PRIMARY KEY,
    host_id                     INT REFERENCES hosts(id) ON DELETE CASCADE,
    expires_at                  TIMESTAMP NOT NULL,
    status                      VARCHAR(20) DEFAULT 'ISSUED',
    pairing_code                VARCHAR(6) DEFAULT NULL,
    pairing_code_expires_at     TIMESTAMP DEFAULT NULL,
    pairing_attempts            INT DEFAULT 0,
    created_at                  TIMESTAMP DEFAULT NOW(),
    cert_data                   JSONB DEFAULT NULL
);

-- ============================================================
-- 49. active_sessions
-- ============================================================
CREATE TABLE active_sessions (
    session_token   VARCHAR(255) PRIMARY KEY,
    host_id         INT REFERENCES hosts(id) ON DELETE CASCADE NOT NULL,
    bound_ip        INET NOT NULL,
    expires_at      TIMESTAMP NOT NULL,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 50. cert_provision_tokens
-- ============================================================
CREATE TABLE cert_provision_tokens (
    token           VARCHAR(64) PRIMARY KEY,
    host_id         INT REFERENCES hosts(id) ON DELETE CASCADE,
    server_host     VARCHAR(255) NOT NULL,
    hostname        VARCHAR(255) DEFAULT '',
    ip_address      VARCHAR(255) DEFAULT '',
    expires_at      TIMESTAMP NOT NULL,
    status          VARCHAR(20) DEFAULT 'ISSUED',
    cert_data       JSONB DEFAULT NULL,
    created_by_id   INT REFERENCES users(id) ON DELETE SET NULL,
    consumed_at     TIMESTAMP DEFAULT NULL,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 51. user_sessions
-- ============================================================
CREATE TABLE user_sessions (
    id          SERIAL PRIMARY KEY,
    session_id  VARCHAR(128) UNIQUE NOT NULL,
    user_id     INT REFERENCES users(id) ON DELETE CASCADE,
    ip_address  INET DEFAULT NULL,
    user_agent  TEXT DEFAULT '',
    data        JSONB DEFAULT '{}',
    created_at  TIMESTAMP DEFAULT NOW(),
    expires_at  TIMESTAMP NOT NULL
);

-- ============================================================
-- Initial data
-- ============================================================
INSERT INTO system_configs (id, site_name, enable_registration)
VALUES (1, '2c2a', FALSE);

INSERT INTO theme_configs (id, active_theme)
VALUES (1, 'material-design-3');

COMMIT;
