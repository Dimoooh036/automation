pipeline {
    agent {
        label 'ansible-agent'
    }

    options {
        timestamps()
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
    }

    stages {
        stage('Checkout') {
            steps {
                echo 'Клонирование репозитория с PHP проектом...'
                git branch: 'lab05',
                    url: 'https://github.com/Dimoooh036/automation.git'
            }
        }

        stage('Deploy PHP Application') {
            steps {
                echo 'Копирование файлов проекта на тестовый сервер...'
                dir('lab05/ansible') {
                    sh 'ansible-playbook -i hosts.ini deploy_php_app.yml -e "project_dir=$WORKSPACE/lab05/php-app"'
                }
            }
        }

        stage('Verify Deployment') {
            steps {
                echo 'Проверка доступности приложения по HTTP...'
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

    post {
        always {
            echo 'Конвейер размещения PHP проекта завершён.'
        }
        success {
            echo 'PHP проект успешно размещён на тестовом сервере.'
        }
        failure {
            echo 'Размещение PHP проекта завершилось с ошибкой.'
        }
    }
}
