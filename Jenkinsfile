pipeline {
    agent any
    
    options {
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '10'))
        timeout(time: 240, unit: 'MINUTES')
        retry(2) // Глобальный retry лучше убрать или перенести на конкретные шаги
        timestamps()
    }
    
    triggers {
        cron('0 0,6,12,18 * * *') // Запуск 4 раза в день
    }
    
    environment {
        GITHUB_TOKEN = credentials('github-token')
        REPO_URL = 'https://github.com/soverxpro/IPTV-Checker-Fix.git'
        PLAYLIST_URL = 'https://raw.githubusercontent.com/soverxpro/IPTV-Checker-Fix/refs/heads/master/test.m3u'
        OUTPUT_FILE = 'iptv.m3u'
        // EMAIL_TO удален, так как уведомления больше не нужны
    }
    
    stages {
        stage('Initialize') {
            steps {
                sh '''
                    apt-get update -qq
                    apt-get install -y -qq python3 python3-venv python3-pip ffmpeg git
                    python3 -m venv /tmp/venv
                    /tmp/venv/bin/pip install --upgrade pip
                '''
            }
        }
        
        stage('Clone and Setup') {
            steps {
                script {
                    try {
                        checkout([$class: 'GitSCM',
                            branches: [[name: '*/master']],
                            userRemoteConfigs: [[url: "${REPO_URL}", credentialsId: 'github-token']] // Добавлен credentialsId для надежности
                        ])
                        
                        sh '''
                            /tmp/venv/bin/pip install -r requirements.txt
                        '''
                    } catch (Exception e) {
                        error "Setup failed: ${e.message}"
                    }
                }
            }
        }
        
        stage('Check IPTV Playlist') {
            steps {
                script {
                    def startTime = new Date()
                    sh '''
                        /tmp/venv/bin/python iptv-checker.py -p "${PLAYLIST_URL}" \
                            -s "${OUTPUT_FILE}" \
                            -t 4 \
                            -ft 10
                    '''
                    env.CHECK_DURATION = "${(new Date().time - startTime.time)/1000}s"
                }
            }
        }
        
        stage('Validate Playlist') {
            when { expression { fileExists("${OUTPUT_FILE}") } }
            steps {
                sh '''
                    ffmpeg -i "${OUTPUT_FILE}" -t 5 -f null - || true
                '''
            }
        }
        
        stage('Deploy to GitHub') {
            when { expression { fileExists("${OUTPUT_FILE}") } }
            steps {
                sh '''
                    git config --global user.email "soverx.online@gmail.com"
                    git config --global user.name "SoverX Online"
                    git config --global credential.helper 'store --file=.git-credentials'
                    echo "https://soverxpro:${GITHUB_TOKEN}@github.com" > .git-credentials
                    git add "${OUTPUT_FILE}"
                    git commit -m "IPTV update: $(date '+%Y-%m-%d %H:%M:%S')" // Убрано "Daily", так как обновление 4 раза в день
                    git push "${REPO_URL}" HEAD:master
                '''
            }
        }
    }
    
    post {
        always {
            sh 'rm -f .git-credentials || true' // Добавлено || true для устойчивости
            archiveArtifacts artifacts: "${OUTPUT_FILE}", allowEmptyArchive: true
            cleanWs()
        }
    }
}
