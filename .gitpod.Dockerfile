FROM gitpod/workspace-full

RUN pyenv install 3.7.11 && pyenv install 3.8.11 && pyenv install 3.9.6 && pyenv install 3.10.2 && pyenv global 3.10.2 3.9.6 3.8.11 3.7.11
RUN npm install -g npm && npm install -g commitizen cz-emoji && echo "{ \"path\": \"cz-emoji\", \"config\": { \"cz-emoji\": { \"skipQuestions\": [\"scope\", \"issues\"] } } }" > /home/gitpod/.czrc