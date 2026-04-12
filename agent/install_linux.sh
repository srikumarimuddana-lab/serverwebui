#!/bin/bash
# agent/install_linux.sh
set -euo pipefail

INSTALL_DIR="/opt/server-agent"
CONFIG_DIR="/etc/server-agent"
CERT_DIR="/etc/server-agent/certs"
SERVICE_USER="serveragent"

echo "=== Server Agent Installer (Linux) ==="

# Check root
if [ "$EUID" -ne 0 ]; then
    echo "Error: Run as root"
    exit 1
fi

# Create service user
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
    echo "Created user: $SERVICE_USER"
fi

# Create directories
mkdir -p "$INSTALL_DIR" "$CONFIG_DIR" "$CERT_DIR"

# Install Python deps
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip
cp -r "$(dirname "$0")"/* "$INSTALL_DIR/"
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

# Config
if [ ! -f "$CONFIG_DIR/config.yaml" ]; then
    cp "$INSTALL_DIR/config.example.yaml" "$CONFIG_DIR/config.yaml"
    echo "Config created at $CONFIG_DIR/config.yaml — edit before starting"
fi

# Set permissions
chown -R "$SERVICE_USER":"$SERVICE_USER" "$INSTALL_DIR" "$CONFIG_DIR"
chmod 700 "$CERT_DIR"

# Create systemd service
cat > /etc/systemd/system/server-agent.service <<EOF
[Unit]
Description=Server Agent
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/uvicorn agent.app.main:app --host 0.0.0.0 --port 8420
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable server-agent

echo ""
echo "=== Installation complete ==="
echo "1. Edit config: $CONFIG_DIR/config.yaml"
echo "2. Place certificates in: $CERT_DIR"
echo "3. Start: systemctl start server-agent"
