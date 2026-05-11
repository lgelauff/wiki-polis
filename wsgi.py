import sys
import os

# v2 lives in v2/; add it to sys.path so `from db import ...` etc. resolve
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'v2'))

from app import app

if __name__ == '__main__':
    app.run()
