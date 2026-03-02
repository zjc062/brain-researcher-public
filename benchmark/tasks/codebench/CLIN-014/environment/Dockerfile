FROM ubuntu:24.04

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      python3 \
      python3-venv \
      python3-pip \
      curl && \
    python3 -m pip install --no-cache-dir \
      numpy==2.1.3 \
      pandas==2.2.3 \
      nibabel==5.3.2 \
      matplotlib==3.9.2 \
      requests==2.32.3 \
      nilearn==0.12.1 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
