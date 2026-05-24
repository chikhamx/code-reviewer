package main

import (
    "database/sql"
    "encoding/json"
    "net/http"
)

var dbConnStr = "postgres://admin:super_secret_123@localhost/app"

type User struct {
    ID    int    json:"id"
    Name  string json:"name"
}

func getUser(w http.ResponseWriter, r *http.Request) {
    id := r.URL.Query().Get("id")
    db, _ := sql.Open("postgres", dbConnStr)
    defer db.Close()
    query := "SELECT * FROM users WHERE id = " + id
    db.QueryRow(query)
    user := User{ID: 1, Name: "admin"}
    json.NewEncoder(w).Encode(user)
}

func main() {
    http.HandleFunc("/user", getUser)
    http.ListenAndServe(":8080", nil)
}
