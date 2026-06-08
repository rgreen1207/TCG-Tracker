#!/usr/bin/env bash
# Push the portable setup.sh fix to GitHub
# Run from your TCG-Tracker repo directory:
#   bash push_setup_fix.sh
 
set -euo pipefail
 
GREEN='\033[0;32m'; NC='\033[0m'
info() { echo -e "${GREEN}[push]${NC} $*"; }
 
# ── Make sure we're in the repo ───────────────────────────────
[[ -f "main.py" ]] || { echo "Run this from inside your TCG-Tracker repo directory."; exit 1; }
 
info "Downloading updated deploy files from the fixed version…"
 
# Write the new portable setup.sh directly
cat > deploy/setup.sh << 'SETUPEOF'
#!/usr/bin/env bash
# =============================================================================
# TCG Tracker — Raspberry Pi Setup Script
# Portable: works for any username, any clone location, any Pi.
# Usage: bash deploy/setup.sh   (run from anywhere inside the repo)
# =============================================================================
set -euo pipefail
 
# ── Resolve repo root from script location (works regardless of username/path)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$REPO_DIR/venv"
SERVICE_NAME="tcg-tracker"
NGINX_CONF="/etc/nginx/sites-available/$SERVICE_NAME"
CURRENT_USER="$(whoami)"
LOCAL_IP="$(hostname -I | awk '{print $1}')"
 
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'
 
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }
 
# ── Preflight checks ──────────────────────────────────────────
[[ "$(id -u)" -eq 0 ]] && error "Do not run as root. Run as your normal user (e.g. ryan, pi, ubuntu)."
[[ -f "$REPO_DIR/main.py" ]]          || error "Cannot find main.py in $REPO_DIR — run this script from inside the cloned repo."
[[ -f "$REPO_DIR/requirements.txt" ]] || error "Cannot find requirements.txt in $REPO_DIR."
 
info "TCG Tracker setup starting…"
info "Repo root:    $REPO_DIR"
info "Running as:   $CURRENT_USER"
info "Local IP:     $LOCAL_IP"
 
# ── System packages ───────────────────────────────────────────
info "Installing system dependencies…"
sudo apt-get update -q
sudo apt-get install -y -q \
    python3 python3-pip python3-venv \
    nginx certbot python3-certbot-nginx \
    sqlite3 curl git
 
# ── Python virtual environment ────────────────────────────────
info "Creating Python virtual environment at $VENV_DIR…"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$REPO_DIR/requirements.txt" -q
info "Python dependencies installed."
 
# ── Runtime directories ───────────────────────────────────────
mkdir -p "$REPO_DIR/data" "$REPO_DIR/logs"
chmod 700 "$REPO_DIR/data"
info "Created data/ and logs/ directories."
 
# ── .env file ────────────────────────────────────────────────
if [[ ! -f "$REPO_DIR/.env" ]]; then
    cp "$REPO_DIR/.env.example" "$REPO_DIR/.env"
    SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s/change_me_to_a_random_32_byte_hex_string/$SECRET/" "$REPO_DIR/.env"
    warn ".env created from template — EDIT IT before starting the service:"
    warn "  nano $REPO_DIR/.env"
    warn "  → Set ADMIN_PASSWORD, eBay keys, Pushover keys, etc."
else
    info ".env already exists — skipping (delete it to regenerate)."
fi
 
# ── Systemd service (dynamically written — no hardcoded paths) ──
info "Writing systemd service file…"
sudo bash -c "cat > /etc/systemd/system/$SERVICE_NAME.service" << SVCEOF
[Unit]
Description=TCG Price Tracker
After=network.target
 
