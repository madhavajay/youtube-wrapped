#!/bin/bash

rm -rf .venv
uv venv -p 3.12
uv pip install -r requirements.txt
uv run main.py