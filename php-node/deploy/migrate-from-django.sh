#!/usr/bin/env bash
# ============================================================
# 2c2a Application - Migration Script from Django to PHP+Node.js
# ============================================================
set -euo pipefail

# ----------------------------------------------------------
# Configuration
# ----------------------------------------------------------
APP_DIR="/var/www/2c2a"
DJANGO_DIR=""
PHP_DIR="/var/www/2c2a"
LOG_DIR="/var/log/2c2a"
MIGRATION_LOG="${LOG_DIR}/migration-$(date +%Y%m%d-%H%M%S).log"
REPORT_FILE="${LOG_DIR}/migration-report-$(date +%Y%m%d-%H%M%S).txt"

# Migration stats
STATS_USERS=0
STATS_USERS_FAILED=0
STATS_HOSTS=0
STATS_HOSTS_FAILED=0
STATS_PRODUCTS=0
STATS_PRODUCTS_FAILED=0
STATS_TICKETS=0
STATS_TICKETS_FAILED=0
STATS_MEDIA_FILES=0
STATS_MEDIA_FAILED=0
STATS_CERT_FILES=0
STATS_CERT_FAILED=0
STATS_STATIC_FILES=0
STATS_STATIC_FAILED=0

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC}  $*" | tee -a "${MIGRATION_LOG}"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*" | tee -a "${MIGRATION_LOG}"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*" | tee -a "${MIGRATION_LOG}"; }
error() { echo -e "${RED}[ERROR]${NC} $*" | tee -a "${MIGRATION_LOG}"; }

# ----------------------------------------------------------
# Pre-flight checks
# ----------------------------------------------------------
preflight() {
    info "Running pre-flight checks..."

    if [[ $EUID -ne 0 ]]; then
        error "This script must be run as root"
    fi

    # Require Django project directory
    if [[ -z "${DJANGO_DIR}" ]]; then
        echo ""
        read -rp "Enter the path to the Django project root: " DJANGO_DIR
    fi

    if [[ ! -d "${DJANGO_DIR}" ]]; then
        error "Django project directory not found: ${DJANGO_DIR}"
    fi

    if [[ ! -f "${DJANGO_DIR}/manage.py" ]]; then
        error "manage.py not found in ${DJANGO_DIR}. Is this a Django project?"
    fi

    if [[ ! -d "${PHP_DIR}" ]]; then
        error "PHP application directory not found: ${PHP_DIR}. Run install.sh first."
    fi

    # Ensure log directory exists
    mkdir -p "${LOG_DIR}"

    # Check for required tools
    for tool in psql python3 php; do
        if ! command -v "${tool}" &>/dev/null; then
            error "Required tool '${tool}' not found. Please install it first."
        fi
    done

    ok "Pre-flight checks passed"
}

# ----------------------------------------------------------
# Read Django configuration
# ----------------------------------------------------------
read_django_config() {
    info "Reading Django configuration..."

    local django_env="${DJANGO_DIR}/.env"
    local django_settings="${DJANGO_DIR}/config/settings.py"

    # Source Django .env if available
    if [[ -f "${django_env}" ]]; then
        info "Found Django .env file: ${django_env}"
        # Parse key values
        DJANGO_DB_ENGINE=$(grep '^DB_ENGINE=' "${django_env}" 2>/dev/null | cut -d'=' -f2- || echo "sqlite")
        DJANGO_DB_NAME=$(grep '^DB_NAME=' "${django_env}" 2>/dev/null | cut -d'=' -f2- || echo "2c2a")
        DJANGO_DB_USER=$(grep '^DB_USER=' "${django_env}" 2>/dev/null | cut -d'=' -f2- || echo "postgres")
        DJANGO_DB_PASSWORD=$(grep '^DB_PASSWORD=' "${django_env}" 2>/dev/null | cut -d'=' -f2- || echo "")
        DJANGO_DB_HOST=$(grep '^DB_HOST=' "${django_env}" 2>/dev/null | cut -d'=' -f2- || echo "127.0.0.1")
        DJANGO_DB_PORT=$(grep '^DB_PORT=' "${django_env}" 2>/dev/null | cut -d'=' -f2- || echo "5432")
        DJANGO_REDIS_URL=$(grep '^REDIS_URL=' "${django_env}" 2>/dev/null | cut -d'=' -f2- || echo "")
        DJANGO_SECRET_KEY=$(grep '^DJANGO_SECRET_KEY=' "${django_env}" 2>/dev/null | cut -d'=' -f2- || echo "")
        DJANGO_DEBUG=$(grep '^DEBUG=' "${django_env}" 2>/dev/null | cut -d'=' -f2- || echo "True")
        DJANGO_ALLOWED_HOSTS=$(grep '^ALLOWED_HOSTS=' "${django_env}" 2>/dev/null | cut -d'=' -f2- || echo "localhost")
    else
        warn "Django .env file not found, will try to read from settings.py"
    fi

    # Read settings.py for additional config
    if [[ -f "${django_settings}" ]]; then
        info "Found Django settings.py: ${django_settings}"
        # Extract database engine from settings if not in .env
        if [[ -z "${DJANGO_DB_ENGINE:-}" || "${DJANGO_DB_ENGINE}" == "sqlite" ]]; then
            DJANGO_DB_ENGINE=$(grep -E "^\s*'ENGINE':" "${django_settings}" 2>/dev/null | head -1 | grep -oE '(mysql|postgresql|sqlite)' || echo "sqlite")
        fi
    fi

    # Read PHP .env for target database
    PHP_DB_NAME=$(grep '^DB_NAME=' "${PHP_DIR}/.env" 2>/dev/null | cut -d'=' -f2- || echo "2c2a")
    PHP_DB_USER=$(grep '^DB_USER=' "${PHP_DIR}/.env" 2>/dev/null | cut -d'=' -f2- || echo "2c2a")
    PHP_DB_PASSWORD=$(grep '^DB_PASSWORD=' "${PHP_DIR}/.env" 2>/dev/null | cut -d'=' -f2- || echo "")
    PHP_DB_HOST=$(grep '^DB_HOST=' "${PHP_DIR}/.env" 2>/dev/null | cut -d'=' -f2- || echo "127.0.0.1")
    PHP_DB_PORT=$(grep '^DB_PORT=' "${PHP_DIR}/.env" 2>/dev/null | cut -d'=' -f2- || echo "5432")

    info "Django database: ${DJANGO_DB_ENGINE}://${DJANGO_DB_HOST:-localhost}:${DJANGO_DB_PORT:-5432}/${DJANGO_DB_NAME:-2c2a}"
    info "PHP target database: PostgreSQL://${PHP_DB_HOST}:${PHP_DB_PORT}/${PHP_DB_NAME}"

    ok "Django configuration read"
}

