#!/bin/bash
# Runs only on the disposable image builder; no database credentials are used.
set -euo pipefail
exec > >(tee -a /var/log/jumpserve-image-build.log /dev/console) 2>&1
BACKEND_COMMIT=__BACKEND_COMMIT__

build_failed() {
  local code=$?
  trap - EXIT
  if [ "$code" -ne 0 ]; then
    echo "JUMPSERVE_AMI_FAILED: provisioning exited with $code"
  fi
  exit "$code"
}
trap build_failed EXIT
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a

# Avoid unattended package activity while measuring network performance. Rebuild
# the image regularly to apply OS updates; job instances never install packages.
systemctl mask --now apt-daily.timer apt-daily-upgrade.timer
timeout 120 systemctl stop apt-daily.service apt-daily-upgrade.service
systemctl mask apt-daily.service apt-daily-upgrade.service
timeout 600 apt-get -o Acquire::Retries=3 update
timeout 900 apt-get -o DPkg::Lock::Timeout=300 --assume-yes --no-install-recommends install \
  iproute2 ethtool python3 git net-tools ca-certificates curl jq unzip

curl --fail --location --retry 3 --connect-timeout 20 --max-time 180 \
  https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb \
  -o /tmp/amazon-cloudwatch-agent.deb
dpkg -i /tmp/amazon-cloudwatch-agent.deb
systemctl disable --now amazon-cloudwatch-agent

git init /home/ubuntu/jumpserve-back-end
git -C /home/ubuntu/jumpserve-back-end remote add origin https://github.com/jumpserve-networks/jumpserve-back-end.git
timeout 180 git -C /home/ubuntu/jumpserve-back-end fetch --depth=1 origin "$BACKEND_COMMIT"
git -C /home/ubuntu/jumpserve-back-end checkout --detach FETCH_HEAD
test "$(git -C /home/ubuntu/jumpserve-back-end rev-parse HEAD)" = "$BACKEND_COMMIT"

# Check every runner before allowing an AMI to be registered.
for runner in netem_cubic_benchmark_hotnets.py netem_cubic_benchmark_nines.py netem_nines.py netem_multi_bottleneck.py; do
  python3 "/home/ubuntu/jumpserve-back-end/$runner" --help > /dev/null
done
for executable in ip tc ss ethtool python3 sysctl shutdown timeout; do
  command -v "$executable" > /dev/null
done
test -x /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl
ip netns add jumpserve-image-check
ip netns exec jumpserve-image-check ip link set lo up
ip netns exec jumpserve-image-check tc qdisc add dev lo root netem delay 1ms
ip netns delete jumpserve-image-check

python3 - "$BACKEND_COMMIT" <<'PY'
import datetime, json, pathlib, subprocess, sys
pathlib.Path('/etc/jumpserve-image.json').write_text(json.dumps({
    'schema_version': 1,
    'backend_commit': sys.argv[1],
    'built_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'kernel': subprocess.check_output(['uname', '-r'], text=True).strip(),
}) + '\n')
PY
dpkg-query -W > /etc/jumpserve-image-packages.txt
apt-get clean
rm -rf /var/lib/apt/lists/* /home/ubuntu/jumpserve-back-end/.git
chown -R ubuntu:ubuntu /home/ubuntu/jumpserve-back-end

# Cleaning from inside cloud-final would allow it to recreate cached state.
# The build driver queues this service through SSM after verifying cloud-init.
cat > /usr/local/sbin/jumpserve-seal-image <<'SEAL'
#!/bin/bash
set -euo pipefail
exec > /dev/console 2>&1
trap 'code=$?; echo "JUMPSERVE_AMI_FAILED: sealing exited with $code"' ERR
cloud-init status --wait
backend_commit=$(python3 -c 'import json; print(json.load(open("/etc/jumpserve-image.json"))["backend_commit"])')
systemctl stop snap.amazon-ssm-agent.amazon-ssm-agent.service || systemctl stop amazon-ssm-agent.service || true
cloud-init clean --logs --machine-id --seed
rm -f /etc/ssh/ssh_host_* /root/.bash_history /home/ubuntu/.bash_history
rm -rf /var/lib/amazon/ssm/* /tmp/* /var/tmp/*
rm -f /var/lib/systemd/random-seed
rm -f /etc/systemd/system/jumpserve-seal-image.service /usr/local/sbin/jumpserve-seal-image
find /var/log -type f -exec truncate -s 0 {} +
sync
echo "JUMPSERVE_AMI_READY:$backend_commit"
shutdown -h now
SEAL
chmod 700 /usr/local/sbin/jumpserve-seal-image
cat > /etc/systemd/system/jumpserve-seal-image.service <<'UNIT'
[Unit]
Description=Seal the JumpServe benchmark image after first boot completes
After=cloud-final.service
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/jumpserve-seal-image
UNIT
systemctl daemon-reload
