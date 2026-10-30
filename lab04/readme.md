# Лабораторная работа №4 (IW04) — Настройка Jenkins для автоматизации задач DevOps

Конвейер CI на Jenkins: контроллер и SSH-агент запускаются через Docker Compose,
агент подключается к контроллеру по SSH, а конвейер Jenkins клонирует PHP-проект
из GitHub и запускает его модульные тесты.

## Описание проекта

Состав работы:

- **Jenkins Controller** (`jenkins/jenkins:lts`) — веб-интерфейс и координация сборок,
  порты 8080 (UI) и 50000 (агенты), состояние хранится в томе `jenkins_home`.
- **SSH-агент** — образ на базе `jenkins/ssh-agent` с доустановленным `php-cli`;
  Jenkins подключается к нему по SSH (ключ из папки `secrets`) и запускает задачи
  в `/home/jenkins/agent`.
- **PHP-проект `php-app`** — небольшой проект с двумя модулями и модульными тестами:
  - `src/Calculator.php` — арифметические операции (включая обработку деления на ноль);
  - `src/StrUtils.php` — работа со строками (палиндромы, подсчёт слов, Unicode);
  - `tests/run_tests.php` — самодостаточный тестовый рантайм (без Composer/PHPUnit,
    т.к. на агенте установлен только `php-cli`). При провале тестов скрипт
    возвращает ненулевой код возврата, и Jenkins помечает сборку как неуспешную.
- **`Jenkinsfile`** — декларативный конвейер, который выполняется на узле
  с меткой `php-agent`.

Структура `lab04`:

```
lab04/
├── docker-compose.yml      # сервисы jenkins-controller и ssh-agent, тома и сеть
├── Dockerfile              # образ SSH-агента (jenkins/ssh-agent + php-cli)
├── .env                    # JENKINS_AGENT_SSH_PUBKEY (публичный ключ агента)
├── secrets/
│   ├── jenkins_agent_ssh_key     # приватный ключ (в .gitignore, не публикуется)
│   └── jenkins_agent_ssh_key.pub # публичный ключ (ставится в authorized_keys агента)
├── php-app/
│   ├── src/Calculator.php        # тестируемый модуль 1
│   ├── src/StrUtils.php          # тестируемый модуль 2
│   └── tests/run_tests.php       # модульные тесты (10 проверок)
├── Jenkinsfile             # декларативный конвейер CI
└── readme.md               # этот отчёт
```

## Шаги по настройке Jenkins Controller

1. В `docker-compose.yml` описан сервис контроллера:

   ```yaml
   services:
     jenkins-controller:
       image: jenkins/jenkins:lts
       container_name: jenkins-controller
       ports:
         - "8080:8080"
         - "50000:50000"
       volumes:
         - jenkins_home:/var/jenkins_home
       networks:
         - jenkins-network
   ```

2. Стек запущен:

   ```bash
   cd lab04
   docker compose up -d --build
   ```

3. Первичный пароль администратора взят из лога контроллера:

   ```bash
   docker exec jenkins-controller cat /var/jenkins_home/secrets/initialAdminPassword
   ```

4. Открыт `http://localhost:8080`, введён пароль из шага 3 (экран **Unlock Jenkins**).
5. На экране **Customize Jenkins** выбрано *Install suggested plugins* — установлено
   92 плагина (Git, Pipeline/Workflow, Credentials, SSH Build Agents и др.).
6. Создан учётная запись администратора: логин `admin` (экран **Create First Admin User**),
   затем задан URL инстанса (*Save and Finish*) и выполнен **Restart**.
   Важно: кнопка *Restart* завершает JVM внутри контейнера, поэтому после неё
   контейнер нужно поднять снова: `docker start jenkins-controller`.
7. Дополнительно установлен плагин **SSH Agents Plugin** (требование задания) через
   *Manage Jenkins → Manage Plugins → Available* (в API — `POST /pluginManager/installNecessaryPlugins`),
   версия `ssh-agent 433.v9e73d67c3f74`, статус *Active*.

## Шаги по настройке SSH агента

1. Сгенерированы SSH-ключи в папке `secrets` (в корне проекта `lab04`):

   ```bash
   mkdir secrets && cd secrets
   ssh-keygen -f jenkins_agent_ssh_key          # парольная фраза не задавалась
   ```

2. Создан `Dockerfile` агента — официальный образ + PHP-CLI:

   ```dockerfile
   FROM jenkins/ssh-agent
   # install PHP-CLI
   RUN apt-get update && apt-get install -y php-cli
   ```

3. Публичный ключ помещён в `.env` (переменная `JENKINS_AGENT_SSH_PUBKEY`) —
   образ `jenkins/ssh-agent` сам добавляет его в `~jenkins/.ssh/authorized_keys`
   при старте контейнера. Приватный ключ добавлен в `.gitignore` и в репозиторий
   не попадает.
