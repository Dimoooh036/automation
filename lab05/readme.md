# Лабораторная работа №5 (IW05) — Ansible и Jenkins CI/CD

Настройка тестового сервера с помощью Ansible, сборка и тестирование PHP-проекта
на отдельном Jenkins-агенте, а затем автоматическое развёртывание проекта на
тестовом сервере через Jenkins Pipeline.

## Описание проекта

В работе собран стек из четырёх контейнеров Docker Compose:

| Сервис | Контейнер | Назначение |
|---|---|---|
| `jenkins-controller` | `lab05-jenkins-controller` | Jenkins Controller: веб-интерфейс, конвейеры, управление агентами |
| `ssh-agent` | `lab05-ssh-agent` | Jenkins-агент для сборки PHP-проекта и запуска PHPUnit |
| `ansible-agent` | `lab05-ansible-agent` | Jenkins-агент с Ansible, настраивает и разворачивает тестовый сервер |
| `test-server` | `lab05-test-server` | Ubuntu-сервер, который настраивается Ansible: Apache2 + PHP |

Схема взаимодействия:

```
                         SSH (ключ jenkins_agent_ssh_key)
  Jenkins Controller  ───────────────────────────────────►  ssh-agent
        │                                                    PHP, Composer, PHPUnit
        │
        │  SSH (ключ jenkins_ansible_agent_ssh_key)
        └──────────────────────────────────────────────────►  ansible-agent
                                                                 │
                                                                 │ SSH (ключ ansible_server_key)
                                                                 │ пользователь ansible
                                                                 ▼
                                                            test-server
                                                            Apache2 + PHP
                                                            http://localhost:8081
```

Все контейнеры находятся в одной Docker-сети `jenkins-network`, поэтому
обращаются друг к другу по именам сервисов: `ssh-agent`, `ansible-agent`,
`test-server`. Наружу опубликованы только порты Jenkins (`8080`, `50000`) и
тестового сервера (`8081`).

### Структура `lab05`

```
lab05/
├── compose.yaml                       # четыре сервиса, тома и сеть
├── .env                               # публичные SSH-ключи для контейнеров
├── Dockerfile.ssh_agent               # образ Jenkins-агента для PHP
├── Dockerfile.ansible_agent           # образ Jenkins-агента с Ansible
├── Dockerfile.test_server             # образ тестового сервера (Ubuntu + sshd)
├── ssh-agent-entrypoint.sh            # authorized_keys + запуск sshd
├── ansible-agent-entrypoint.sh        # authorized_keys + приватный ключ Ansible + sshd
├── test-server-entrypoint.sh          # authorized_keys пользователя ansible + sshd
├── secrets/
│   ├── jenkins_agent_ssh_key          # приватный ключ (в .gitignore)
│   ├── jenkins_agent_ssh_key.pub
│   ├── jenkins_ansible_agent_ssh_key  # приватный ключ (в .gitignore)
│   ├── jenkins_ansible_agent_ssh_key.pub
│   ├── ansible_server_key             # приватный ключ Ansible (в .gitignore)
│   └── ansible_server_key.pub
├── ansible/
│   ├── ansible.cfg                    # настройки Ansible
│   ├── hosts.ini                      # инвентарь: test-server, пользователь ansible
│   ├── setup_test_server.yml          # установка Apache2, PHP и vhost
│   ├── deploy_php_app.yml             # копирование PHP-проекта на сервер
│   └── templates/
│       └── php-app.conf.j2            # шаблон виртуального хоста Apache
├── php-app/
│   ├── composer.json                  # зависимости: PHPUnit ^11.5
│   ├── composer.lock
│   ├── phpunit.xml
│   ├── public/index.php               # стартовая страница приложения
│   ├── src/Calculator.php
│   ├── src/StrUtils.php
│   └── tests/                         # PHPUnit-тесты
├── pipelines/
│   ├── php_build_and_test_pipeline.groovy
│   ├── ansible_setup_pipeline.groovy
│   └── php_deploy_pipeline.groovy
└── readme.md                          # этот отчёт
```

