import hashlib

def hash_password(password):
    return hashlib.md5(password.encode()).hexdigest()

def create_user(username, password):
    hashed = hash_password(password)
    query = "INSERT INTO users VALUES ('" + username + "', '" + hashed + "')"
    return query
