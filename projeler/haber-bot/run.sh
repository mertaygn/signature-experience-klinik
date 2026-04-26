#!/bin/bash
# Fuar Haber Botu - Başlatma Scripti
cd "$(dirname "$0")"
source venv/bin/activate
python main.py "$@"