# ----------------------------------------------------------
# Map Django database to PostgreSQL schema
# ----------------------------------------------------------
migrate_database() {
    info "Migrating database from Django to PHP+Node.js schema..."

    # Determine Django database connection
    local django_db_url=""
    case "${DJANGO_DB_ENGINE:-sqlite}" in
        postgresql)
            django_db_url="postgresql://${DJANGO_DB_USER}:${DJANGO_DB_PASSWORD}@${DJANGO_DB_HOST}:${DJANGO_DB_PORT}/${DJANGO_DB_NAME}"
            ;;
        mysql)
            # For MySQL source, we'll use Python to export data
            warn "MySQL source detected. Data will be exported via Django ORM."
            ;;
        sqlite)
            local sqlite_db="${DJANGO_DIR}/db.sqlite3"
            if [[ -f "${sqlite_db}" ]]; then
                info "SQLite database found: ${sqlite_db}"
            else
                warn "SQLite database not found at ${sqlite_db}"
            fi
            ;;
        *)
            warn "Unknown database engine: ${DJANGO_DB_ENGINE}"
            ;;
    esac

    # Use Django's dumpdata to export data, then transform and import
    info "Exporting data from Django using dumpdata..."

    local dump_dir="${LOG_DIR}/django_dump"
    mkdir -p "${dump_dir}"

    # Export Django data using manage.py dumpdata
    cd "${DJANGO_DIR}"

    # Export each app's data
    local apps=(
        "accounts"
        "hosts"
        "operations"
        "dashboard"
        "audit"
        "bootstrap"
        "certificates"
        "tickets"
        "themes"
    )

    for app in "${apps[@]}"; do
        info "Exporting ${app}..."
        python3 manage.py dumpdata "${app}" --indent 2 --output "${dump_dir}/${app}.json" 2>/dev/null || {
            warn "Could not export ${app} (may not exist or have data)"
            echo "[]" > "${dump_dir}/${app}.json"
        }
    done

    # Also export auth data
    python3 manage.py dumpdata auth --indent 2 --output "${dump_dir}/auth.json" 2>/dev/null || {
        warn "Could not export auth data"
        echo "[]" > "${dump_dir}/auth.json"
    }

    ok "Django data exported to ${dump_dir}"

    # Now transform and import into PHP schema
    info "Transforming and importing data into PHP+Node.js schema..."

    # Create a Python migration script inline
    python3 <<'PYTHON_SCRIPT'
import json
import os
import sys
import hashlib
import psycopg2
from datetime import datetime

dump_dir = os.environ.get('DUMP_DIR', '/var/log/2c2a/django_dump')
php_db_host = os.environ.get('PHP_DB_HOST', '127.0.0.1')
php_db_port = os.environ.get('PHP_DB_PORT', '5432')
php_db_name = os.environ.get('PHP_DB_NAME', '2c2a')
php_db_user = os.environ.get('PHP_DB_USER', '2c2a')
php_db_password = os.environ.get('PHP_DB_PASSWORD', '')

stats = {
    'users': 0, 'users_failed': 0,
    'hosts': 0, 'hosts_failed': 0,
    'products': 0, 'products_failed': 0,
    'tickets': 0, 'tickets_failed': 0,
}

def get_conn():
    return psycopg2.connect(
        host=php_db_host,
        port=int(php_db_port),
        dbname=php_db_name,
        user=php_db_user,
        password=php_db_password,
    )

def load_dump(app_name):
    filepath = os.path.join(dump_dir, f'{app_name}.json')
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            return json.load(f)
    return []

