pipeline {
    agent any
    
    // Опции сборки
    options {
        disableConcurrentBuilds() // Запрещаем параллельные запуски
        buildDiscarder(logRotator(numToKeepStr: '10')) // Храним 10 последних сборок
        timeout(time: 240, unit: 'MINUTES') // Ограничение времени выполнения
        retry(2) // Повтор при неудаче
        timestamps() // Добавляем метки времени в лог
    }
    
    // Триггеры запуска
    triggers {
        cron('0 0 * * *') // Ежедневно в полночь
    }
    
    environment {
        GITHUB_TOKEN = credentials('github-token')
        REPO_URL = 'https://github.com/soverxpro/IPTV-Checker-Fix.git'
        PLAYLIST_URL = 'https://iptv.org.ua/iptv/avto.m3u8'
        OUTPUT_FILE = 'iptv.m3u'
        EMAIL_TO = 'soverx.online@gmail.com' // Укажите ваш email
    }
    
    stages {
        stage('Initialize') {
            steps {
                sh '''
                    apt-get update -qq
                    apt-get install -y -qq python3 python3-venv python3-pip ffmpeg git
                    python3 -m venv venv
                '''
            }
        }
        
        stage('Clone and Setup') {
            steps {
                script {
                    try {
                        checkout([$class: 'GitSCM',
                            branches: [[name: '*/master']],
                            userRemoteConfigs: [[url: "${REPO_URL}"]]
                        ])
                        
                        sh '''
                            python3 -m venv venv
                            . venv/bin/activate
                            pip install -r requirements.txt
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
                        . venv/bin/activate
                        python3 iptv-checker.py -p "${PLAYLIST_URL}" \
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
                    git commit -m "Daily IPTV update: $(date '+%Y-%m-%d %H:%M:%S')"
                    git push "${REPO_URL}" HEAD:master
                '''
            }
        }
    }
    
    post {
        always {
            sh 'rm -f .git-credentials'
            cleanWs()
            archiveArtifacts artifacts: "${OUTPUT_FILE}", allowEmptyArchive: true
        }
        
        success {
            mail to: "${EMAIL_TO}",
                subject: "IPTV Check Success - ${currentBuild.fullDisplayName}",
                body: """\
                    Pipeline completed successfully!
                    Duration: ${currentBuild.durationString}
                    Check time: ${env.CHECK_DURATION}
                    Build URL: ${env.BUILD_URL}
                    Commit: ${env.GIT_COMMIT}
                """.stripIndent()
        }
        
        failure {
            mail to: "${EMAIL_TO}",
                subject: "IPTV Check Failed - ${currentBuild.fullDisplayName}",
                body: """\
                    Pipeline failed!
                    Duration: ${currentBuild.durationString}
                    Stage: ${currentBuild.getCurrentResult()}
                    Build URL: ${env.BUILD_URL}
                    Check logs for details
                """.stripIndent()
        }
        
        unstable {
            mail to: "${EMAIL_TO}",
                subject: "IPTV Check Unstable - ${currentBuild.fullDisplayName}",
                body: "Pipeline completed with warnings. Check ${env.BUILD_URL}"
        }
    }
}
