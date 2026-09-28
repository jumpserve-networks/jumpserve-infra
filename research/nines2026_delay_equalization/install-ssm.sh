#!/usr/bin/env bash
# Ubuntu's snap agent requires SquashFS/AppArmor; use AWS's Debian package instead.
set -euo pipefail
cd /opt/jumpserve-research/linux
scripts/config --module SQUASHFS --enable SQUASHFS_XZ --module BLK_DEV_LOOP
make olddefconfig
make -j16 modules
make modules_install
depmod -a
modprobe loop
modprobe squashfs
systemctl restart snapd
systemctl disable --now snap.amazon-ssm-agent.amazon-ssm-agent.service
snap remove --purge amazon-ssm-agent
curl --fail --location --max-time 60 \
  https://s3.us-east-1.amazonaws.com/amazon-ssm-us-east-1/latest/debian_amd64/amazon-ssm-agent.deb \
  --output /opt/jumpserve-research/amazon-ssm-agent.deb
dpkg -i /opt/jumpserve-research/amazon-ssm-agent.deb
systemctl enable --now amazon-ssm-agent
systemctl is-active amazon-ssm-agent
