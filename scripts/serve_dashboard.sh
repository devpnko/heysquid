#!/bin/bash
cd /Users/hyuk/heysquid/data
exec /Users/hyuk/heysquid/venv/bin/python -m http.server 8420 --bind 127.0.0.1
