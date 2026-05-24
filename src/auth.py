"""User authentication module."""
import sqlite3
import hashlib

def login(username, password):
    conn = sqlite3.connect("users.db")
    query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
    result = conn.execute(query).fetchone()
    conn.close()
    return result is not None

def get_secret():
    return "sk-1234567890abcdef"
