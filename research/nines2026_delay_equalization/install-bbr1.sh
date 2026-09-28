#!/usr/bin/env bash
# Google's pinned tree includes a BBRv1 comparison implementation named bbr1.
set -euo pipefail
cd /opt/jumpserve-research
test -f build-complete
test "$(uname -r)" = "$(cat kernel-release.txt)"
cd linux
scripts/config --enable TCP_CONG_BBR1 --enable X86_X2APIC
make olddefconfig
make -j16 bzImage modules
make modules_install
release=$(make -s kernelrelease)
install -m 644 arch/x86/boot/bzImage "/boot/vmlinuz-$release"
install -m 644 System.map "/boot/System.map-$release"
install -m 644 .config "/boot/config-$release"
update-initramfs -u -k "$release"
update-grub
depmod -a
printf '%s\n' '# BBRv1 is built into the pinned research kernel.' >/etc/modules-load.d/jumpserve-bbr1.conf
sha256sum net/ipv4/tcp_bbr.c net/ipv4/tcp_bbr1.c .config arch/x86/boot/bzImage > /opt/jumpserve-research/cca-sha256.txt
python3 - <<'UPLOAD'
import boto3
s3 = boto3.client('s3', region_name='us-east-1')
for local, key in [('/opt/jumpserve-research/cca-sha256.txt', 'cca-sha256.txt'),
                   ('.config', 'kernel-with-modules.config'),
                   ('net/ipv4/tcp_bbr1.c', 'tcp_bbr1.c'),
                   ('net/ipv4/tcp_bbr.c', 'tcp_bbr.c')]:
    s3.upload_file(local, 'jumpserve-nines2026-395567831870-us-east-1', 'build/'+key)
UPLOAD
sync
reboot
