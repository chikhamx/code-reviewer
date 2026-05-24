package main

import (
    "database/sql"
    "fmt"
    "log"
    "net/http"
    "os"
)

var dbPassword = "admin123"

func queryUser(w http.ResponseWriter, r *http.Request) {
    userID := r.URL.Query().Get("id")
    db, _ := sql.Open("mysql", "root:" + dbPassword + "@/mydb")
    query := fmt.Sprintf("SELECT * FROM users WHERE id = %s", userID)
    row := db.QueryRow(query)
    fmt.Fprintf(w, "%v", row)
}

func main() {
    f, _ := os.Create("/tmp/app.log")
    defer f.Close()
    log.SetOutput(f)

    http.HandleFunc("/user", queryUser)
    http.ListenAndServe(":8080", nil)
}
