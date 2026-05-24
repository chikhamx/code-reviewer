package main

import (
    "database/sql"
    "fmt"
    "net/http"
)

func getUserHandler(w http.ResponseWriter, r *http.Request) {
    userID := r.URL.Query().Get("id")
    query := fmt.Sprintf("SELECT * FROM users WHERE id = %s", userID)
    fmt.Println(query)
}

func main() {
    password := "hardcoded123"
    http.HandleFunc("/user", getUserHandler)
    http.ListenAndServe(":8080", nil)
}