## Запуск стека

```bash
cd lab05
docker compose up -d --build
```

Проверка контейнеров:

```bash
docker compose ps
```

Ожидаемый результат: четыре контейнера в состоянии `Up`, порты
`0.0.0.0:8080->8080/tcp`, `0.0.0.0:50000->50000/tcp` и
`0.0.0.0:8081->80/tcp`.

## Настройка Jenkins Controller

1. Контроллер запускается из официального образа `jenkins/jenkins:lts`
   (в работе использован Jenkins **2.580.2**). Состояние хранится в томе
   `jenkins_home`, поэтому настройки и история сборок переживают перезапуск
   контейнера.

2. Первичный пароль администратора:

   ```bash
   docker exec lab05-jenkins-controller \
     cat /var/jenkins_home/secrets/initialAdminPassword
   ```

3. Далее в браузере открывается `http://localhost:8080`:
   - вводится пароль из шага 2;
   - выбирается установка рекомендуемых плагинов (*Install suggested plugins*);
   - создаётся администратор и задаётся URL Jenkins.

4. Дополнительно нужен плагин **SSH Build Agents** (SSH Agents Plugin) —
   именно он позволяет подключать агенты по SSH. Он устанавливается через
   *Manage Jenkins → Plugins → Available plugins*.

5. Для конвейеров используется плагин **Pipeline** (входит в рекомендуемый
   набор), для публикации результатов PHPUnit — **JUnit**.

## Настройка SSH-агента для PHP

### Ключи

В каталоге `lab05/secrets` сгенерированы отдельные ключи для каждого
соединения:

```bash
cd lab05/secrets
ssh-keygen -t ed25519 -N '' -f jenkins_agent_ssh_key
ssh-keygen -t ed25519 -N '' -f jenkins_ansible_agent_ssh_key
ssh-keygen -t ed25519 -N '' -f ansible_server_key
```

Приватные ключи (`*_key`) добавлены в `.gitignore` и в репозиторий не
попадают. Публичные ключи записаны в `lab05/.env`:

```dotenv
JENKINS_AGENT_SSH_PUBKEY="ssh-ed25519 AAAA... lab05-jenkins-ssh-agent"
JENKINS_ANSIBLE_AGENT_SSH_PUBKEY="ssh-ed25519 AAAA... lab05-jenkins-ansible-agent"
ANSIBLE_SERVER_SSH_PUBKEY="ssh-ed25519 AAAA... lab05-ansible-to-test-server"
```

### Образ агента

`Dockerfile.ssh_agent` основан на `ubuntu:24.04` и содержит:

- `openssh-server` — Jenkins подключается к агенту по SSH;
- `default-jre-headless` — Java необходима для Jenkins Remoting (без неё
  агент падает с ошибкой `java: command not found`);
- `php-cli`, `php-mbstring`, `php-xml`, `php-curl`, `composer` — сборка
  PHP-проекта и запуск PHPUnit;
- `git` — клонирование репозитория из Jenkins Pipeline.

Пользователь `jenkins` создаётся в образе. Entrypoint
`ssh-agent-entrypoint.sh` записывает публичный ключ в
`/home/jenkins/.ssh/authorized_keys`, выставляет права и запускает `sshd`.

### Регистрация агента в Jenkins

1. *Manage Jenkins → Credentials → System → Global credentials → Add Credentials*:
   - Kind: **SSH Username with private key**;
   - ID: `jenkins-agent-ssh-key`;
   - Username: `jenkins`;
   - Private Key: содержимое `secrets/jenkins_agent_ssh_key`.

2. *Manage Jenkins → Nodes → New Node*:
   - имя: `ssh-agent1`, тип **Permanent Agent**;
   - Remote root directory: `/home/jenkins/agent`;
   - Labels: `php-agent`;
   - Launch method: **Launch agents via SSH**;
   - Host: `ssh-agent`, Port: `22`;
   - Credentials: `jenkins-agent-ssh-key`;
   - Host Key Verification Strategy: **Non verifying**.

