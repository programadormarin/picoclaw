package server

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/sipeed/picoclaw/pkg/auth"
	"github.com/sipeed/picoclaw/pkg/config"
)

const DefaultPort = "18800"

// providerStatus represents the auth status of a single provider in API responses.
type providerStatus struct {
	Provider   string `json:"provider"`
	AuthMethod string `json:"auth_method"`
	Status     string `json:"status"`
	AccountID  string `json:"account_id,omitempty"`
	Email      string `json:"email,omitempty"`
	ProjectID  string `json:"project_id,omitempty"`
	ExpiresAt  string `json:"expires_at,omitempty"`
}

// ── Middleware ───────────────────────────────────────────────────

func RequireJWT(secret []byte) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			authHeader := r.Header.Get("Authorization")
			if authHeader == "" || !strings.HasPrefix(authHeader, "Bearer ") {
				http.Error(w, "Unauthorized: Missing or invalid Authorization header", http.StatusUnauthorized)
				return
			}

			tokenString := strings.TrimPrefix(authHeader, "Bearer ")
			token, err := jwt.Parse(tokenString, func(token *jwt.Token) (interface{}, error) {
				if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
					return nil, fmt.Errorf("unexpected signing method: %v", token.Header["alg"])
				}
				return secret, nil
			})

			if err != nil || !token.Valid {
				http.Error(w, "Unauthorized: Invalid token", http.StatusUnauthorized)
				return
			}

			next.ServeHTTP(w, r)
		})
	}
}

// ── Route registration ───────────────────────────────────────────

func RegisterConfigAPI(mux *http.ServeMux, absPath string, secret []byte) {
	middleware := RequireJWT(secret)

	// GET /api/config — read config
	mux.Handle("GET /api/config", middleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		cfg, err := config.LoadConfig(absPath)
		if err != nil {
			http.Error(w, fmt.Sprintf("Failed to load config: %v", err), http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		resp := map[string]any{
			"config": cfg,
			"path":   absPath,
		}
		enc := json.NewEncoder(w)
		enc.SetIndent("", "  ")
		if err := enc.Encode(resp); err != nil {
			log.Printf("Failed to encode response: %v", err)
		}
	})))

	// PUT /api/config — save config
	mux.Handle("PUT /api/config", middleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, err := io.ReadAll(io.LimitReader(r.Body, 1<<20))
		if err != nil {
			http.Error(w, "Failed to read request body", http.StatusBadRequest)
			return
		}
		defer r.Body.Close()

		var cfg config.Config
		if err := json.Unmarshal(body, &cfg); err != nil {
			http.Error(w, fmt.Sprintf("Invalid JSON: %v", err), http.StatusBadRequest)
			return
		}

		if err := config.SaveConfig(absPath, &cfg); err != nil {
			http.Error(w, fmt.Sprintf("Failed to save config: %v", err), http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
	})))
}

func RegisterAuthAPI(mux *http.ServeMux, absPath string, secret []byte) {
	middleware := RequireJWT(secret)

	// GET /api/auth/status — all authenticated providers + pending login state
	mux.Handle("GET /api/auth/status", middleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		store, err := auth.LoadStore()
		if err != nil {
			http.Error(w, fmt.Sprintf("Failed to load auth store: %v", err), http.StatusInternalServerError)
			return
		}

		result := []providerStatus{}
		for name, cred := range store.Credentials {
			status := "active"
			if cred.IsExpired() {
				status = "expired"
			} else if cred.NeedsRefresh() {
				status = "needs_refresh"
			}
			ps := providerStatus{
				Provider:   name,
				AuthMethod: cred.AuthMethod,
				Status:     status,
				AccountID:  cred.AccountID,
				Email:      cred.Email,
				ProjectID:  cred.ProjectID,
			}
			if !cred.ExpiresAt.IsZero() {
				ps.ExpiresAt = cred.ExpiresAt.Format(time.RFC3339)
			}
			result = append(result, ps)
		}

		// Include pending device code state
		var pendingDevice map[string]any
		activeDeviceSessionMu.Lock()
		if activeDeviceSession != nil {
			activeDeviceSession.mu.Lock()
			pendingDevice = map[string]any{
				"provider":   activeDeviceSession.Provider,
				"status":     activeDeviceSession.Status,
				"device_url": activeDeviceSession.Info.VerifyURL,
				"user_code":  activeDeviceSession.Info.UserCode,
			}
			if activeDeviceSession.Error != "" {
				pendingDevice["error"] = activeDeviceSession.Error
			}
			if activeDeviceSession.Done {
				activeDeviceSession.mu.Unlock()
				activeDeviceSession = nil
			} else {
				activeDeviceSession.mu.Unlock()
			}
		}
		activeDeviceSessionMu.Unlock()

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]any{
			"providers":      result,
			"pending_device": pendingDevice,
		})
	})))

	// POST /api/auth/login — initiate provider login
	mux.Handle("POST /api/auth/login", middleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			Provider string `json:"provider"`
			Token    string `json:"token,omitempty"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		switch req.Provider {
		case "openai":
			handleOpenAILogin(w, absPath)
		case "anthropic":
			handleAnthropicLogin(w, req.Token, absPath)
		case "google-antigravity", "antigravity":
			handleGoogleAntigravityLogin(w, r, absPath)
		default:
			http.Error(
				w,
				fmt.Sprintf(
					"Unsupported provider: %s (supported: openai, anthropic, google-antigravity)",
					req.Provider,
				),
				http.StatusBadRequest,
			)
		}
	})))

	// POST /api/auth/logout — logout a provider
	mux.Handle("POST /api/auth/logout", middleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			Provider string `json:"provider"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, "Invalid request body", http.StatusBadRequest)
			return
		}

		if req.Provider == "" {
			if err := auth.DeleteAllCredentials(); err != nil {
				http.Error(w, fmt.Sprintf("Failed to logout: %v", err), http.StatusInternalServerError)
				return
			}
			clearAllAuthMethodsInConfig(absPath)
		} else {
			if err := auth.DeleteCredential(req.Provider); err != nil {
				http.Error(w, fmt.Sprintf("Failed to logout: %v", err), http.StatusInternalServerError)
				return
			}
			clearAuthMethodInConfig(absPath, req.Provider)
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
	})))

	// GET /auth/callback — OAuth browser callback for Google Antigravity
	mux.HandleFunc("GET /auth/callback", handleOAuthCallback)
}
