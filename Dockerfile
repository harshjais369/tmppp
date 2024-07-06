FROM ubuntu:latest

LABEL maintainer="harshjais369@gmail.com" version="1.0" description="Dockerfile for crocbot"

RUN apt -y update && apt -y upgrade
RUN apt -y install git && apt -y install python3 && apt -y install python3-pip
RUN git clone https://github.com/harshjais369/tmppp.git /root/harshjais369
# COPY . /root/harshjais369
WORKDIR /root/harshjais369
RUN pip3 install -U -r requirements.txt --break-system-packages

CMD ["python3", "./crocbot/crocbot.py"]
