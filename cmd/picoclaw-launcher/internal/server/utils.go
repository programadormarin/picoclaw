package server

import (
	"crypto/rand"
	"net"
	"os"
	"path/filepath"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

func DefaultConfigPath() string {
	home, err := os.UserHomeDir()
	if err != nil {
		return "config.json"
	}
	return filepath.Join(home, ".picoclaw", "config.json")
}

func GetLocalIP() string {
	addrs, err := net.InterfaceAddrs()
	if err != nil {
		return ""
	}
	for _, a := range addrs {
		if ipnet, ok := a.(*net.IPNet); ok && !ipnet.IP.IsLoopback() && ipnet.IP.To4() != nil {
			return ipnet.IP.String()
		}
	}
	return ""
}

// GenerateSecret generates a random 32-byte secret.
func GenerateSecret() ([]byte, error) {
	secret := make([]byte, 32)
	_, err := rand.Read(secret)
	return secret, err
}

// GenerateToken generates a signed JWT token with the given secret.
func GenerateToken(secret []byte) (string, error) {
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
		"iat": time.Now().Unix(),
		"exp": time.Now().Add(24 * time.Hour).Unix(), // 24h session
	})
	return token.SignedString(secret)
}
