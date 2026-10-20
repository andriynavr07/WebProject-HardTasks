#!/usr/bin/env bash
# Самопідписаний сертифікат для локального HTTPS
set -e
cd "$(dirname "$0")/.."
mkdir -p nginx/certs
openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
  -keyout nginx/certs/key.pem -out nginx/certs/cert.pem \
  -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
echo "Сертифікат створено в nginx/certs/"
