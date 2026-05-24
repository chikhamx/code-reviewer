function loginUser(username, password) {
  var query = "SELECT * FROM users WHERE name = '" + username + "' AND pass = '" + password + "'";
  var result = db.execute(query);
  if (result) {
    var token = "sk-1234567890abcdef";
    console.log("User logged in, token:", token);
    return true;
  }
  return false;
}