3. Узел `ssh-agent1` переходит в состояние **online**. Проверка через API:

   ```bash
   curl --globoff -sS \
     "http://localhost:8080/computer/api/json?tree=computer%5BdisplayName,offline,labels%5Bname%5D%5D"
   ```

   Фрагмент ответа:

   ```json
   {"displayName":"ssh-agent1","offline":false,
    "labels":[{"name":"php-agent"},{"name":"ssh-agent1"}]}
   ```

## Настройка Ansible-агента

### Образ агента

`Dockerfile.ansible_agent` также основан на `ubuntu:24.04` и содержит:

- `openssh-server` — для подключения Jenkins;
- `default-jre-headless` — для Jenkins Remoting;
- `ansible`, `python3` — запуск playbook'ов;
- `openssh-client` — SSH-подключение к тестовому серверу;
- `git`, `curl` — клонирование репозитория и проверка HTTP.

Приватный ключ `ansible_server_key` монтируется в контейнер только для
чтения:

```yaml
volumes:
  - ./secrets/ansible_server_key:/run/secrets/ansible_server_key:ro
```

Entrypoint `ansible-agent-entrypoint.sh` копирует его в
`/home/jenkins/.ssh/ansible_server_key` и выставляет права `600`, иначе
OpenSSH отказывается использовать ключ. Публичный ключ Jenkins записывается
в `authorized_keys`, после чего запускается `sshd`.

### Регистрация агента в Jenkins

1. Credentials:
   - Kind: **SSH Username with private key**;
   - ID: `ansible-agent-ssh-key`;
   - Username: `jenkins`;
   - Private Key: `secrets/jenkins_ansible_agent_ssh_key`.

2. Узел:
   - имя: `ansible-agent1`, тип **Permanent Agent**;
   - Remote root directory: `/home/jenkins/agent`;
   - Labels: `ansible-agent`;
   - Launch method: **Launch agents via SSH**;
   - Host: `ansible-agent`, Port: `22`;
   - Credentials: `ansible-agent-ssh-key`;
   - Host Key Verification Strategy: **Non verifying**.

3. Проверка, что агент видит тестовый сервер:

   ```bash
   docker exec -u jenkins lab05-ansible-agent bash -lc \
     "ssh -o StrictHostKeyChecking=no \
          -i ~/.ssh/ansible_server_key \
          ansible@test-server 'id'"
   ```

   Ожидаемый вывод содержит `uid=1000(ansible) gid=1000(ansible)`.

## Тестовый сервер

`Dockerfile.test_server` основан на `ubuntu:24.04` и содержит
`openssh-server`, `python3` и `sudo`. В образе создаётся пользователь
`ansible` с настроенным `sudo` без пароля:

```dockerfile
RUN useradd -m -s /bin/bash ansible \
    && echo 'ansible:ansible' | chpasswd \
    && echo 'ansible ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/ansible \
    && chmod 0440 /etc/sudoers.d/ansible
```

Публичный ключ `ansible_server_key.pub` передаётся через переменную
`ANSIBLE_SERVER_SSH_PUBKEY` и записывается entrypoint'ом в
`/home/ansible/.ssh/authorized_keys`. Пароль для SSH не используется:
Ansible подключается только по ключу.

Apache2 и PHP в образ не устанавливаются — это делает Ansible playbook,
чтобы вся настройка сервера была описана кодом.

## Ansible: инвентарь и playbook'и

### `ansible/hosts.ini`

```ini
[test_servers]
test-server ansible_host=test-server \
            ansible_user=ansible \
            ansible_ssh_private_key_file=/home/jenkins/.ssh/ansible_server_key \
            ansible_python_interpreter=/usr/bin/python3

[test_servers:vars]
ansible_ssh_common_args=-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null
```

### `ansible/ansible.cfg`

```ini
[defaults]
inventory = hosts.ini
host_key_checking = False
interpreter_python = auto_silent
deprecation_warnings = False
retry_files_enabled = False
timeout = 30

[ssh_connection]
ssh_args = -o ControlMaster=auto -o ControlPersist=60s -o StrictHostKeyChecking=no
```

