#!/bin/bash

# Create swap file for low-memory EC2 instances
# Recommended for t2.micro (1GB RAM)

set -e

echo "=================================="
echo "Setting Up Swap File"
echo "=================================="
echo ""

# Check if swap already exists
if swapon --show | grep -q '/swapfile'; then
    echo "Swap file already exists"
    swapon --show
    exit 0
fi

# Create 1GB swap file
echo "[1/5] Creating 1GB swap file..."
sudo fallocate -l 1G /swapfile

# Set permissions
echo "[2/5] Setting permissions..."
sudo chmod 600 /swapfile

# Make swap
echo "[3/5] Making swap..."
sudo mkswap /swapfile

# Enable swap
echo "[4/5] Enabling swap..."
sudo swapon /swapfile

# Make permanent
echo "[5/5] Making swap permanent..."
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

echo ""
echo "Swap file created successfully!"
echo ""
swapon --show
free -h
