FROM ubuntu:24.04

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      python3 \
      python3-venv \
      curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

RUN pip install --no-cache-dir \
    numpy==1.26.4 \
    scipy==1.12.0 \
    nibabel==5.2.1 \
    nilearn==0.10.4 \
    scikit-learn==1.4.2