Проверка host key отключена, потому что контейнер тестового сервера
генерирует новый host key при каждой пересборке. Для лабораторного
окружения это допустимо; в продакшене ключ нужно фиксировать.

### `ansible/setup_test_server.yml`

Playbook выполняет идемпотентную настройку сервера:

1. обновляет кэш `apt`;
2. устанавливает `apache2`, `libapache2-mod-php`, `php`, `php-cli`,
   `php-mbstring`, `php-xml`, `php-curl`;
3. создаёт каталоги `/var/www/php-app` и `/var/www/php-app/public`;
4. разворачивает виртуальный хост из шаблона `templates/php-app.conf.j2`;
5. включает сайт `php-app` (`a2ensite`) и отключает `000-default`;
6. включает модуль `rewrite`;
7. запускает Apache2 и проверяет, что модуль `php_module` загружен.

Шаблон виртуального хоста:

```apache
<VirtualHost *:80>
    ServerName {{ php_app_server_name }}
    ServerAdmin admin@example.com
    DocumentRoot {{ php_app_public_dir }}

    <Directory {{ php_app_public_dir }}>
        Options Indexes FollowSymLinks
        AllowOverride All
        Require all granted
    </Directory>

    DirectoryIndex index.php index.html

    ErrorLog ${APACHE_LOG_DIR}/php-app-error.log
    CustomLog ${APACHE_LOG_DIR}/php-app-access.log combined
</VirtualHost>
```

Ручной запуск выполняется на Ansible-агенте (там находится приватный ключ
`/home/jenkins/.ssh/ansible_server_key`, на который ссылается `hosts.ini`):

```bash
docker exec -u jenkins lab05-ansible-agent bash -lc \
  "cd /home/jenkins/agent/workspace/lab05-ansible-setup/lab05/ansible && \
   ansible-playbook -i hosts.ini setup_test_server.yml"
```

Результат выполнения в работе:

```
PLAY RECAP *********************************************************************
test-server : ok=10 changed=2 unreachable=0 failed=0 skipped=0 rescued=0 ignored=0
```

Повторный запуск не меняет уже настроенный сервер (кроме обновления кэша
`apt`), то есть playbook идемпотентен.

### `ansible/deploy_php_app.yml`

Playbook развёртывания:

1. создаёт каталог `/var/www/php-app`;
2. копирует туда содержимое `php-app` (владелец `www-data`);
3. проверяет, что приложение отвечает по HTTP 200 (до 10 попыток);
4. перезапускает Apache2 через handler при изменении файлов.

Путь к проекту передаётся из Jenkins:

```bash
ansible-playbook -i hosts.ini deploy_php_app.yml \
  -e "project_dir=$WORKSPACE/lab05/php-app"
```

Результат:

```
PLAY RECAP *********************************************************************
test-server : ok=5 changed=2 unreachable=0 failed=0 skipped=0 rescued=0 ignored=0
```

## Конвейеры Jenkins

Все три конвейера хранятся в репозитории и запускаются как
**Pipeline script from SCM**:

- SCM: Git;
- URL: `https://github.com/Dimoooh036/automation.git`;
- Branch Specifier: `*/lab05`;
- Script Path: соответствующий файл в `lab05/pipelines/`.

### 1. Сборка и тестирование PHP

`pipelines/php_build_and_test_pipeline.groovy` выполняется на узле с меткой
`php-agent`:

```groovy
pipeline {
    agent { label 'php-agent' }

    options {
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }

    environment {
        PROJECT_DIR = 'lab05/php-app'
    }

    stages {
        stage('Checkout') {
            steps {
                git branch: 'lab05',
                    url: 'https://github.com/Dimoooh036/automation.git'
            }
        }
        stage('Install Dependencies') {
            steps {
                sh 'composer --version'
                sh 'cd $PROJECT_DIR && composer install --no-interaction --prefer-dist --no-progress'
            }
        }
        stage('Run Unit Tests') {
            steps {
                sh 'cd $PROJECT_DIR && mkdir -p build && ./vendor/bin/phpunit --testdox --log-junit build/phpunit.xml'
            }
        }
        stage('Publish Test Report') {
            steps {
                junit allowEmptyResults: false,
                      testResults: "$PROJECT_DIR/build/phpunit.xml"
            }
        }
    }
}
```

