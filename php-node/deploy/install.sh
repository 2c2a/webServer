#!/usr/bin/env bash
# ============================================================
# 2c2a Application - Installation Script
# PHP + Node.js deployment
# ============================================================
set -euo pipefail

# ----------------------------------------------------------
# Configuration
# ----------------------------------------------------------
APP_NAME="2c2a"
APP_DIR="/var/www/2c2a"
APP_USER="www-data"
APP_GROUP="www-data"
DB_NAME="2c2a"
DB_USER="2c2a"
PHP_VERSION="8.2"
NODE_MAJOR=20
LOG_DIR="/var/log/2c2a"
DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ----------------------------------------------------------
# Helper functions
# ----------------------------------------------------------
info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

check_root() {
    if [[ $EUID -ne 0 ]]; then
        error "This script must be run as root"
    fi
}

# ----------------------------------------------------------
# Step 1: Install system dependencies
# ----------------------------------------------------------
install_system_deps() {
    info "Installing system dependencies..."

    # Add PHP PPA
    apt-get update -qq
    apt-get install -y -qq software-properties-common gnupg2 curl ca-certificates lsb-release >/dev/null 2>&1

    # Add PHP repository
    if [[ ! -f /etc/apt/sources.list.d/ondrej-ubuntu-php-*.list ]]; then
        add-apt-repository -y ppa:ondrej/php >/dev/null 2>&1
    fi

    # Add Node.js repository
    if [[ ! -f /etc/apt/sources.list.d/nodesource.list ]]; then
        curl -fsSL https://deb.nodesource.com/setup_${NODE_MAJOR}.x | bash - >/dev/null 2>&1
    fi

    apt-get update -qq

    # Install PHP and extensions
    info "Installing PHP ${PHP_VERSION} and extensions..."
    apt-get install -y -qq \
        php${PHP_VERSION}-fpm \
        php${PHP_VERSION}-pgsql \
        php${PHP_VERSION}-redis \
        php${PHP_VERSION}-mbstring \
        php${PHP_VERSION}-xml \
        php${PHP_VERSION}-curl \
        php${PHP_VERSION}-gd \
        php${PHP_VERSION}-zip \
        php${PHP_VERSION}-intl \
        php${PHP_VERSION}-opcache \
        php${PHP_VERSION}-bcmath \
        php${PHP_VERSION}-json \
        >/dev/null 2>&1
    ok "PHP ${PHP_VERSION} installed"

    # Install Node.js
    info "Installing Node.js..."
    apt-get install -y -qq nodejs >/dev/null 2>&1
    ok "Node.js $(node --version) installed"

    # Install PostgreSQL
    info "Installing PostgreSQL..."
    apt-get install -y -qq postgresql postgresql-contrib >/dev/null 2>&1
    ok "PostgreSQL installed"

    # Install Redis
    info "Installing Redis..."
    apt-get install -y -qq redis-server >/dev/null 2>&1
    ok "Redis installed"

    # Install Nginx
    info "Installing Nginx..."
    apt-get install -y -qq nginx >/dev/null 2>&1
    ok "Nginx installed"

    # Install Supervisor
    info "Installing Supervisor..."
    apt-get install -y -qq supervisor >/dev/null 2>&1
    ok "Supervisor installed"

    # Install other utilities
    apt-get install -y -qq openssl >/dev/null 2>&1

    ok "All system dependencies installed"
}

# ----------------------------------------------------------
# Step 2: Create PostgreSQL database and user
# ----------------------------------------------------------
setup_database() {
    info "Setting up PostgreSQL database..."

    # Check if database already exists
    if sudo -u postgres psql -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw "${DB_NAME}"; then
        warn "Database '${DB_NAME}' already exists, skipping creation"
    else
        # Generate a random password
        DB_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=' | head -c 32)
        sudo -u postgres psql -c "CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';" 2>/dev/null
        sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};" 2>/dev/null
        sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};" 2>/dev/null
        ok "Database '${DB_NAME}' and user '${DB_USER}' created"
        info "Database password: ${DB_PASSWORD}"
        info "Save this password! It will be written to .env"
    fi
}

