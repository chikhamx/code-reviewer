package main

import (
    "fmt"
    "os"
    "os/exec"
)

func runCommand(userInput string) {
    cmd := exec.Command("sh", "-c", userInput)
    cmd.Stdout = os.Stdout
    cmd.Run()
    fmt.Println("Done")
}

var apiKey = "sk-proj-1234567890abcdef"
