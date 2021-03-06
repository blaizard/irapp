FROM debian:latest
# Load dependencies
RUN apt-get update && apt-get install -y python git sudo  cmake  g++  python2.7  python3  valgrind 
# Add Jenkins user
RUN sudo groupadd -g 1000 1000
RUN sudo useradd -u 1000 -s /bin/sh -g 1000 1000