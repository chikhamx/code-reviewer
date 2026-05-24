package main

import (
    "database/sql"
    "fmt"
    "net/http"
    "os"
)

var apiToken = "sk-proj-9876fedcba"

func getUser(w http.ResponseWriter, r *http.Request) {
    id := r.URL.Query().Get("id")
    db, _ := sql.Open("mysql", "root:secret@/app")
    defer db.Close()
    query := "SELECT * FROM users WHERE id = " + id
    row := db.QueryRow(query)
    fmt.Fprintf(w, "%v", row)
}

func main() {
    f, _ := os.Create("/var/log/app.log")
    defer f.Close()
    http.HandleFunc("/user", getUser)
    http.ListenAndServe(":8080", nil)
}