4. В `docker-compose.yml` описан сервис агента (сеть общая с контроллером,
   том `jenkins_agent_volume` для рабочей директории):

   ```yaml
     ssh-agent:
       build:
         context: .
         dockerfile: Dockerfile
       container_name: ssh-agent
       environment:
         - JENKINS_AGENT_SSH_PUBKEY=${JENKINS_AGENT_SSH_PUBKEY}
       volumes:
         - jenkins_agent_volume:/home/jenkins/agent
       depends_on:
         - jenkins-controller
       networks:
         - jenkins-network
   ```

5. Проект перезапущен: `docker compose up -d --build`; проверено, что в контейнере
   работают `sshd` (порт 22) и `php` (PHP 8.4.27).
6. Плагин **SSH Agents Plugin** установлен (см. шаг 7 выше).
7. Зарегистрирован SSH-ключ в Jenkins: *Manage Jenkins → Manage Credentials →
   System → Global credentials → Add Credentials*:
   - Kind: **SSH Username with private key**,
   - ID: `jenkins-agent-ssh-key`,
   - Username: `jenkins`,
   - Private Key: вставлен приватный ключ из `secrets/jenkins_agent_ssh_key`.
8. Создан узел: *Manage Jenkins → Manage Nodes and Clouds → New Node*:
   - Имя: `ssh-agent1`, тип **Permanent Agent**;
   - Remote root directory: `/home/jenkins/agent`;
   - Launch method: **Launch agents via SSH**, Host: `ssh-agent`, Credentials:
     `jenkins-agent-ssh-key`;
   - Host Key Verification Strategy: **Non verifying** (контейнер агента генерирует
     новый host key при каждой пересборке, поэтому проверка отключена);
   - Метка узла: `php-agent`.

   После настройки узел `ssh-agent1` в статусе **online** (проверено:
   `GET /computer/api/json` → `"offline":false`, метки `php-agent`, `ssh-agent1`).

## Шаги по созданию и настройке конвейера Jenkins

1. В репозиторий положен PHP-проект `lab04/php-app` с модульными тестами
   (10 проверок, запуск: `php lab04/php-app/tests/run_tests.php`).
2. Создан файл `lab04/Jenkinsfile` (декларативный конвейер из задания, заполненный
   командами проекта):

   ```groovy
   pipeline {
       agent {
           label 'php-agent'
       }

       stages {
           stage('Install Dependencies') {
               steps {
                   echo 'Подготовка проекта...'
                   // php-app не использует Composer — достаточно php-cli
                   sh 'php -v'
               }
           }

           stage('Test') {
               steps {
                   echo 'Запуск тестов...'
                   sh 'php lab04/php-app/tests/run_tests.php'
               }
           }
       }

       post {
           always  { echo 'Конвейер завершен.' }
           success { echo 'Все этапы прошли успешно!' }
           failure { echo 'Обнаружены ошибки в конвейере.' }
       }
   }
   ```

3. Ветка `lab04` запушена в GitHub: https://github.com/Dimoooh036/automation/tree/lab04/lab04
4. Создан конвейер: *New Item → Pipeline*, имя `php-ci`, Source Code Management:
   **Git**, репозиторий `https://github.com/Dimoooh036/automation.git`, ветка `*/lab04`,
   Script Path: `lab04/Jenkinsfile`.
5. Запущена сборка (*Build Now*). Результат — **Finished: SUCCESS**; из лога видно,
   что задача выполнялась на агенте: `Running on ssh-agent1 in /home/jenkins/agent/workspace/php-ci`.
   Этапы:
   - *Checkout SCM* — клон репозитория (git 2.47.3 на агенте);
   - *Install Dependencies* — `php -v` → PHP 8.4.27;
   - *Test* — `php lab04/php-app/tests/run_tests.php` → **10 passed, 0 failed**;
   - *Post Actions* — «Конвейер завершен.», «Все этапы прошли успешно!».

   Фрагмент лога сборки:

   ```
   Running on ssh-agent1 in /home/jenkins/agent/workspace/php-ci
   ...
   + php lab04/php-app/tests/run_tests.php
   [PASS] Calculator::add(2, 2) == 4
   [PASS] Calculator::divide(1, 0) throws DivisionByZeroError
   [PASS] StrUtils::isPalindrome(palindrome) == true
   ...
   10 passed, 0 failed
   Finished: SUCCESS
   ```

## Как повторить запуск

```bash
cd lab04
docker compose up -d --build        # контроллер + агент
# далее в веб-интерфейсе http://localhost:8080:
#   Manage Credentials -> добавить SSH-ключ (ID: jenkins-agent-ssh-key)
#   Manage Nodes -> New Node ssh-agent1 (метка php-agent, Launch via SSH, host: ssh-agent)
#   New Item -> Pipeline php-ci (Git, */lab04, Script Path: lab04/Jenkinsfile)
#   Build Now
```

