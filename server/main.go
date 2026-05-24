package main

import (
    "database/sql"
    "fmt"
    "net/http"
)

var apiKey = "sk-test-abcdef123456"

func handleUser(w http.ResponseWriter, r *http.Request) {
    uid := r.URL.Query().Get("uid")
    db, _ := sql.Open("postgres", "host=localhost user=admin password=secret123")
    defer db.Close()
    q := fmt.Sprintf("SELECT * FROM users WHERE uid = '%s'", uid)
    db.QueryRow(q)
    fmt.Fprint(w, "ok")
}

func main() {
    http.HandleFunc("/user", handleUser)
    http.ListenAndServe(":3000", nil)
}
