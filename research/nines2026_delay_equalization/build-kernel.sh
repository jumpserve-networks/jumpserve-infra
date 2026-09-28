#!/usr/bin/env bash
# Isolated EC2 preparation, not an application deployment. No database credentials.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
readonly KERNEL_SHA=90210de4b779d40496dee0b89081780eeddf2a60
readonly RELEASE_SUFFIX=-jumpserve-nines2026
readonly RESEARCH_BUCKET=jumpserve-nines2026-395567831870-us-east-1
mkdir -p /opt/jumpserve-research
exec > >(tee -a /opt/jumpserve-research/build.log) 2>&1

# The instance is configured to terminate on shutdown. This persists over reboot.
cat >/etc/systemd/system/jumpserve-research-deadline.service <<'UNIT'
[Unit]
Description=Bound the lifetime of the NINeS research builder
[Service]
Type=oneshot
ExecStart=/sbin/shutdown -h now
UNIT
cat >/etc/systemd/system/jumpserve-research-deadline.timer <<'UNIT'
[Unit]
Description=Terminate the research builder after three hours per boot
[Timer]
OnBootSec=3h
Unit=jumpserve-research-deadline.service
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now jumpserve-research-deadline.timer
apt-get update
apt-get install -y build-essential flex bison libssl-dev libelf-dev bc git \
  libncurses-dev python3 python3-boto3 iproute2 iperf3 ethtool tcpdump jq \
  initramfs-tools linux-base cpio rsync kmod dwarves
# Use the standalone management agent so the experiment kernel need not support
# Ubuntu snap's filesystem and confinement dependencies.
systemctl disable --now snap.amazon-ssm-agent.amazon-ssm-agent.service
snap remove --purge amazon-ssm-agent
curl --fail --location --max-time 60 \
  https://s3.us-east-1.amazonaws.com/amazon-ssm-us-east-1/latest/debian_amd64/amazon-ssm-agent.deb \
  --output /opt/jumpserve-research/amazon-ssm-agent.deb
dpkg -i /opt/jumpserve-research/amazon-ssm-agent.deb
systemctl enable --now amazon-ssm-agent

cd /opt/jumpserve-research
git init linux
git -C linux remote add origin https://github.com/google/bbr.git
git -C linux fetch --depth=1 origin "$KERNEL_SHA"
git -C linux checkout --detach FETCH_HEAD
test "$(git -C linux rev-parse HEAD)" = "$KERNEL_SHA"
cd linux
make defconfig
scripts/config --set-str LOCALVERSION "$RELEASE_SUFFIX" --disable LOCALVERSION_AUTO
# Boot on Nitro/UEFI, support SSM networking and namespace experiments.
for option in BLK_DEV_NVME NVME_CORE EXT4_FS DEVTMPFS DEVTMPFS_MOUNT EFI \
  EFI_STUB EFI_PARTITION ENA_ETHERNET NET_NS NAMESPACES CGROUPS UNIX \
  INET_DIAG INET_TCP_DIAG INET_DIAG_DESTROY TCP_CONG_ADVANCED \
  NET_SCHED NET_CLS NET_CLS_ACT VETH IFB NET_SCH_NETEM NET_SCH_FQ \
  NET_SCH_TBF NET_SCH_HTB NET_SCH_INGRESS NET_CLS_U32 NET_ACT_MIRRED \
  TCP_CONG_CUBIC TCP_CONG_BBR TCP_CONG_HYBLA TCP_CONG_ILLINOIS TCP_CONG_WESTWOOD \
  IP_MULTIPLE_TABLES IP_ADVANCED_ROUTER NETFILTER CONFIGFS_FS OVERLAY_FS; do
  scripts/config --enable "$option"
done
scripts/config --disable DEBUG_INFO --disable DEBUG_INFO_BTF \
  --set-str SYSTEM_TRUSTED_KEYS '' --set-str SYSTEM_REVOCATION_KEYS ''
scripts/config --enable TCP_CONG_BBR1 --enable X86_X2APIC --module SQUASHFS --enable SQUASHFS_XZ --module BLK_DEV_LOOP
make olddefconfig
make -j16 bzImage modules
make modules_install
release=$(make -s kernelrelease)
install -m 644 arch/x86/boot/bzImage "/boot/vmlinuz-$release"
install -m 644 System.map "/boot/System.map-$release"
install -m 644 .config "/boot/config-$release"
update-initramfs -c -k "$release"
cat >/etc/default/grub.d/99-jumpserve-research.cfg <<EOF
GRUB_DEFAULT="Advanced options for Ubuntu>Ubuntu, with Linux $release"
GRUB_TIMEOUT=3
EOF
update-grub
printf '%s\n' "$KERNEL_SHA" > /opt/jumpserve-research/kernel-commit.txt
printf '%s\n' "$release" > /opt/jumpserve-research/kernel-release.txt
sha256sum .config arch/x86/boot/bzImage > /opt/jumpserve-research/kernel-sha256.txt
python3 - <<'PY'
import boto3
from pathlib import Path
s3=boto3.client('s3',region_name='us-east-1')
for name in ('kernel-commit.txt','kernel-release.txt','kernel-sha256.txt','build.log'):
    s3.upload_file('/opt/jumpserve-research/'+name,
        'jumpserve-nines2026-395567831870-us-east-1','build/'+name)
s3.upload_file('/opt/jumpserve-research/linux/.config',
    'jumpserve-nines2026-395567831870-us-east-1','build/kernel.config')
PY
touch /opt/jumpserve-research/build-complete
sync
reboot
