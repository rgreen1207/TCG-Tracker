#!/usr/bin/env bash
# =============================================================================
# Pokemon Price Tracker — Raspberry Pi Setup Script
# Run as the 'pi' user: bash setup.sh
# =============================================================================
set -euo pipefail

REPO_DIR="$HOME/pokemon-tracker"
VENV_DIR="$REPO_DIR/venv"
SERVICE_NAME="pokemon-tracker"
NGINX_CONF="/etc/nginx/sites-available/$SERVICE_NAME"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── Preflight ─────────────────────────────────────────────────
[[ "$(id -u)" -eq 0 ]] && error "Do not run as root. Run as user 'pi'."
[[ -d "$REPO_DIR" ]]   || error "Project not found at $REPO_DIR. Clone/copy it there first."

info "Starting Pokemon Price Tracker setup…"

# ── System packages ───────────────────────────────────────────
info "Installing system dependencies…"
sudo apt-get update -q
sudo apt-get install -y -q \
    python3 python3-pip python3-venv \
    nginx certbot python3-certbot-nginx \
    sqlite3 curl git

# ── Python venv ───────────────────────────────────────────────
info "Creating Python virtual environment…"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$REPO_DIR/requirements.txt" -q
info "Python dependencies installed."

# ── Data & log directories ────────────────────────────────────
mkdir -p "$REPO_DIR/data" "$REPO_DIR/logs"
chmod 700 "$REPO_DIR/data"

# ── .env file ────────────────────────────────────────────────
if [[ ! -f "$REPO_DIR/.env" ]]; then
    cp "$REPO_DIR/.env.example" "$REPO_DIR/.env"
    # Auto-generate a SECRET_KEY
    SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s/change_me_to_a_random_32_byte_hex_string/$SECRET/" "$REPO_DIR/.env"
    warn ".env created from template. EDIT IT NOW before starting the service:"
    warn "  nano $REPO_DIR/.env"
    warn "  → Set ADMIN_PASSWORD, eBay keys, Pushover keys, etc."
else
    info ".env already exists — skipping."
fi

# ── Systemd service ───────────────────────────────────────────
info "Installing systemd service…"
sudo cp "$REPO_DIR/deploy/pokemon-tracker.service" "/etc/systemd/system/$SERVICE_NAME.service"
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
info "Service installed (not started yet — configure .env first)."

# ── Nginx ─────────────────────────────────────────────────────
info "Configuring Nginx…"

# Detect public IP for placeholder if no domain given
PUBLIC_IP=$(curl -sf https://api.ipify.org || echo "YOUR_PI_IP")

sudo cp "$REPO_DIR/deploy/nginx.conf" "$NGINX_CONF"
# Use self-signed cert if no domain/certbot yet (you can upgrade later)
if [[ ! -f /etc/letsencrypt/live/*/fullchain.pem ]]; then
    warn "No Let's Encrypt cert found — setting up self-signed cert for now."
    warn "After pointing a domain at this Pi, run:"
    warn "  sudo certbot --nginx -d YOUR_DOMAIN"

    # Generate self-signed cert
    sudo mkdir -p /etc/ssl/pokemon-tracker
    sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout /etc/ssl/pokemon-tracker/selfsigned.key \
        -out    /etc/ssl/pokemon-tracker/selfsigned.crt \
        -subj   "/CN=$PUBLIC_IP" 2>/dev/null

    # Rewrite nginx conf to use self-signed
    sudo bash -c "cat > $NGINX_CONF" <<NGINXEOF
limit_req_zone \$binary_remote_addr zone=general:10m rate=60r/m;
limit_req_zone \$binary_remote_addr zone=login:10m    rate=5r/m;

server {
    listen 80;
    server_name _;
    return 301 https://\$host\$request_uri;
}

server {
    listen 443 ssl;
    server_name _;

    ssl_certificate     /etc/ssl/pokemon-tracker/selfsigned.crt;
    ssl_certificate_key /etc/ssl/pokemon-tracker/selfsigned.key;
    ssl_protocols TLSv1.2 TLSv1.3;

    add_header X-Content-Type-Options "nosniff"   always;
    add_header X-Frame-Options        "DENY"       always;

    location /login {
        limit_req zone=login burst=3 nodelay;
        proxy_pass http://127.0.0.1:8888;
        proxy_set_header Host              \$host;
        proxy_set_header X-Real-IP         \$remote_addr;
        proxy_set_header X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location / {
        limit_req zone=general burst=20 nodelay;
        proxy_pass http://127.0.0.1:8888;
        proxy_set_header Host              \$host;
        proxy_set_header X-Real-IP         \$remote_addr;
        proxy_set_header X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 60s;
    }

    location /static/ {
        alias /home/pi/pokemon-tracker/static/;
        expires 7d;
    }

    location ~ /\.  { deny all; }
    location ~ /(\.env|data/)  { deny all; }
}
NGINXEOF
fi

sudo ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx
info "Nginx configured and restarted."

# ── Firewall (ufw) ────────────────────────────────────────────
if command -v ufw &>/dev/null; then
    info "Configuring firewall…"
    sudo ufw allow 22/tcp   comment "SSH"
    sudo ufw allow 80/tcp   comment "HTTP (redirect)"
    sudo ufw allow 443/tcp  comment "HTTPS"
    sudo ufw --force enable
    info "Firewall enabled: SSH + HTTP + HTTPS allowed."
fi

# ── Cron for cert renewal ─────────────────────────────────────
(crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet --post-hook 'systemctl reload nginx'") | sort -u | crontab -

# ── Summary ───────────────────────────────────────────────────
echo ""
echo -e "${GREEN}════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Setup complete!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════${NC}"
echo ""
echo "  Next steps:"
echo "  1. Edit your config:    nano $REPO_DIR/.env"
echo "  2. Start the service:   sudo systemctl start $SERVICE_NAME"
echo "  3. View logs:           sudo journalctl -u $SERVICE_NAME -f"
echo ""
echo "  Access the tracker:"
echo "    Local network:  https://$(hostname -I | awk '{print $1}')"
echo "    Public IP:      https://$PUBLIC_IP  (after router port-forward 443)"
echo ""
echo "  To get a free HTTPS cert once you have a domain:"
echo "    sudo certbot --nginx -d YOUR_DOMAIN"
echo ""
echo "  Router port forwarding:"
echo "    External 443 → Pi internal IP $(hostname -I | awk '{print $1}') port 443"
echo "    External 80  → Pi internal IP $(hostname -I | awk '{print $1}') port 80"
echo ""