[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$REPO_DIR
Environment=PATH=$VENV_DIR/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin
ExecStart=$VENV_DIR/bin/uvicorn main:app --host 127.0.0.1 --port 8888 --workers 1
Restart=on-failure
RestartSec=5s
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=$REPO_DIR/data $REPO_DIR/logs
StandardOutput=journal
StandardError=journal
SyslogIdentifier=$SERVICE_NAME
 
[Install]
WantedBy=multi-user.target
SVCEOF
 
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
info "Systemd service installed and enabled."
 
# ── Nginx config (dynamically written — no hardcoded paths) ──
info "Configuring Nginx…"
PUBLIC_IP=$(curl -sf --max-time 5 https://api.ipify.org || echo "YOUR_PUBLIC_IP")
 
SSL_DIR="/etc/ssl/$SERVICE_NAME"
SSL_CERT="$SSL_DIR/selfsigned.crt"
SSL_KEY="$SSL_DIR/selfsigned.key"
 
if [[ ! -f /etc/letsencrypt/live/*/fullchain.pem ]] 2>/dev/null; then
    warn "No Let's Encrypt cert found — generating self-signed cert."
    warn "After pointing a domain at this Pi, upgrade with:"
    warn "  sudo certbot --nginx -d YOUR_DOMAIN"
    sudo mkdir -p "$SSL_DIR"
    sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout "$SSL_KEY" \
        -out    "$SSL_CERT" \
        -subj   "/CN=$LOCAL_IP" 2>/dev/null
    CERT_PATH="$SSL_CERT"
    KEY_PATH="$SSL_KEY"
else
    CERT_PATH="$(ls /etc/letsencrypt/live/*/fullchain.pem | head -1)"
    KEY_PATH="$(ls /etc/letsencrypt/live/*/privkey.pem | head -1)"
    info "Let's Encrypt cert found: $CERT_PATH"
fi
 
sudo bash -c "cat > $NGINX_CONF" << NGINXEOF
# TCG Tracker — generated by setup.sh
# Repo: $REPO_DIR  |  User: $CURRENT_USER
limit_req_zone \$binary_remote_addr zone=general:10m rate=60r/m;
limit_req_zone \$binary_remote_addr zone=login:10m   rate=5r/m;
 
server {
    listen 80;
    server_name _;
    return 301 https://\$host\$request_uri;
}
 
server {
    listen 443 ssl;
    server_name _;
 
    ssl_certificate     $CERT_PATH;
    ssl_certificate_key $KEY_PATH;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
 
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options    "nosniff"                             always;
    add_header X-Frame-Options           "DENY"                                always;
    add_header X-XSS-Protection          "1; mode=block"                       always;
    add_header Referrer-Policy           "strict-origin-when-cross-origin"     always;
 
    location /login {
        limit_req zone=login burst=3 nodelay;
        proxy_pass         http://127.0.0.1:8888;
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
    }
 
    location / {
        limit_req zone=general burst=20 nodelay;
        proxy_pass         http://127.0.0.1:8888;
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_read_timeout 60s;
    }
 
    location /static/ {
        alias $REPO_DIR/static/;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }
 
    location ~ /\.    { deny all; }
    location ~ /\.env { deny all; }
    location ~ /data/ { deny all; }
    location ~ /logs/ { deny all; }
}
NGINXEOF
 
sudo ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx
info "Nginx configured and restarted."
 
# ── Firewall ──────────────────────────────────────────────────
if command -v ufw &>/dev/null; then
    info "Configuring firewall…"
    sudo ufw allow 22/tcp  comment "SSH"
    sudo ufw allow 80/tcp  comment "HTTP → HTTPS redirect"
    sudo ufw allow 443/tcp comment "HTTPS"
    sudo ufw --force enable
    info "Firewall: SSH + HTTP + HTTPS allowed."
fi
 
# ── Certbot auto-renewal cron ─────────────────────────────────
(crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet --post-hook 'systemctl reload nginx'") \
    | sort -u | crontab -
 
# ── Final summary ─────────────────────────────────────────────
echo ""
echo -e "${GREEN}════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Setup complete!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════${NC}"
echo ""
echo "  Repo:         $REPO_DIR"
echo "  Running as:   $CURRENT_USER"
echo "  Service name: $SERVICE_NAME"
echo ""
echo "  Next steps:"
echo "  1. Edit credentials:  nano $REPO_DIR/.env"
echo "  2. Start service:     sudo systemctl start $SERVICE_NAME"
echo "  3. View live logs:    sudo journalctl -u $SERVICE_NAME -f"
echo "  4. Check status:      sudo systemctl status $SERVICE_NAME"
echo ""
echo "  Access from your network:  https://$LOCAL_IP"
echo "  Access from the internet:  https://$PUBLIC_IP  (after port-forwarding 443)"
echo ""
echo "  To upgrade to a real HTTPS cert once you have a domain:"
echo "    sudo certbot --nginx -d YOUR_DOMAIN"
echo ""
echo "  To deploy on any other Pi in future — just:"
echo "    git clone https://github.com/rgreen1207/TCG-Tracker"
echo "    cd TCG-Tracker && bash deploy/setup.sh"
echo ""
SETUPEOF
 
chmod +x deploy/setup.sh
info "deploy/setup.sh updated."
 
# Write the template-only service file
cat > deploy/pokemon-tracker.service << 'SVCEOF'
# NOTE: This file is a documentation template only.
# The actual /etc/systemd/system/tcg-tracker.service is written
# dynamically by deploy/setup.sh with correct user, paths, and venv
# for whatever machine you're running on.
#
# To install on any Pi:
#   git clone https://github.com/rgreen1207/TCG-Tracker
#   cd TCG-Tracker && bash deploy/setup.sh
 
[Unit]
Description=TCG Price Tracker
After=network.target
 
[Service]
Type=simple
User=<auto-detected by setup.sh>
WorkingDirectory=<auto-detected by setup.sh>
Environment=PATH=<auto-detected by setup.sh>
ExecStart=<venv>/bin/uvicorn main:app --host 127.0.0.1 --port 8888 --workers 1
Restart=on-failure
RestartSec=5s
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
StandardOutput=journal
StandardError=journal
SyslogIdentifier=tcg-tracker
 
[Install]
WantedBy=multi-user.target
SVCEOF
 
info "deploy/pokemon-tracker.service updated."
 
# ── Commit and push ───────────────────────────────────────────
git add deploy/setup.sh deploy/pokemon-tracker.service
 
git commit -m "fix: make setup.sh fully portable (any user, any path, any Pi)
 
- Derive REPO_DIR from script location via BASH_SOURCE — no hardcoded paths
- Derive CURRENT_USER via whoami — no hardcoded 'pi' or 'ryan'
- Systemd service file written dynamically at install time
- Nginx config written dynamically — static alias uses live REPO_DIR
- Service renamed to tcg-tracker for clarity
- Preflight check verifies main.py exists rather than checking a fixed path
- Works: git clone <repo> && bash deploy/setup.sh on any machine"
 
git push
info "Pushed to GitHub. On your Pi, run:"
echo ""
echo "  cd ~/TCG-Tracker"
echo "  git pull"
echo "  bash deploy/setup.sh"
echo ""
