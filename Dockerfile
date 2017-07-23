FROM ubuntu:14.04

MAINTAINER MorkHub, https://github.com/MorkHub/PedantBot

#Install dependencies
RUN sudo apt-get update \
    && sudo apt-get install software-properties-common -y \
    && sudo add-apt-repository ppa:fkrull/deadsnakes -y \
    && sudo add-apt-repository ppa:mc3man/trusty-media -y \
    && sudo apt-get update -y \
    && sudo apt-get install build-essential unzip -y \
    && sudo apt-get install python3.5 python3.5-dev -y \
    && sudo apt-get install ffmpeg -y \
    && sudo apt-get install libopus-dev -y \
    && sudo apt-get install libffi-dev -y

#Install Pip
RUN sudo apt-get install wget \
    && wget https://bootstrap.pypa.io/get-pip.py \
    && sudo python3 get-pip.py

#Add musicBot
ADD . /pedantbot
WORKDIR /pedantbot

#Install PIP dependencies
RUN sudo pip install -r requirements.txt

CMD run.sh

api='77feaa99be7a879a3d931f730a2e96b6'
secret='cd5a3e82334ed4f23705916526439e38'