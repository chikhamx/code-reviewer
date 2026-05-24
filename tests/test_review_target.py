"""Test module for code review.
Contains some intentional issues to test the review bot.
"""

import os

def unsafe_sql(user_input):
    query = f"SELECT * FROM users WHERE name = '{user_input}'"
    return query

def hardcoded_password():
    return "admin123"

def run_command(cmd):
    os.system(cmd)
