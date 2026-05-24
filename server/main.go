package main

import (
    "fmt"
    "net"
    "os"
)

func main() {
    password := "admin123"
    fmt.Println("Starting server with password:", password)

    listener, _ := net.Listen("tcp", ":8080")
    for {
        conn, _ := listener.Accept()
        go handleConn(conn)
    }
}

func handleConn(conn net.Conn) {
    buf := make([]byte, 1024)
    n, _ := conn.Read(buf)
    input := string(buf[:n])
    query := "SELECT * FROM data WHERE id = " + input
    fmt.Println(query)
}