Результат сборки `lab05-php-build-test` — **SUCCESS**:

```
Running on ssh-agent1 in /home/jenkins/agent/workspace/lab05-php-build-test
+ composer --version
Composer version 2.7.1
+ ./vendor/bin/phpunit --testdox --log-junit build/phpunit.xml
PHPUnit 11.5.58 by Sebastian Bergmann and contributors.
.........                                                           9 / 9 (100%)
OK (9 tests, 10 assertions)
Recording test results
Finished: SUCCESS
```

### 2. Настройка тестового сервера через Ansible

`pipelines/ansible_setup_pipeline.groovy` выполняется на узле
`ansible-agent`:

```groovy
pipeline {
    agent { label 'ansible-agent' }

    options {
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
    }

    stages {
        stage('Checkout') {
            steps {
                git branch: 'lab05',
                    url: 'https://github.com/Dimoooh036/automation.git'
            }
        }
        stage('Check Ansible') {
            steps {
                sh 'ansible --version'
                sh 'ansible-playbook --version'
            }
        }
        stage('Run Ansible Playbook') {
            steps {
                dir('lab05/ansible') {
                    sh 'ansible-playbook -i hosts.ini setup_test_server.yml'
                }
            }
        }
    }
}
```

Результат сборки `lab05-ansible-setup` — **SUCCESS**:

```
Running on ansible-agent1 in /home/jenkins/agent/workspace/lab05-ansible-setup
+ ansible-playbook -i hosts.ini setup_test_server.yml
PLAY RECAP *********************************************************************
test-server : ok=10 changed=2 unreachable=0 failed=0 skipped=0 rescued=0 ignored=0
Finished: SUCCESS
```

### 3. Развёртывание PHP-проекта

`pipelines/php_deploy_pipeline.groovy` также выполняется на
`ansible-agent`:

```groovy
pipeline {
    agent { label 'ansible-agent' }

    options {
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
    }

    stages {
        stage('Checkout') {
            steps {
                git branch: 'lab05',
                    url: 'https://github.com/Dimoooh036/automation.git'
            }
        }
        stage('Deploy PHP Application') {
            steps {
                dir('lab05/ansible') {
                    sh 'ansible-playbook -i hosts.ini deploy_php_app.yml \
                        -e "project_dir=$WORKSPACE/lab05/php-app"'
                }
            }
        }
        stage('Verify Deployment') {
            steps {
                sh '''
                    set -e
                    for i in $(seq 1 10); do
                        code=$(curl -s -o /dev/null -w "%{http_code}" http://test-server/ || true)
                        if [ "$code" = "200" ]; then
                            echo "Application is available: HTTP $code"
                            exit 0
                        fi
                        sleep 2
                    done
                    echo "Application is not available (last HTTP code: $code)"
                    exit 1
                '''
            }
        }
    }
}
```

Результат сборки `lab05-php-deploy` — **SUCCESS**:

```
Running on ansible-agent1 in /home/jenkins/agent/workspace/lab05-php-deploy
+ ansible-playbook -i hosts.ini deploy_php_app.yml \
    -e project_dir=/home/jenkins/agent/workspace/lab05-php-deploy/lab05/php-app
PLAY RECAP *********************************************************************
test-server : ok=5 changed=2 unreachable=0 failed=0 skipped=0 rescued=0 ignored=0
+ curl -s -o /dev/null -w %{http_code} http://test-server/
+ code=200
Application is available: HTTP 200
Finished: SUCCESS
```

## Проверка результата

Приложение доступно по адресу `http://localhost:8081/`. Проверка:

```bash
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8081/
# 200
```