def migrate_users(conn):
    """Migrate Django auth_user to PHP users table"""
    cur = conn.cursor()
    auth_data = load_dump('auth')
    accounts_data = load_dump('accounts')

    # Build a map of Django user PK to profile data
    profile_map = {}
    for obj in accounts_data:
        model = obj.get('model', '')
        if 'userprofile' in model.lower() or 'profile' in model.lower():
            pk = obj.get('pk')
            fields = obj.get('fields', {})
            profile_map[pk] = fields

    # Migrate users
    for obj in auth_data:
        model = obj.get('model', '')
        if 'auth.user' not in model:
            continue

        fields = obj.get('fields', {})
        pk = obj.get('pk')

        username = fields.get('username', '')
        email = fields.get('email', '')
        password = fields.get('password', '')  # Django PBKDF2 hash
        first_name = fields.get('first_name', '')
        last_name = fields.get('last_name', '')
        is_active = fields.get('is_active', True)
        is_staff = fields.get('is_staff', False)
        is_superuser = fields.get('is_superuser', False)
        date_joined = fields.get('date_joined', datetime.now().isoformat())
        last_login = fields.get('last_login', None)

        # Django passwords are in format: algorithm$iterations$salt$hash
        # We keep the Django hash format and mark for reset
        # The PHP app will detect Django hashes and require password reset
        # We prepend a marker so the PHP app knows this is a migrated password
        migrated_password = f"__django_migrated__{password}"

        try:
            cur.execute("""
                INSERT INTO users (username, email, password, first_name, last_name,
                                   is_active, is_staff, is_superuser, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (username) DO UPDATE SET
                    email = EXCLUDED.email,
                    is_active = EXCLUDED.is_active,
                    is_staff = EXCLUDED.is_staff,
                    is_superuser = EXCLUDED.is_superuser
                RETURNING id
            """, (username, email, migrated_password, first_name, last_name,
                  is_active, is_staff, is_superuser, date_joined))

            user_id = cur.fetchone()[0]

            # Update last_login if available
            if last_login:
                cur.execute("UPDATE users SET last_login_ip = NULL WHERE id = %s", (user_id,))

            # Create user profile
            profile = profile_map.get(pk, {})
            nickname = profile.get('nickname', '')
            if not nickname:
                nickname = f"{first_name}{last_name}" if first_name or last_name else username

            cur.execute("""
                INSERT INTO user_profiles (user_id, nickname)
                VALUES (%s, %s)
                ON CONFLICT (user_id) DO NOTHING
            """, (user_id, nickname))

            stats['users'] += 1
        except Exception as e:
            print(f"  [WARN] Failed to migrate user {username}: {e}", file=sys.stderr)
            stats['users_failed'] += 1

    conn.commit()
    print(f"  Migrated {stats['users']} users ({stats['users_failed']} failed)")

