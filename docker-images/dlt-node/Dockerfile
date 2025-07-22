# Use a base image with Ubuntu 
FROM ubuntu:20.04

LABEL maintainer="azahir@pa.uc3m.es"

# Set environment variables to avoid user interaction during the installation
ENV DEBIAN_FRONTEND=noninteractive

# Install the required software-properties-common package
RUN apt-get update && \
    apt-get install -y software-properties-common \
    wget \
    iputils-ping \
&& apt-get clean \
&& rm -rf /var/lib/apt/lists/*
 

# Download and install specific version of Geth (1.13)
RUN wget https://gethstore.blob.core.windows.net/builds/geth-linux-amd64-1.13.15-c5ba367e.tar.gz && \
    tar -xvf geth-linux-amd64-1.13.15-c5ba367e.tar.gz && \
    mv geth-linux-amd64-1.13.15-c5ba367e/geth /usr/local/bin/ && \
    rm -rf geth-linux-amd64-1.13.15-c5ba367e geth-linux-amd64-1.13.15-c5ba367e.tar.gz


# Add Ethereum PPA repository
RUN add-apt-repository -y ppa:ethereum/ethereum

# Update package list
RUN apt-get update

# Install Ethereum package (bootnode)
RUN apt-get install -y bootnode

# Set the working directory inside the container
WORKDIR /dlt-network

# # Copy the entire directories and their contents into the container
COPY bootnode ./bootnode

# Copy node directories individually
COPY node1 ./node1
COPY node2 ./node2
COPY node3 ./node3
COPY node4 ./node4
COPY node5 ./node5
COPY node6 ./node6
COPY node7 ./node7
COPY node8 ./node8
COPY node9 ./node9
COPY node10 ./node10
COPY node11 ./node11
COPY node12 ./node12
COPY node13 ./node13
COPY node14 ./node14
COPY node15 ./node15
COPY node16 ./node16
COPY node17 ./node17
COPY node18 ./node18
COPY node19 ./node19
COPY node20 ./node20
COPY node21 ./node21
COPY node22 ./node22
COPY node23 ./node23
COPY node24 ./node24
COPY node25 ./node25
COPY node26 ./node26
COPY node27 ./node27
COPY node28 ./node28
COPY node29 ./node29
COPY node30 ./node30
COPY node31 ./node31
COPY node32 ./node32
COPY node33 ./node33
COPY node34 ./node34
COPY node35 ./node35
COPY node36 ./node36
COPY node37 ./node37
COPY node38 ./node38
COPY node39 ./node39
COPY node40 ./node40
COPY node41 ./node41
COPY node42 ./node42
COPY node43 ./node43
COPY node44 ./node44
COPY node45 ./node45
COPY node46 ./node46
COPY node47 ./node47
COPY node48 ./node48
COPY node49 ./node49
COPY node50 ./node50

RUN mkdir logs

# # Copy the shell scripts and other files
COPY scripts/bootnode_start.sh ./bootnode_start.sh
COPY scripts/node_start.sh ./node_start.sh
COPY scripts/password.txt ./password.txt

# Make bash scripts executable
RUN chmod +x ./*_start.sh