На странице отображается заголовок «PHP-приложение развёрнуто на тестовом
сервере» и результаты пяти проверок (`5 / 5 проверок пройдено`).

Дополнительно проверено внутри тестового сервера:

```bash
docker exec lab05-test-server bash -lc \
  "php -v | head -1; apache2ctl -M | grep php; ls -l /etc/apache2/sites-enabled/"
```

```
PHP 8.3.6 (cli)
php_module (shared)
php-app.conf -> ../sites-available/php-app.conf
```

## Как повторить запуск

```bash
cd lab05
docker compose up -d --build

# 1. Открыть http://localhost:8080 и выполнить первичную настройку Jenkins.
# 2. Добавить credentials:
#    - jenkins-agent-ssh-key   (username jenkins, ключ secrets/jenkins_agent_ssh_key)
#    - ansible-agent-ssh-key   (username jenkins, ключ secrets/jenkins_ansible_agent_ssh_key)
# 3. Создать узлы:
#    - ssh-agent1     (label php-agent,     host ssh-agent,     remote root /home/jenkins/agent)
#    - ansible-agent1 (label ansible-agent, host ansible-agent, remote root /home/jenkins/agent)
# 4. Создать три Pipeline-задания (Pipeline script from SCM, ветка */lab05):
#    - lab05-php-build-test  -> lab05/pipelines/php_build_and_test_pipeline.groovy
#    - lab05-ansible-setup   -> lab05/pipelines/ansible_setup_pipeline.groovy
#    - lab05-php-deploy      -> lab05/pipelines/php_deploy_pipeline.groovy
# 5. Запустить задания по порядку: build-test -> ansible-setup -> php-deploy.
```

Проверка без Jenkins (внутри Ansible-агента):

```bash
docker exec -u jenkins lab05-ansible-agent bash -lc '
  rm -rf /tmp/lab05 &&
  git clone --branch lab05 --depth 1 \
    https://github.com/Dimoooh036/automation.git /tmp/lab05 &&
  cd /tmp/lab05/lab05/ansible &&
  ansible-playbook -i hosts.ini setup_test_server.yml &&
  ansible-playbook -i hosts.ini deploy_php_app.yml
'
curl -sS -o /dev/null -w "%{http_code}\n" http://localhost:8081/
```

## Ответы на вопросы

### 1. Какие преимущества даёт Ansible при настройке сервера?

1. **Infrastructure as Code.** Настройка сервера описывается YAML-файлами,
   которые хранятся в Git рядом с приложением. Вместо ручных команд в
   терминале получается воспроизводимый и проверяемый процесс.
2. **Идемпотентность.** Повторный запуск playbook'а приводит сервер к тому же
   состоянию: уже установленные пакеты не переустанавливаются, существующие
   каталоги не пересоздаются. Это безопасно для повторных запусков и
   исправления «дрейфа» конфигурации.
3. **Агентless-архитектура.** На управляемый сервер не нужно устанавливать
   агент Ansible — достаточно SSH и Python. В работе это позволило обойтись
   обычным Ubuntu-контейнером с `openssh-server` и `python3`.
4. **Декларативность и читаемость.** В playbook'е перечислено *что* должно
   быть на сервере (пакеты, каталоги, виртуальный хост, запущенный Apache), а
   не *как* это делать по шагам. Модули `apt`, `file`, `template`, `service`
   сами выполняют нужные действия и сообщают об изменениях.
5. **Повторное использование.** Шаблоны Jinja2, переменные, handlers и роли
   позволяют описывать конфигурацию один раз и применять её к разным
   серверам и окружениям.
6. **Интеграция с CI/CD.** Ansible легко вызывается из Jenkins Pipeline одной
   командой `ansible-playbook`, а результат (код возврата и `PLAY RECAP`)
   автоматически становится статусом сборки.

### 2. Какие ещё есть инструменты управления конфигурациями и чем Ansible отличается от них?

- **Puppet** — декларативный, использует собственный язык Puppet DSL и
  агент на каждом узле; требует Puppet Server и периодического запуска агента.
