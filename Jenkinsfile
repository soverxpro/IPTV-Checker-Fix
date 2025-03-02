pipeline {
    agent any
    
    options {
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '10'))
        timeout(time: 240, unit: 'MINUTES')
        retry(2)
        timestamps()
    }
    
    triggers {
        cron('0 0,6,12,18 * * *') // 00:00, 06:00, 12:00, 18:00
    }
    
    environment {
        GITHUB_TOKEN = credentials('github-token') // Убедимся, что это правильный ID
        REPO_URL = 'https://github.com/soverxpro/IPTV-Checker-Fix.git'
        PLAYLIST_URL = 'https://iptv.org.ua/iptv/avto.m3u8'
        OUTPUT_FILE = 'iptv.m3u'
 Schuster EMAIL_TO = 'soverx.online@gmail.com'
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
                            userRemoteConfigs: [[url: "${REPO_URL}", credentialsId: 'github-token']]
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
                withCredentials([usernamePassword(credentialsId: 'github-token', usernameVariable: 'GIT_USERNAME', passwordVariable: 'GIT_PASSWORD')]) {
                    sh '''
                        git config --global user.email "soverx.online@gmail.com"
                        git config --global user.name "SoverX Online"
                        git add "${OUTPUT_FILE}"
                        git commit -m "IPTV update at $(date '+%Y-%m-%d %H:%M:%S')"
                        git push https://${GIT_USERNAME}:${GIT_PASSWORD}@github.com/soverxpro/IPTV-Checker-Fix.git HEAD:master
                    '''
                }
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
