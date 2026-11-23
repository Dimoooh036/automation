pipeline {
    agent {
        label 'php-agent'
    }

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
                echo 'Клонирование репозитория с PHP проектом...'
                git branch: 'lab05',
                    url: 'https://github.com/Dimoooh036/automation.git'
            }
        }

        stage('Install Dependencies') {
            steps {
                echo 'Установка зависимостей через Composer...'
                sh 'composer --version'
                sh 'cd $PROJECT_DIR && composer install --no-interaction --prefer-dist --no-progress'
            }
        }

        stage('Run Unit Tests') {
            steps {
                echo 'Запуск модульных тестов PHPUnit...'
                sh 'cd $PROJECT_DIR && mkdir -p build && ./vendor/bin/phpunit --testdox --log-junit build/phpunit.xml'
            }
        }

        stage('Publish Test Report') {
            steps {
                echo 'Публикация отчёта о результатах тестирования...'
                junit allowEmptyResults: false,
                      testResults: "$PROJECT_DIR/build/phpunit.xml"
            }
        }
    }

    post {
        always {
            echo 'Конвейер сборки и тестирования завершён.'
        }
        success {
            echo 'Все модульные тесты пройдены.'
        }
        failure {
            echo 'Сборка или тесты завершились с ошибкой.'
        }
    }
}
