FROM gitpod/workspace-full

RUN pyenv install 3.9.6 && pyenv global 3.9.6
RUN npm install -g npm && npm install -g commitizen cz-emoji && echo "{ \"path\": \"cz-emoji\", \"config\": { \"cz-emoji\": { \"skipQuestions\": [\"scope\", \"issues\"] } } }" > /home/gitpod/.czrc