# ----------------------------------------------------------
# Step 3: Run schema.sql
# ----------------------------------------------------------
run_schema() {
    info "Running database schema..."

    if [[ -f "${APP_DIR}/sql/schema.sql" ]]; then
        # Read DB_PASSWORD from .env if available
        local db_pass
        db_pass=$(grep '^DB_PASSWORD=' "${APP_DIR}/.env" 2>/dev/null | cut -d'=' -f2- || echo "")

        PGPASSWORD="${db_pass}" psql -h 127.0.0.1 -U "${DB_USER}" -d "${DB_NAME}" \
            -f "${APP_DIR}/sql/schema.sql" 2>&1 || true
        ok "Database schema applied"
    else
        warn "schema.sql not found at ${APP_DIR}/sql/schema.sql, skipping"
    fi
}

# ----------------------------------------------------------
# Step 4: Install Node.js dependencies
# ----------------------------------------------------------
install_node_deps() {
    info "Installing Node.js worker dependencies..."

    if [[ -f "${APP_DIR}/worker/package.json" ]]; then
        cd "${APP_DIR}/worker"
        npm install --production 2>&1
        ok "Node.js dependencies installed"
    else
        warn "worker/package.json not found, skipping"
    fi
}

# ----------------------------------------------------------
# Step 5: Setup .env configuration
# ----------------------------------------------------------
setup_env() {
    info "Setting up environment configuration..."

    if [[ -f "${APP_DIR}/.env" ]]; then
        warn ".env file already exists, skipping copy"
        return
    fi

    if [[ -f "${APP_DIR}/.env.example" ]]; then
        cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"

        # Generate APP_SECRET_KEY
        local secret_key
        secret_key=$(openssl rand -base64 48 | tr -d '/+=' | head -c 64)
        sed -i "s/^APP_SECRET_KEY=.*/APP_SECRET_KEY=${secret_key}/" "${APP_DIR}/.env"

        # Set database password if we created one
        if [[ -n "${DB_PASSWORD:-}" ]]; then
            sed -i "s/^DB_PASSWORD=.*/DB_PASSWORD=${DB_PASSWORD}/" "${APP_DIR}/.env"
            sed -i "s/^DB_USER=.*/DB_USER=${DB_USER}/" "${APP_DIR}/.env"
            sed -i "s/^DB_NAME=.*/DB_NAME=${DB_NAME}/" "${APP_DIR}/.env"
        fi

        ok ".env file created with generated APP_SECRET_KEY"

        # Prompt for values
        echo ""
        info "Please review and update the .env file with your configuration:"
        info "  ${APP_DIR}/.env"
        echo ""
        info "Key settings to configure:"
        info "  - APP_URL: Your application URL"
        info "  - SMTP_*: Email server settings"
        info "  - GATEWAY_*: Gateway settings (if applicable)"
        info "  - RDP_DOMAIN: RDP domain name"
        echo ""

        read -rp "Do you want to edit .env now? [y/N]: " edit_env
        if [[ "${edit_env}" =~ ^[Yy]$ ]]; then
            ${EDITOR:-nano} "${APP_DIR}/.env"
        fi
    else
        warn ".env.example not found, creating minimal .env"
        cat > "${APP_DIR}/.env" <<ENVEOF
# Database
DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=${DB_NAME}
DB_USER=${DB_USER}
DB_PASSWORD=${DB_PASSWORD:-}

# Redis
REDIS_URL=redis://127.0.0.1:6379/0

# App
APP_SECRET_KEY=$(openssl rand -base64 48 | tr -d '/+=' | head -c 64)
APP_DEBUG=false
APP_URL=http://localhost:8080

# SMTP
SMTP_HOST=
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=

# Gateway
GATEWAY_ENABLED=false
GATEWAY_ADDRESS=rdp.2c2a.com
GATEWAY_PORT=443
GATEWAY_PAA_TOKEN_SIGNING_KEY=change-me-32-chars-minimum!!

# RDP
RDP_DOMAIN=2c2a.com

# Demo
2C2A_DEMO=0
ENVEOF
        ok "Minimal .env file created"
    fi
}

# ----------------------------------------------------------
# Step 6: Set file permissions
# ----------------------------------------------------------
set_permissions() {
    info "Setting file permissions..."

    # Create necessary directories
    mkdir -p "${APP_DIR}/storage/uploads"
    mkdir -p "${APP_DIR}/storage/cache"
    mkdir -p "${APP_DIR}/storage/logs"
    mkdir -p "${APP_DIR}/storage/certs"
    mkdir -p "${APP_DIR}/storage/sessions"

    # Set ownership
    chown -R ${APP_USER}:${APP_GROUP} "${APP_DIR}/storage"
    chown -R ${APP_USER}:${APP_GROUP} "${APP_DIR}/public"

    # Set writable permissions
    chmod -R 775 "${APP_DIR}/storage"
    chmod -R 755 "${APP_DIR}/public"

    # Ensure .env is readable by www-data but not world-readable
    if [[ -f "${APP_DIR}/.env" ]]; then
        chmod 640 "${APP_DIR}/.env"
        chown ${APP_USER}:${APP_GROUP} "${APP_DIR}/.env"
    fi

    # Create log directory
    mkdir -p "${LOG_DIR}"
    chown -R ${APP_USER}:${APP_GROUP} "${LOG_DIR}"

    ok "File permissions set"
}

