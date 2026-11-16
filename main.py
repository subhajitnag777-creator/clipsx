"""Clips X Server Entrypoint.

Usage on your VPS or Server:
    python main.py
    python3 main.py
"""
import os
import sys

# Add project root to sys.path so studio package is discoverable anywhere
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from studio.server import main

if __name__ == "__main__":
    main()
