# AI-Based Study Time Optimizer

A full-stack machine learning web application that predicts a student's productivity score based on lifestyle and study habits.

## Features
- Flask backend with ML model integration
- Multi-page responsive frontend
- Productivity score prediction
- Smart AI insights and suggestions
- Progress/history tracking
- Chart-based result visualization
- Built-in study assistant chatbot
- Optional Razorpay premium flow for demo/extension

## Tech Stack
Python, Flask, Pandas, Scikit-learn, HTML, CSS, Bootstrap, Chart.js

## Run Locally
```bash
pip install -r requirements.txt
python app.py
```

Open: http://127.0.0.1:10000

## Deployment
Build command:
```bash
pip install -r requirements.txt
```
Start command:
```bash
gunicorn app:app
```