# ----------------------------------------------------------
# Step 7: Copy configuration files
# ----------------------------------------------------------
copy_configs() {
    info "Copying configuration files..."

    # Copy nginx config
    if [[ -f "${DEPLOY_DIR}/nginx.conf" ]]; then
        cp "${DEPLOY_DIR}/nginx.conf" /etc/nginx/sites-available/2c2a
        # Remove default site if exists
        rm -f /etc/nginx/sites-enabled/default
        # Enable 2c2a site
        ln -sf /etc/nginx/sites-available/2c2a /etc/nginx/sites-enabled/2c2a
        ok "Nginx configuration installed"
    else
        warn "nginx.conf not found in ${DEPLOY_DIR}"
    fi

    # Copy PHP-FPM pool config
    if [[ -f "${DEPLOY_DIR}/php-fpm.conf" ]]; then
        cp "${DEPLOY_DIR}/php-fpm.conf" "/etc/php/${PHP_VERSION}/fpm/pool.d/2c2a.conf"
        # Remove default pool to avoid conflicts
        rm -f "/etc/php/${PHP_VERSION}/fpm/pool.d/www.conf"
        ok "PHP-FPM pool configuration installed"
    else
        warn "php-fpm.conf not found in ${DEPLOY_DIR}"
    fi

    # Copy supervisor config
    if [[ -f "${DEPLOY_DIR}/supervisor.conf" ]]; then
        cp "${DEPLOY_DIR}/supervisor.conf" /etc/supervisor/conf.d/2c2a.conf
        ok "Supervisor configuration installed"
    else
        warn "supervisor.conf not found in ${DEPLOY_DIR}"
    fi

    # Generate self-signed SSL certificate if none exists
    if [[ ! -f /etc/ssl/certs/2c2a.crt ]]; then
        info "Generating self-signed SSL certificate..."
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout /etc/ssl/private/2c2a.key \
            -out /etc/ssl/certs/2c2a.crt \
            -subj "/C=CN/ST=Beijing/L=Beijing/O=2c2a/CN=2c2a" \
            2>/dev/null
        ok "Self-signed SSL certificate generated (replace with proper cert in production)"
    fi
}

# ----------------------------------------------------------
# Step 8: Generate APP_SECRET_KEY
# ----------------------------------------------------------
generate_secret_key() {
    info "Checking APP_SECRET_KEY..."

    if [[ -f "${APP_DIR}/.env" ]]; then
        local current_key
        current_key=$(grep '^APP_SECRET_KEY=' "${APP_DIR}/.env" | cut -d'=' -f2-)

        if [[ -z "${current_key}" || "${current_key}" == "change-me-in-production" ]]; then
            local new_key
            new_key=$(openssl rand -base64 48 | tr -d '/+=' | head -c 64)
            sed -i "s/^APP_SECRET_KEY=.*/APP_SECRET_KEY=${new_key}/" "${APP_DIR}/.env"
            ok "APP_SECRET_KEY generated and set in .env"
        else
            ok "APP_SECRET_KEY already configured"
        fi
    fi
}

# ----------------------------------------------------------
# Step 9: Enable and start services
# ----------------------------------------------------------
start_services() {
    info "Enabling and starting services..."

    # Enable services to start on boot
    systemctl enable postgresql 2>/dev/null || true
    systemctl enable redis-server 2>/dev/null || true
    systemctl enable nginx 2>/dev/null || true
    systemctl enable php${PHP_VERSION}-fpm 2>/dev/null || true
    systemctl enable supervisor 2>/dev/null || true

    # Start services (if not already running)
    systemctl start postgresql 2>/dev/null || true
    systemctl start redis-server 2>/dev/null || true

    # Test nginx config
    nginx -t 2>/dev/null && {
        systemctl restart nginx 2>/dev/null || true
        ok "Nginx started"
    } || {
        warn "Nginx configuration test failed, not restarting"
    }

    # Restart PHP-FPM
    systemctl restart php${PHP_VERSION}-fpm 2>/dev/null || true
    ok "PHP-FPM started"

    # Restart Supervisor
    systemctl restart supervisor 2>/dev/null || true
    ok "Supervisor started"

    ok "All services enabled and started"
}

