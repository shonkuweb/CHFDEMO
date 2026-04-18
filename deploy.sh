#!/bin/bash
# ── CHF Botanical Luxury :: VPS Deployment Automation ──

# ⚠️ INSTRUCTIONS:
# 1. Provide your VPS IP address or Hostname
VPS_IP="root@your_vps_ip"

# 2. Specify the directory on the VPS where the app should live
REMOTE_DIR="/var/www/chf_app"

echo "Deploying CHF Botanical Luxury to $VPS_IP..."

# Execute rsync (Exclude local databases, virtual environments, .git, and .env files to preserve production secrets natively on the VPS)
rsync -avz --exclude 'venv' \
           --exclude 'env' \
           --exclude '__pycache__' \
           --exclude '.git' \
           --exclude '.env' \
           --exclude 'chf_archive.db' \
           -e "ssh -o StrictHostKeyChecking=no" \
           ./ $VPS_IP:$REMOTE_DIR

echo "✅ Sync complete!"
echo ""
echo "Next Steps:"
echo "1. SSH into your VPS: ssh $VPS_IP"
echo "2. Navigate to the App: cd $REMOTE_DIR"
echo "3. Spin up the container: docker-compose up --build -d"
echo "4. Copy the newly generated nginx_template.conf to /etc/nginx/sites-available/chf and restart Nginx!"
