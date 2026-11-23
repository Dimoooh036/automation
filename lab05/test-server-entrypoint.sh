#!/bin/bash
# Entrypoint тестового сервера: публичный ключ Ansible-агента
# и запуск sshd.
set -e

mkdir -p /run/sshd /home/ansible/.ssh

if [ -n "${ANSIBLE_SSH_PUBKEY:-}" ]; then
    printf '%s\n' "$ANSIBLE_SSH_PUBKEY" > /home/ansible/.ssh/authorized_keys
fi

chown -R ansible:ansible /home/ansible
chmod 700 /home/ansible/.ssh
chmod 600 /home/ansible/.ssh/authorized_keys 2>/dev/null || true

ssh-keygen -A

exec /usr/sbin/sshd -D -e
