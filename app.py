"""Flask entry point for the CMSC 495 campus navigation frontend.

Backend integration belongs in /api/locations and /api/route.
The frontend uses clearly marked demonstration data until those routes exist.
"""
from flask import Flask, render_template

app = Flask(__name__)


@app.get('/')
def index():
    return render_template('index.html')


if __name__ == '__main__':
    app.run(debug=True)