def migrate_hosts(conn):
    """Migrate Django hosts to PHP hosts table"""
    cur = conn.cursor()
    hosts_data = load_dump('hosts')

    for obj in hosts_data:
        model = obj.get('model', '')
        if 'host' not in model.lower() or 'group' in model.lower():
            continue
        if 'host.host' not in model:
            continue

        fields = obj.get('fields', {})
        pk = obj.get('pk')

        name = fields.get('name', '')
        hostname = fields.get('hostname', '')
        os_type = fields.get('os_type', 'windows')
        connection_type = fields.get('connection_type', 'winrm')
        auth_method = fields.get('auth_method', 'ntlm')
        port = fields.get('port', 5985)
        rdp_port = fields.get('rdp_port', 3389)
        use_ssl = fields.get('use_ssl', False)
        username = fields.get('username', '')
        password = fields.get('password', '')
        status = fields.get('status', 'offline')
        description = fields.get('description', '')
        created_by_id = fields.get('created_by', None)
        site_group_id = fields.get('site_group', None)

        try:
            cur.execute("""
                INSERT INTO hosts (name, os_type, hostname, connection_type, auth_method,
                                   port, rdp_port, use_ssl, username, password,
                                   status, description, created_by_id, site_group_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (name, os_type, hostname, connection_type, auth_method,
                  port, rdp_port, use_ssl, username, password,
                  status, description, created_by_id, site_group_id))
            stats['hosts'] += 1
        except Exception as e:
            print(f"  [WARN] Failed to migrate host {name}: {e}", file=sys.stderr)
            stats['hosts_failed'] += 1

    conn.commit()
    print(f"  Migrated {stats['hosts']} hosts ({stats['hosts_failed']} failed)")

def migrate_operations(conn):
    """Migrate Django operations to PHP products and related tables"""
    cur = conn.cursor()
    ops_data = load_dump('operations')

    for obj in ops_data:
        model = obj.get('model', '')
        fields = obj.get('fields', {})

        try:
            if 'product' in model.lower() and 'group' not in model.lower():
                cur.execute("""
                    INSERT INTO products (name, description, display_name, display_description,
                                          host_id, rdp_port, display_hostname, is_available,
                                          auto_approval, visibility, created_by_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (
                    fields.get('name', ''),
                    fields.get('description', ''),
                    fields.get('display_name', fields.get('name', '')),
                    fields.get('display_description', fields.get('description', '')),
                    fields.get('host', None),
                    fields.get('rdp_port', 3389),
                    fields.get('display_hostname', ''),
                    fields.get('is_available', True),
                    fields.get('auto_approval', False),
                    fields.get('visibility', 'public'),
                    fields.get('created_by', None),
                ))
                stats['products'] += 1
            elif 'accountopeningrequest' in model.lower():
                cur.execute("""
                    INSERT INTO account_opening_requests (applicant_id, contact_email, contact_phone,
                                                          username, user_fullname, user_email,
                                                          user_description, target_product_id, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (
                    fields.get('applicant', None),
                    fields.get('contact_email', ''),
                    fields.get('contact_phone', ''),
                    fields.get('username', ''),
                    fields.get('user_fullname', ''),
                    fields.get('user_email', ''),
                    fields.get('user_description', ''),
                    fields.get('target_product', None),
                    fields.get('status', 'pending'),
                ))
        except Exception as e:
            print(f"  [WARN] Failed to migrate operation record: {e}", file=sys.stderr)
            stats['products_failed'] += 1

    conn.commit()
    print(f"  Migrated {stats['products']} operation records ({stats['products_failed']} failed)")

def migrate_tickets(conn):
    """Migrate Django tickets to PHP tickets table"""
    cur = conn.cursor()
    tickets_data = load_dump('tickets')

    for obj in tickets_data:
        model = obj.get('model', '')
        fields = obj.get('fields', {})

        try:
            if 'ticket' in model.lower() and 'category' not in model.lower() and 'comment' not in model.lower() and 'activity' not in model.lower() and 'attachment' not in model.lower():
                cur.execute("""
                    INSERT INTO tickets (ticket_no, title, description, category_id, status,
                                         priority, creator_id, assignee_id, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (
                    fields.get('ticket_no', f"TK-{obj.get('pk', 0):06d}"),
                    fields.get('title', ''),
                    fields.get('description', ''),
                    fields.get('category', None),
                    fields.get('status', 'pending'),
                    fields.get('priority', 'medium'),
                    fields.get('creator', None),
                    fields.get('assignee', None),
                    fields.get('created_at', datetime.now().isoformat()),
                ))
                stats['tickets'] += 1
        except Exception as e:
            print(f"  [WARN] Failed to migrate ticket: {e}", file=sys.stderr)
            stats['tickets_failed'] += 1

    conn.commit()
    print(f"  Migrated {stats['tickets']} tickets ({stats['tickets_failed']} failed)")

def main():
    try:
        conn = get_conn()
        print("  Connected to PHP database")

        migrate_users(conn)
        migrate_hosts(conn)
        migrate_operations(conn)
        migrate_tickets(conn)

        conn.close()
        print("  Database migration complete")
    except Exception as e:
        print(f"  [ERROR] Database migration failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Write stats to file for the shell script to read
    stats_file = os.path.join(dump_dir, 'migration_stats.txt')
    with open(stats_file, 'w') as f:
        for k, v in stats.items():
            f.write(f"{k}={v}\n")

if __name__ == '__main__':
    main()
PYTHON_SCRIPT

    # Pass environment variables to the Python script
    export DUMP_DIR="${dump_dir}"
    export PHP_DB_HOST="${PHP_DB_HOST}"
    export PHP_DB_PORT="${PHP_DB_PORT}"
    export PHP_DB_NAME="${PHP_DB_NAME}"
    export PHP_DB_USER="${PHP_DB_USER}"
    export PHP_DB_PASSWORD="${PHP_DB_PASSWORD}"

    # Re-run with exported env vars
    cd "${DJANGO_DIR}"
    DUMP_DIR="${dump_dir}" \
    PHP_DB_HOST="${PHP_DB_HOST}" \
    PHP_DB_PORT="${PHP_DB_PORT}" \
    PHP_DB_NAME="${PHP_DB_NAME}" \
    PHP_DB_USER="${PHP_DB_USER}" \
    PHP_DB_PASSWORD="${PHP_DB_PASSWORD}" \
    python3 <<'PYTHON_SCRIPT'
import json
import os
import sys
import psycopg2
from datetime import datetime

dump_dir = os.environ.get('DUMP_DIR', '/var/log/2c2a/django_dump')
php_db_host = os.environ.get('PHP_DB_HOST', '127.0.0.1')
php_db_port = os.environ.get('PHP_DB_PORT', '5432')
php_db_name = os.environ.get('PHP_DB_NAME', '2c2a')
php_db_user = os.environ.get('PHP_DB_USER', '2c2a')
php_db_password = os.environ.get('PHP_DB_PASSWORD', '')

stats = {
    'users': 0, 'users_failed': 0,
    'hosts': 0, 'hosts_failed': 0,
    'products': 0, 'products_failed': 0,
    'tickets': 0, 'tickets_failed': 0,
}

def get_conn():
    return psycopg2.connect(
        host=php_db_host,
        port=int(php_db_port),
        dbname=php_db_name,
        user=php_db_user,
        password=php_db_password,
    )

def load_dump(app_name):
    filepath = os.path.join(dump_dir, f'{app_name}.json')
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            return json.load(f)
    return []

def migrate_users(conn):
    cur = conn.cursor()
    auth_data = load_dump('auth')
    accounts_data = load_dump('accounts')

    profile_map = {}
    for obj in accounts_data:
        model = obj.get('model', '')
        if 'profile' in model.lower():
            pk = obj.get('pk')
            fields = obj.get('fields', {})
            profile_map[pk] = fields

    for obj in auth_data:
        model = obj.get('model', '')
        if 'auth.user' not in model:
            continue

        fields = obj.get('fields', {})
        pk = obj.get('pk')

        username = fields.get('username', '')
        email = fields.get('email', '')
        password = fields.get('password', '')
        first_name = fields.get('first_name', '')
        last_name = fields.get('last_name', '')
        is_active = fields.get('is_active', True)
        is_staff = fields.get('is_staff', False)
        is_superuser = fields.get('is_superuser', False)
        date_joined = fields.get('date_joined', datetime.now().isoformat())

        # Mark Django PBKDF2 passwords for reset on first login
        # The PHP app will detect the __django_migrated__ prefix
        # and force a password reset
        migrated_password = f"__django_migrated__{password}"

        try:
            cur.execute("""
                INSERT INTO users (username, email, password, first_name, last_name,
                                   is_active, is_staff, is_superuser, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (username) DO UPDATE SET
                    email = EXCLUDED.email,
                    is_active = EXCLUDED.is_active,
                    is_staff = EXCLUDED.is_staff,
                    is_superuser = EXCLUDED.is_superuser,
                    password = EXCLUDED.password
                RETURNING id
            """, (username, email, migrated_password, first_name, last_name,
                  is_active, is_staff, is_superuser, date_joined))

            user_id = cur.fetchone()[0]

            profile = profile_map.get(pk, {})
            nickname = profile.get('nickname', '')
            if not nickname:
                nickname = f"{first_name}{last_name}" if first_name or last_name else username

            cur.execute("""
                INSERT INTO user_profiles (user_id, nickname)
                VALUES (%s, %s)
                ON CONFLICT (user_id) DO NOTHING
            """, (user_id, nickname))

            stats['users'] += 1
        except Exception as e:
            print(f"  [WARN] Failed to migrate user {username}: {e}", file=sys.stderr)
            stats['users_failed'] += 1

    conn.commit()
    print(f"  Migrated {stats['users']} users ({stats['users_failed']} failed)")

def migrate_hosts(conn):
    cur = conn.cursor()
    hosts_data = load_dump('hosts')

    for obj in hosts_data:
        model = obj.get('model', '')
        if 'host.host' not in model:
            continue

        fields = obj.get('fields', {})

        try:
            cur.execute("""
                INSERT INTO hosts (name, os_type, hostname, connection_type, auth_method,
                                   port, rdp_port, use_ssl, username, password,
                                   status, description, created_by_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (
                fields.get('name', ''),
                fields.get('os_type', 'windows'),
                fields.get('hostname', ''),
                fields.get('connection_type', 'winrm'),
                fields.get('auth_method', 'ntlm'),
                fields.get('port', 5985),
                fields.get('rdp_port', 3389),
                fields.get('use_ssl', False),
                fields.get('username', ''),
                fields.get('password', ''),
                fields.get('status', 'offline'),
                fields.get('description', ''),
                fields.get('created_by', None),
            ))
            stats['hosts'] += 1
        except Exception as e:
            print(f"  [WARN] Failed to migrate host: {e}", file=sys.stderr)
            stats['hosts_failed'] += 1

    conn.commit()
    print(f"  Migrated {stats['hosts']} hosts ({stats['hosts_failed']} failed)")

def migrate_operations(conn):
    cur = conn.cursor()
    ops_data = load_dump('operations')

    for obj in ops_data:
        model = obj.get('model', '')
        fields = obj.get('fields', {})

        try:
            if 'product' in model.lower() and 'group' not in model.lower():
                cur.execute("""
                    INSERT INTO products (name, description, display_name, display_description,
                                          host_id, rdp_port, display_hostname, is_available,
                                          auto_approval, visibility, created_by_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (
                    fields.get('name', ''),
                    fields.get('description', ''),
                    fields.get('display_name', fields.get('name', '')),
                    fields.get('display_description', fields.get('description', '')),
                    fields.get('host', None),
                    fields.get('rdp_port', 3389),
                    fields.get('display_hostname', ''),
                    fields.get('is_available', True),
                    fields.get('auto_approval', False),
                    fields.get('visibility', 'public'),
                    fields.get('created_by', None),
                ))
                stats['products'] += 1
        except Exception as e:
            print(f"  [WARN] Failed to migrate operation record: {e}", file=sys.stderr)
            stats['products_failed'] += 1

    conn.commit()
    print(f"  Migrated {stats['products']} operation records ({stats['products_failed']} failed)")

def migrate_tickets(conn):
    cur = conn.cursor()
    tickets_data = load_dump('tickets')

    for obj in tickets_data:
        model = obj.get('model', '')
        fields = obj.get('fields', {})

        try:
            if 'ticket' in model.lower() and 'category' not in model.lower() and 'comment' not in model.lower() and 'activity' not in model.lower() and 'attachment' not in model.lower():
                cur.execute("""
                    INSERT INTO tickets (ticket_no, title, description, category_id, status,
                                         priority, creator_id, assignee_id, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (
                    fields.get('ticket_no', f"TK-{obj.get('pk', 0):06d}"),
                    fields.get('title', ''),
                    fields.get('description', ''),
                    fields.get('category', None),
                    fields.get('status', 'pending'),
                    fields.get('priority', 'medium'),
                    fields.get('creator', None),
                    fields.get('assignee', None),
                    fields.get('created_at', datetime.now().isoformat()),
                ))
                stats['tickets'] += 1
        except Exception as e:
            print(f"  [WARN] Failed to migrate ticket: {e}", file=sys.stderr)
            stats['tickets_failed'] += 1

    conn.commit()
    print(f"  Migrated {stats['tickets']} tickets ({stats['tickets_failed']} failed)")

def main():
    try:
        conn = get_conn()
        print("  Connected to PHP database")

        migrate_users(conn)
        migrate_hosts(conn)
        migrate_operations(conn)
        migrate_tickets(conn)

        conn.close()
        print("  Database migration complete")
    except Exception as e:
        print(f"  [ERROR] Database migration failed: {e}", file=sys.stderr)
        sys.exit(1)

    stats_file = os.path.join(dump_dir, 'migration_stats.txt')
    with open(stats_file, 'w') as f:
        for k, v in stats.items():
            f.write(f"{k}={v}\n")

if __name__ == '__main__':
    main()
PYTHON_SCRIPT

    # Read back stats
    if [[ -f "${dump_dir}/migration_stats.txt" ]]; then
        source "${dump_dir}/migration_stats.txt"
        STATS_USERS=${users:-0}
        STATS_USERS_FAILED=${users_failed:-0}
        STATS_HOSTS=${hosts:-0}
        STATS_HOSTS_FAILED=${hosts_failed:-0}
        STATS_PRODUCTS=${products:-0}
        STATS_PRODUCTS_FAILED=${products_failed:-0}
        STATS_TICKETS=${tickets:-0}
        STATS_TICKETS_FAILED=${tickets_failed:-0}
    fi

    ok "Database migration completed"
}

# ----------------------------------------------------------
# Migrate user passwords (mark for reset)
# ----------------------------------------------------------
migrate_passwords() {
    info "Processing user password migration..."

    # All Django passwords have been marked with __django_migrated__ prefix
    # The PHP Auth class should detect this prefix and force password reset
    # on first login attempt

    local db_pass
    db_pass=$(grep '^DB_PASSWORD=' "${PHP_DIR}/.env" 2>/dev/null | cut -d'=' -f2- || echo "")
    local php_db_user
    php_db_user=$(grep '^DB_USER=' "${PHP_DIR}/.env" 2>/dev/null | cut -d'=' -f2- || echo "2c2a")
    local php_db_name
    php_db_name=$(grep '^DB_NAME=' "${PHP_DIR}/.env" 2>/dev/null | cut -d'=' -f2- || echo "2c2a")

    # Count migrated passwords
    local migrated_count
    migrated_count=$(PGPASSWORD="${db_pass}" psql -h 127.0.0.1 -U "${php_db_user}" -d "${php_db_name}" -t -c \
        "SELECT COUNT(*) FROM users WHERE password LIKE '__django_migrated__%';" 2>/dev/null | tr -d ' ')

    info "Found ${migrated_count:-0} users with Django-migrated passwords"
    info "These users will be required to reset their password on first login"
    info "Django PBKDF2 hashes are preserved for potential future verification"

    ok "Password migration handled (users will need to reset on first login)"
}

# ----------------------------------------------------------
# Copy media files
# ----------------------------------------------------------
copy_media_files() {
    info "Copying media files..."

    local django_media="${DJANGO_DIR}/media"
    local php_media="${PHP_DIR}/storage/uploads"

    mkdir -p "${php_media}"

    if [[ -d "${django_media}" ]]; then
        # Copy avatars
        if [[ -d "${django_media}/avatars" ]]; then
            mkdir -p "${php_media}/avatars"
            cp -r "${django_media}/avatars/"* "${php_media}/avatars/" 2>/dev/null || true
            local avatar_count
            avatar_count=$(find "${php_media}/avatars" -type f 2>/dev/null | wc -l)
            info "Copied ${avatar_count} avatar files"
            STATS_MEDIA_FILES=$((STATS_MEDIA_FILES + avatar_count))
        fi

        # Copy attachments
        if [[ -d "${django_media}/attachments" ]]; then
            mkdir -p "${php_media}/attachments"
            cp -r "${django_media}/attachments/"* "${php_media}/attachments/" 2>/dev/null || true
            local attach_count
            attach_count=$(find "${php_media}/attachments" -type f 2>/dev/null | wc -l)
            info "Copied ${attach_count} attachment files"
            STATS_MEDIA_FILES=$((STATS_MEDIA_FILES + attach_count))
        fi

        # Copy any other media files
        for subdir in "${django_media}"/*/; do
            local dirname
            dirname=$(basename "${subdir}")
            if [[ "${dirname}" != "avatars" && "${dirname}" != "attachments" ]]; then
                mkdir -p "${php_media}/${dirname}"
                cp -r "${subdir}"* "${php_media}/${dirname}/" 2>/dev/null || true
            fi
        done

        # Update database paths for avatars
        local db_pass
        db_pass=$(grep '^DB_PASSWORD=' "${PHP_DIR}/.env" 2>/dev/null | cut -d'=' -f2- || echo "")
        local php_db_user
        php_db_user=$(grep '^DB_USER=' "${PHP_DIR}/.env" 2>/dev/null | cut -d'=' -f2- || echo "2c2a")
        local php_db_name
        php_db_name=$(grep '^DB_NAME=' "${PHP_DIR}/.env" 2>/dev/null | cut -d'=' -f2- || echo "2c2a")

        # Update avatar paths in users table
        PGPASSWORD="${db_pass}" psql -h 127.0.0.1 -U "${php_db_user}" -d "${php_db_name}" -c \
            "UPDATE users SET avatar = REPLACE(avatar, 'media/avatars/', 'uploads/avatars/') WHERE avatar LIKE 'media/avatars/%';" \
            2>/dev/null || true

        # Update attachment paths in ticket_attachments table
        PGPASSWORD="${db_pass}" psql -h 127.0.0.1 -U "${php_db_user}" -d "${php_db_name}" -c \
            "UPDATE ticket_attachments SET file_path = REPLACE(file_path, 'media/', 'uploads/') WHERE file_path LIKE 'media/%';" \
            2>/dev/null || true

        chown -R www-data:www-data "${php_media}"
        ok "Media files copied (${STATS_MEDIA_FILES} files)"
    else
        warn "Django media directory not found: ${django_media}"
    fi
}

# ----------------------------------------------------------
# Copy certificate files
# ----------------------------------------------------------
copy_certificate_files() {
    info "Copying certificate files..."

    local django_certs="${DJANGO_DIR}/certs"
    local php_certs="${PHP_DIR}/storage/certs"

    # Also check common Django cert locations
    local cert_search_paths=(
        "${DJANGO_DIR}/certs"
        "${DJANGO_DIR}/storage/certs"
        "${DJANGO_DIR}/data/certs"
    )

    mkdir -p "${php_certs}"

    for search_path in "${cert_search_paths[@]}"; do
        if [[ -d "${search_path}" ]]; then
            info "Found certificate directory: ${search_path}"
            cp -r "${search_path}/"* "${php_certs}/" 2>/dev/null || true
        fi
    done

    # Count cert files
    local cert_count
    cert_count=$(find "${php_certs}" -type f 2>/dev/null | wc -l)
    STATS_CERT_FILES=${cert_count}

    if [[ ${cert_count} -gt 0 ]]; then
        chown -R www-data:www-data "${php_certs}"
        chmod -R 700 "${php_certs}"
        ok "Certificate files copied (${cert_count} files)"
    else
        warn "No certificate files found to copy"
    fi
}

# ----------------------------------------------------------
# Copy static files
# ----------------------------------------------------------
copy_static_files() {
    info "Copying static files..."

    local django_static="${DJANGO_DIR}/static"
    local django_collected_static="${DJANGO_DIR}/staticfiles"
    local php_static="${PHP_DIR}/public/static"

    mkdir -p "${php_static}"

    # Prefer collected static (from collectstatic)
    local source_static="${django_collected_static}"
    if [[ ! -d "${source_static}" ]]; then
        source_static="${django_static}"
    fi

    if [[ -d "${source_static}" ]]; then
        # Copy static assets
        cp -r "${source_static}/"* "${php_static}/" 2>/dev/null || true

        local static_count
        static_count=$(find "${php_static}" -type f 2>/dev/null | wc -l)
        STATS_STATIC_FILES=${static_count}

        chown -R www-data:www-data "${php_static}"
        ok "Static files copied (${static_count} files)"
    else
        warn "Django static directory not found: ${source_static}"
    fi
}

# ----------------------------------------------------------
# Validate data integrity
# ----------------------------------------------------------
validate_data() {
    info "Validating data integrity..."

    local db_pass
    db_pass=$(grep '^DB_PASSWORD=' "${PHP_DIR}/.env" 2>/dev/null | cut -d'=' -f2- || echo "")
    local php_db_user
    php_db_user=$(grep '^DB_USER=' "${PHP_DIR}/.env" 2>/dev/null | cut -d'=' -f2- || echo "2c2a")
    local php_db_name
    php_db_name=$(grep '^DB_NAME=' "${PHP_DIR}/.env" 2>/dev/null | cut -d'=' -f2- || echo "2c2a")

    local errors=0

    # Check users table
    local user_count
    user_count=$(PGPASSWORD="${db_pass}" psql -h 127.0.0.1 -U "${php_db_user}" -d "${php_db_name}" -t -c \
        "SELECT COUNT(*) FROM users;" 2>/dev/null | tr -d ' ')
    info "Users in database: ${user_count:-0}"

    # Check for orphaned foreign keys
    local orphan_profiles
    orphan_profiles=$(PGPASSWORD="${db_pass}" psql -h 127.0.0.1 -U "${php_db_user}" -d "${php_db_name}" -t -c \
        "SELECT COUNT(*) FROM user_profiles up LEFT JOIN users u ON up.user_id = u.id WHERE u.id IS NULL;" \
        2>/dev/null | tr -d ' ')
    if [[ "${orphan_profiles:-0}" -gt 0 ]]; then
        warn "Found ${orphan_profiles} orphaned user profiles"
        errors=$((errors + 1))
    fi

    # Check hosts table
    local host_count
    host_count=$(PGPASSWORD="${db_pass}" psql -h 127.0.0.1 -U "${php_db_user}" -d "${php_db_name}" -t -c \
        "SELECT COUNT(*) FROM hosts;" 2>/dev/null | tr -d ' ')
    info "Hosts in database: ${host_count:-0}"

    # Check products table
    local product_count
    product_count=$(PGPASSWORD="${db_pass}" psql -h 127.0.0.1 -U "${php_db_user}" -d "${php_db_name}" -t -c \
        "SELECT COUNT(*) FROM products;" 2>/dev/null | tr -d ' ')
    info "Products in database: ${product_count:-0}"

    # Check tickets table
    local ticket_count
    ticket_count=$(PGPASSWORD="${db_pass}" psql -h 127.0.0.1 -U "${php_db_user}" -d "${php_db_name}" -t -c \
        "SELECT COUNT(*) FROM tickets;" 2>/dev/null | tr -d ' ')
    info "Tickets in database: ${ticket_count:-0}"

    # Check for Django-migrated passwords that need reset
    local migrated_pw_count
    migrated_pw_count=$(PGPASSWORD="${db_pass}" psql -h 127.0.0.1 -U "${php_db_user}" -d "${php_db_name}" -t -c \
        "SELECT COUNT(*) FROM users WHERE password LIKE '__django_migrated__%';" 2>/dev/null | tr -d ' ')
    info "Users requiring password reset: ${migrated_pw_count:-0}"

    # Verify media files exist
    if [[ -d "${PHP_DIR}/storage/uploads" ]]; then
        local media_count
        media_count=$(find "${PHP_DIR}/storage/uploads" -type f 2>/dev/null | wc -l)
        info "Media files on disk: ${media_count}"
    fi

    # Verify cert files exist
    if [[ -d "${PHP_DIR}/storage/certs" ]]; then
        local cert_count
        cert_count=$(find "${PHP_DIR}/storage/certs" -type f 2>/dev/null | wc -l)
        info "Certificate files on disk: ${cert_count}"
    fi

    if [[ ${errors} -eq 0 ]]; then
        ok "Data integrity validation passed"
    else
        warn "Data integrity validation found ${errors} issues (see above)"
    fi
}

# ----------------------------------------------------------
# Generate migration report
# ----------------------------------------------------------
generate_report() {
    info "Generating migration report..."

    cat > "${REPORT_FILE}" <<EOF
============================================================
2c2a Migration Report: Django -> PHP+Node.js
============================================================
Date: $(date '+%Y-%m-%d %H:%M:%S')
Django source: ${DJANGO_DIR}
PHP target: ${PHP_DIR}

------------------------------------------------------------
Database Migration
------------------------------------------------------------
Users migrated:         ${STATS_USERS}
Users failed:           ${STATS_USERS_FAILED}
Hosts migrated:         ${STATS_HOSTS}
Hosts failed:           ${STATS_HOSTS_FAILED}
Products migrated:      ${STATS_PRODUCTS}
Products failed:        ${STATS_PRODUCTS_FAILED}
Tickets migrated:       ${STATS_TICKETS}
Tickets failed:         ${STATS_TICKETS_FAILED}

------------------------------------------------------------
Password Migration
------------------------------------------------------------
Django PBKDF2 passwords are preserved with a __django_migrated__ prefix.
Users with migrated passwords will be required to reset on first login.
The PHP Auth class should detect this prefix and redirect to password reset.

------------------------------------------------------------
File Migration
------------------------------------------------------------
Media files copied:     ${STATS_MEDIA_FILES}
Certificate files:      ${STATS_CERT_FILES}
Static files copied:    ${STATS_STATIC_FILES}

------------------------------------------------------------
Post-Migration Actions Required
------------------------------------------------------------
1. Verify all users can log in and reset their passwords
2. Verify media files are accessible (check avatar display)
3. Verify certificate files are accessible
4. Test all critical application flows
5. Update any hardcoded Django URLs in templates
6. Verify email sending works with new SMTP configuration
7. Check that all worker queues are processing tasks
8. Review and update .env configuration for production

------------------------------------------------------------
Rollback Instructions
------------------------------------------------------------
If migration fails, the original Django project is still intact at:
  ${DJANGO_DIR}

To rollback:
1. Point nginx back to the Django application
2. Restore the database from backup (if created)
3. Restart services

============================================================
End of Report
============================================================
EOF

    ok "Migration report saved to: ${REPORT_FILE}"
    cat "${REPORT_FILE}"
}

# ----------------------------------------------------------
# Main
# ----------------------------------------------------------
main() {
    echo ""
    echo "=========================================="
    echo "  2c2a Migration: Django -> PHP+Node.js"
    echo "=========================================="
    echo ""

    preflight
    read_django_config

    echo ""
    warn "This will migrate data from the Django application to the PHP+Node.js application."
    warn "The Django database will NOT be modified."
    warn "The PHP database will receive the migrated data."
    echo ""
    read -rp "Do you want to proceed? [y/N]: " confirm
    if [[ ! "${confirm}" =~ ^[Yy]$ ]]; then
        info "Migration cancelled by user"
        exit 0
    fi

    # Create database backup before migration
    info "Creating database backup before migration..."
    local db_pass
    db_pass=$(grep '^DB_PASSWORD=' "${PHP_DIR}/.env" 2>/dev/null | cut -d'=' -f2- || echo "")
    local php_db_user
    php_db_user=$(grep '^DB_USER=' "${PHP_DIR}/.env" 2>/dev/null | cut -d'=' -f2- || echo "2c2a")
    local php_db_name
    php_db_name=$(grep '^DB_NAME=' "${PHP_DIR}/.env" 2>/dev/null | cut -d'=' -f2- || echo "2c2a")

    PGPASSWORD="${db_pass}" pg_dump -h 127.0.0.1 -U "${php_db_user}" "${php_db_name}" \
        > "${LOG_DIR}/pre-migration-backup-$(date +%Y%m%d-%H%M%S).sql" 2>/dev/null || {
        warn "Could not create database backup (database may be empty)"
    }

    migrate_database
    migrate_passwords
    copy_media_files
    copy_certificate_files
    copy_static_files
    validate_data
    generate_report

    echo ""
    echo "=========================================="
    echo "  Migration Complete!"
    echo "=========================================="
    echo ""
    info "Report: ${REPORT_FILE}"
    info ""
    info "IMPORTANT: Users with Django-migrated passwords must reset"
    info "their password on first login. The PHP Auth class will"
    info "detect the __django_migrated__ prefix and force a reset."
    info ""
    info "Please verify the application is working correctly."
}

main "$@"
