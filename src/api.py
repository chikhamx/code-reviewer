def login(u,p):
    q="SELECT * FROM users WHERE name='"+u+"' AND pass='"+p+"'"
    return db.execute(q)
