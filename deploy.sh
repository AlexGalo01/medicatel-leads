#!/usr/bin/env bash
# deploy.sh — Deploya medicatel-leads en EC2 con Apache
# Uso: ./deploy.sh [--no-build] [--setup-apache DOMAIN]
#
# Requisitos en EC2:
#   - git, docker, docker compose plugin
#   - Apache con mod_proxy habilitado
#   - .env presente en el directorio del proyecto

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ---------- Colores ----------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[deploy]${NC} $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC}  $*"; }
error() { echo -e "${RED}[error]${NC} $*"; exit 1; }

# ---------- Flags ----------
NO_BUILD=false
SETUP_APACHE=false
DOMAIN=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --no-build)   NO_BUILD=true ;;
    --setup-apache)
      SETUP_APACHE=true
      DOMAIN="${2:?'--setup-apache requiere un dominio, ej: --setup-apache app.tudominio.com'}"
      shift ;;
    *) error "Argumento desconocido: $1" ;;
  esac
  shift
done

# ---------- Validaciones ----------
[[ -f ".env" ]] || error "No se encontró .env — cópialo antes de hacer deploy"
command -v docker  &>/dev/null || error "docker no está instalado"
docker compose version &>/dev/null || error "docker compose plugin no está instalado"

# ---------- 1. Git pull ----------
info "Actualizando código…"
git pull --ff-only

# ---------- 2. Build ----------
if [[ "$NO_BUILD" == false ]]; then
  info "Construyendo imágenes Docker…"
  docker compose build --pull
else
  warn "Saltando build (--no-build)"
fi

# ---------- 3. Levantar servicios ----------
info "Levantando servicios…"
docker compose up -d --remove-orphans

# Esperar que el backend esté healthy
info "Esperando que el backend esté listo…"
TRIES=0
until docker inspect mle-backend --format='{{.State.Health.Status}}' 2>/dev/null | grep -q "healthy"; do
  TRIES=$((TRIES + 1))
  [[ $TRIES -ge 30 ]] && error "Backend no llegó a 'healthy' en 60s — revisa: docker compose logs backend"
  sleep 2
done
info "Backend healthy ✓"

# ---------- 4. Migraciones SQL ----------
info "Aplicando migraciones SQL…"
source .env  # carga DATABASE_URL

# Extraer componentes de la URL de postgres
# Formato: postgresql://user:pass@host:port/dbname?params
DB_URL="${DATABASE_URL}"

if command -v psql &>/dev/null; then
  for sql_file in $(ls backend/sql/*.sql 2>/dev/null | sort); do
    info "  Aplicando: $sql_file"
    psql "$DB_URL" -f "$sql_file" 2>&1 | grep -v "^NOTICE" || true
  done
  info "Migraciones aplicadas ✓"
else
  warn "psql no encontrado — saltando migraciones automáticas"
  warn "Aplica manualmente: psql \"\$DATABASE_URL\" -f backend/sql/<archivo>.sql"
fi

# ---------- 5. Configurar Apache (opcional) ----------
if [[ "$SETUP_APACHE" == true ]]; then
  info "Configurando Apache para dominio: $DOMAIN"

  VHOST_FILE="/etc/apache2/sites-available/medicatel-leads.conf"

  cat > /tmp/medicatel-leads.conf <<APACHE
<VirtualHost *:80>
    ServerName ${DOMAIN}

    # Proxy al contenedor frontend (nginx interno maneja /api/ → backend)
    ProxyPreserveHost On
    ProxyRequests Off

    # WebSocket support
    RewriteEngine On
    RewriteCond %{HTTP:Upgrade} websocket [NC]
    RewriteCond %{HTTP:Connection} upgrade [NC]
    RewriteRule ^/?(.*) "ws://127.0.0.1:3000/\$1" [P,L]

    ProxyPass        / http://127.0.0.1:3000/
    ProxyPassReverse / http://127.0.0.1:3000/

    # Timeouts largos para búsquedas Exa (pueden tardar >60s)
    ProxyTimeout 120
    Timeout 120

    ErrorLog \${APACHE_LOG_DIR}/medicatel-leads-error.log
    CustomLog \${APACHE_LOG_DIR}/medicatel-leads-access.log combined
</VirtualHost>
APACHE

  sudo mv /tmp/medicatel-leads.conf "$VHOST_FILE"
  sudo a2enmod proxy proxy_http rewrite 2>/dev/null || true
  sudo a2ensite medicatel-leads 2>/dev/null || true
  sudo apache2ctl configtest && sudo systemctl reload apache2
  info "Apache configurado ✓"
  info "Sitio disponible en: http://${DOMAIN}"
  warn "Para HTTPS: sudo certbot --apache -d ${DOMAIN}"
fi

# ---------- Done ----------
echo ""
info "Deploy completado ✓"
info "  Frontend: http://localhost:3000"
info "  Backend:  http://localhost:8000"
[[ "$SETUP_APACHE" == true ]] && info "  Público:  http://${DOMAIN}"
echo ""
info "Logs: docker compose logs -f"
