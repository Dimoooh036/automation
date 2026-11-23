#!/bin/bash
# Entrypoint агента Ansible: ключ Jenkins + приватный ключ
# для подключения к тестовому серверу, затем запуск sshd.
set -e

mkdir -p /run/sshd /home/jenkins/.ssh /home/jenkins/agent

if [ -n "${JENKINS_AGENT_SSH_PUBKEY:-}" ]; then
    printf '%s\n' "$JENKINS_AGENT_SSH_PUBKEY" > /home/jenkins/.ssh/authorized_keys
fi

# Приватный ключ Ansible -> тестовый сервер монтируется в /run/secrets.
# Копируем его в домашнюю директорию jenkins и выставляем права 600,
# иначе ssh откажется использовать ключ.
if [ -f /run/secrets/ansible_server_key ]; then
    tr -d '\r' < /run/secrets/ansible_server_key > /home/jenkins/.ssh/ansible_server_key
    chmod 600 /home/jenkins/.ssh/ansible_server_key
fi

chown -R jenkins:jenkins /home/jenkins
chmod 700 /home/jenkins/.ssh
chmod 600 /home/jenkins/.ssh/authorized_keys 2>/dev/null || true

ssh-keygen -A

exec /usr/sbin/sshd -D -e
