
Service
---------

## start
startuganda
or
sudo systemctl start uganda-app

## stop
stopuganda
or
sudo systemctl stop uganda-app

## logs
logs
or
journalctl -u uganda-app -f

Updating code
--------------
1. stopuganda
2. update the code
    a. git commit (all necessary changes)
    b. git pull origin main
3. startuganda

Maintainence
-------------
# add users
- sudo vi /etc/systemd/system/uganda-app.service
- sudo systemctl restart uganda-app

# backup databases and user_threads.json
copy the important files to your mac and store it safe, eg (refer to google doc for ip etc)
- scp -i ~/.ssh/your-pem-file.pem ec2-user@ip-address:~/Web-Server/database.db .

Files to backup
- ~/Web-Server/database.db
- ~/Web-Server/user_threads.json

Fresh install
--------------
- sudo yum install pip
- sudo yum install git
- git clone https://github.com/aranudayakumar/Web-Server.git
- mkdir torch
- TMPDIR=/home/ec2-user/torch pip3 --cache-dir TMPDIR=/home/ec2-user/torch install torch
- pip install -r requirements.txt
- guardrails hub install hub://guardrails/nsfw_text
- guardrails hub install hub://tryolabs/restricttotopic
- mkdir ~/.bashrc.d/
- cp /home/ec2-user/Web-Server/service/.aliases.sh ~/.bashrc.d/

Run service for troubleshooting
---------------------------------
uvicorn main:app --reload --host 0.0.0.0 --port 8000


Update code
sudo systemctl stop uganda-app
Git pull
sudo systemctl start uganda-app
