#!/bin/bash
# Entrypoint SSH-агента Jenkins: добавляет публичный ключ контроллера
# и запускает sshd на переднем плане.
set -e

mkdir -p /run/sshd /home/jenkins/.ssh /home/jenkins/agent

if [ -n "${JENKINS_AGENT_SSH_PUBKEY:-}" ]; then
    printf '%s\n' "$JENKINS_AGENT_SSH_PUBKEY" > /home/jenkins/.ssh/authorized_keys
fi

chown -R jenkins:jenkins /home/jenkins
chmod 700 /home/jenkins/.ssh
chmod 600 /home/jenkins/.ssh/authorized_keys 2>/dev/null || true

# Генерируем host keys при первом запуске
ssh-keygen -A

exec /usr/sbin/sshd -D -e