- **Chef** — также агентская модель, конфигурация описывается на Ruby DSL
  (recipes/cookbooks); мощный, но более тяжёлый в освоении и поддержке.
- **SaltStack (Salt)** — быстрый агентский вариант с шиной сообщений; есть
  и agentless-режим через SSH, но типичная схема предполагает установку
  minion'ов.
- **CFEngine** — один из старейших инструментов, ориентирован на
  масштабные инфраструктуры и агентскую модель.
- **Terraform / OpenTofu** — управляют прежде всего *инфраструктурой*
  (виртуальные машины, сети, облачные ресурсы), а не конфигурацией внутри
  ОС; часто используются вместе с Ansible.
- **Pulumi** — Infrastructure as Code на языках программирования
  (TypeScript, Python, Go и др.).

Ключевые отличия Ansible:

| Критерий | Ansible | Puppet / Chef / Salt |
|---|---|---|
| Агент на узле | не нужен (SSH + Python) | как правило, нужен |
| Язык описания | YAML + Jinja2 | собственный DSL / Ruby |
| Порог входа | низкий | выше |
| Модель работы | push (запуск из Jenkins/CLI) | чаще pull (агент периодически забирает конфигурацию) |
| Основное применение | настройка серверов, деплой, оркестрация | управление большими парками серверов |

Ansible не заменяет Terraform: Terraform создаёт инфраструктуру, а Ansible
настраивает уже существующие машины. В этой работе Ansible использован
именно для настройки и развёртывания внутри готового контейнера.

### 3. С какими проблемами вы столкнулись и как их решили?

1. **Агент Jenkins не запускался: `java: command not found`.** Официальный
   `jenkins/ssh-agent` содержит Java, а собственные Ubuntu-образы — нет.
   Jenkins Remoting запускает на агенте `java -jar remoting.jar`, поэтому
   оба агентских Dockerfile были дополнены пакетом `default-jre-headless`.
   После пересборки образов и пересоздания контейнеров узлы `ssh-agent1` и
   `ansible-agent1` перешли в состояние **online**.

2. **Ошибка `Invalid option type "timestamps"` при первом запуске
   конвейера.** Опция `timestamps()` требует установленного плагина
   Timestamper, которого не было в Jenkins. Опция была удалена из всех трёх
   pipeline-файлов; для журнала сборки достаточно стандартных отметок
   времени Jenkins.

3. **Ansible не мог использовать приватный ключ.** Ключ, смонтированный из
   `secrets/`, имел права, недопустимые для OpenSSH. Entrypoint
   Ansible-агента копирует ключ в `/home/jenkins/.ssh/ansible_server_key` и
   выставляет `chmod 600`; дополнительно удаляются символы `\r`, чтобы
   ключ, созданный в Windows, корректно читался в Linux.

4. **Проверка host key при каждом пересоздании контейнера.** Контейнеры
   генерируют новый SSH host key при старте, поэтому стандартная проверка
   `known_hosts` ломала подключение. Для учебного окружения использована
   стратегия **Non verifying** в настройках Jenkins-узлов и
   `host_key_checking = False` в `ansible.cfg`. В продакшене правильнее
   фиксировать host key или использовать управляемый `known_hosts`.

5. **Кириллица в логах Jenkins выглядела как «кракозябры».** Это связано с
   кодировкой, в которой клиент читает `consoleText`, а не с ошибкой
   конвейера: в веб-интерфейсе Jenkins сообщения отображаются корректно.
   На результат сборки это не влияет.

6. **Тесты PHPUnit требуют зависимостей Composer.** В отличие от lab04, где
   был самодостаточный `tests/run_tests.php`, в lab05 добавлены
   `composer.json`, `composer.lock` и PHPUnit. На агенте выполняется
   `composer install`, после чего `vendor/bin/phpunit` формирует JUnit-отчёт
   для плагина JUnit. Это потребовало установить в образ агента
   `composer` и расширения `php-mbstring`, `php-xml`, `php-curl`.

## Ссылка на репозиторий

https://github.com/Dimoooh036/automation/tree/lab05/lab05