# ----------------------------------------------------------
# Step 10: Create initial admin user
# ----------------------------------------------------------
create_admin_user() {
    info "Creating initial admin user..."

    echo ""
    read -rp "Enter admin username [admin]: " admin_user
    admin_user="${admin_user:-admin}"

    read -rp "Enter admin email: " admin_email
    while [[ -z "${admin_email}" ]]; do
        error "Email is required"
        read -rp "Enter admin email: " admin_email
    done

    read -rsp "Enter admin password: " admin_pass
    echo ""
    while [[ -z "${admin_pass}" ]]; do
        error "Password is required"
        read -rsp "Enter admin password: " admin_pass
        echo ""
    done

    read -rsp "Confirm admin password: " admin_pass_confirm
    echo ""
    if [[ "${admin_pass}" != "${admin_pass_confirm}" ]]; then
        error "Passwords do not match"
    fi

    # Generate bcrypt hash using PHP
    local password_hash
    password_hash=$(php -r "echo password_hash('${admin_pass}', PASSWORD_BCRYPT, ['cost' => 12]);" 2>/dev/null)

    if [[ -z "${password_hash}" ]]; then
        warn "Could not generate bcrypt hash via PHP, using plain insert"
        password_hash="${admin_pass}"
    fi

    # Insert admin user into database
    local db_pass
    db_pass=$(grep '^DB_PASSWORD=' "${APP_DIR}/.env" 2>/dev/null | cut -d'=' -f2- || echo "")

    PGPASSWORD="${db_pass}" psql -h 127.0.0.1 -U "${DB_USER}" -d "${DB_NAME}" -c \
        "INSERT INTO users (username, email, password, is_active, is_staff, is_superuser)
         VALUES ('${admin_user}', '${admin_email}', '${password_hash}', true, true, true)
         ON CONFLICT (username) DO NOTHING;" 2>/dev/null

    # Create user profile
    local user_id
    user_id=$(PGPASSWORD="${db_pass}" psql -h 127.0.0.1 -U "${DB_USER}" -d "${DB_NAME}" -t -c \
        "SELECT id FROM users WHERE username = '${admin_user}';" 2>/dev/null | tr -d ' ')

    if [[ -n "${user_id}" ]]; then
        PGPASSWORD="${db_pass}" psql -h 127.0.0.1 -U "${DB_USER}" -d "${DB_NAME}" -c \
            "INSERT INTO user_profiles (user_id, nickname)
             VALUES (${user_id}, 'Administrator')
             ON CONFLICT (user_id) DO NOTHING;" 2>/dev/null
    fi

    ok "Admin user '${admin_user}' created"
}

# ----------------------------------------------------------
# Main
# ----------------------------------------------------------
main() {
    echo ""
    echo "=========================================="
    echo "  2c2a Application Installer"
    echo "  PHP + Node.js Deployment"
    echo "=========================================="
    echo ""

    check_root

    # Check if APP_DIR exists
    if [[ ! -d "${APP_DIR}" ]]; then
        error "Application directory ${APP_DIR} does not exist. Please clone/copy the application first."
    fi

    install_system_deps
    setup_database
    setup_env
    run_schema
    install_node_deps
    set_permissions
    copy_configs
    generate_secret_key
    start_services
    create_admin_user

    echo ""
    echo "=========================================="
    echo "  Installation Complete!"
    echo "=========================================="
    echo ""
    info "Application directory: ${APP_DIR}"
    info "Configuration file:    ${APP_DIR}/.env"
    info "Log directory:         ${LOG_DIR}"
    info ""
    info "Useful commands:"
    info "  supervisorctl status              - Check process status"
    info "  supervisorctl restart 2c2a:*      - Restart all 2c2a processes"
    info "  systemctl status nginx            - Check Nginx status"
    info "  systemctl status php${PHP_VERSION}-fpm  - Check PHP-FPM status"
    info "  tail -f ${LOG_DIR}/worker-default.stdout.log  - View worker logs"
    info ""
    info "Next steps:"
    info "  1. Review and update ${APP_DIR}/.env"
    info "  2. Replace self-signed SSL certificate with a proper one"
    info "  3. Configure SMTP settings for email notifications"
    info "  4. Configure Gateway settings if applicable"
    info ""
}

main "$@"
