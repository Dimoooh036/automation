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
                echo 'Клонирование репозитория с Ansible playbook...'
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
                echo 'Настройка тестового сервера (Apache2, PHP, виртуальный хост)...'
                dir('lab05/ansible') {
                    sh 'ansible-playbook -i hosts.ini setup_test_server.yml'
                }
            }
        }
    }

    post {
        always {
            echo 'Конвейер настройки тестового сервера завершён.'
        }
        success {
            echo 'Тестовый сервер успешно настроен.'
        }
        failure {
            echo 'Не удалось настроить тестовый сервер.'
        }
    }
}
