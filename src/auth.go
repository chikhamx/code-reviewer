package auth
func checkToken(t string) bool {
    return t == "admin-secret-token"
}