Проверка локально (без Jenkins): `php lab04/php-app/tests/run_tests.php`.

## Ответы на вопросы

### Какие преимущества использования Jenkins для автоматизации задач DevOps?

1. **Единая точка CI/CD** — сборка, тестирование, анализ и развёртывание описываются
   кодом (Jenkinsfile в репозитории), что делает процесс воспроизводимым и версионируемым.
2. **Огромная экосистема плагинов** (~1800 штук) — интеграция с Git, Docker, GitHub,
   SSH, PHPUnit, SonarQube, Kubernetes и почти любым другим инструментом без написания своего кода.
3. **Распределённое выполнение** — задачи можно раздавать множеству агентов
   (SSH, Docker, облачные инстансы), что масштабирует мощность сборок и позволяет
   тестировать на разных ОС/окружениях (в этой работе: контроллер и PHP-агент — разные контейнеры).
4. **Pipeline as Code и визуализация** — конвейер описан кодом, а в UI наглядно видны
   этапы, логи, история сборок и причина падения; есть `post`-блок для уведомлений.
5. **Гибкое расписание и триггеры** — сборка по push-запросу из GitHub, по таймеру, вручную
   или по API; вебхуки позволяют запускать CI на каждый push/PR.
6. **Бесплатный и open source**, самоподдерживающийся (агенты можно добавлять за минуты),
   что важно для учебных и небольших команд.

### Какие еще бывают агенты Jenkins?

- **Permanent Agent (Static agent)** — постоянный узел, подключается по SSH/JNLP,
  как `ssh-agent1` в этой работе;
- **Build Agent in Docker (Docker Agent / Docker Swarm)** — агенты запускаются как
  контейнеры на-demand для каждой сборки (плагины Docker, Docker Swarm);
- **Kubernetes Pod** — Jenkins поднимает под-агент в кластере K8s на время задачи
  и удаляет его после (плагин Kubernetes) — популярный вариант для масштабирования;
- **Cloud Agents (Amazon EC2, Azure VM, Google Compute Engine, VMware vSphere)** —
  агенты создаются в облаке по demand и уничтожаются после сборок;
- **Inbound Agent (JNLP / WebSocket)** — агент сам инициирует соединение к
  контроллеру (`jnlp`/WebSocket-запуск), удобно за NAT/firewall;
- **SSH Build Agents** — любой доступный по SSH хост (в т.ч. Windows через WinRM/OpenSSH);
- **Билд-нода на самой машине контроллера (built-in node)** — используется по умолчанию,
  но не рекомендуется для продакшена.

### Какие проблемы вы столкнулись при настройке Jenkins и как вы их решили?

1. **Рестарт из UI останавливал контейнер.** Кнопка *Restart* в мастере настройки
   завершает JVM, а главный процесс контейнера — сама JVM, поэтому контейнер
   останавливался с кодом 5 и Jenkins не поднимался. Решение: после рестарта выполнить
   `docker start jenkins-controller`.
2. **Агент не подключался по SSH из-за host key.** Контейнер агента генерирует
   случайный host key при каждой пересборке, и проверка по known_hosts падала.
   Решение: в настройках узла выбрать *Non verifying Key Verification Strategy*
   (для лабораторной приемлемо; в продакшене лучше фиксировать ключ).
3. **Пустая метка узла.** Узел создался, но метка `php-agent` не применилась
   (в конфиге осталось `<label></label>`). Решение: задать метку повторно через
   скрипт консоли Jenkins (`node.setLabelString('php-agent'); node.save()`),
   после чего узел отображает метки `php-agent` и `ssh-agent1`.
4. **Ошибка 500 при добавлении SSH-ключа.** В XML-конфигурации креденшала
   class-атрибут `BasicSSHUserPrivateKey$DirectEntryPrivateKeySource` в PowerShell-строке
   в двойных кавычках интерпретировался как переменная и обрезался, из-за чего
   xstream не мог построить объект. Решение: собирать XML в одиночных кавычках.
5. **Ошибка 500 при создании конвейера.** Кириллическое описание в POST-теле
   кодировалось в ISO-8859-1 и ломало XML. Решение: писать `config.xml` в UTF-8
   файл и отправлять его через `InFile`.
6. **Тесты «палиндромов» падали на кириллице.** `strrev()` работает побайтово и
   ломает многобайтовый UTF-8, а `strtolower()` не понимает кириллицу. Решение:
   разбивать строку на символы через `preg_split('//u', ...)` и применять явную
   таблицу соответствия заглавных кириллических букв.

## Ссылка на репозиторий

https://github.com/Dimoooh036/automation/tree/lab04/lab04
