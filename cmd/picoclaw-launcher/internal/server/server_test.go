package server

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/sipeed/picoclaw/pkg/config"
)

// ── Test Utils ───────────────────────────────────────────────────

func setupConfigMux(t *testing.T, cfg *config.Config) (*http.ServeMux, string, []byte, string) {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, "config.json")
	data, err := json.MarshalIndent(cfg, "", "  ")
	if err != nil {
		t.Fatalf("marshal config: %v", err)
	}
	if err := os.WriteFile(path, data, 0o600); err != nil {
		t.Fatalf("write config: %v", err)
	}

	secret, _ := GenerateSecret()
	token, _ := GenerateToken(secret)

	mux := http.NewServeMux()
	RegisterConfigAPI(mux, path, secret)
	RegisterAuthAPI(mux, path, secret)
	return mux, path, secret, token
}

func addAuth(req *http.Request, token string) {
	req.Header.Set("Authorization", "Bearer "+token)
}

// ── Config API tests ─────────────────────────────────────────────

func TestGetConfig(t *testing.T) {
	cfg := &config.Config{
		ModelList: []config.ModelConfig{
			{ModelName: "gpt-4o", Model: "openai/gpt-4o"},
		},
	}
	mux, path, _, token := setupConfigMux(t, cfg)

	req := httptest.NewRequest("GET", "/api/config", nil)
	addAuth(req, token)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("GET /api/config: expected 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp struct {
		Config config.Config `json:"config"`
		Path   string        `json:"path"`
	}
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}

	if resp.Path != path {
		t.Errorf("expected path %q, got %q", path, resp.Path)
	}
	if len(resp.Config.ModelList) != 1 {
		t.Errorf("expected 1 model, got %d", len(resp.Config.ModelList))
	}
}

func TestUnauthorizedAccess(t *testing.T) {
	cfg := &config.Config{}
	mux, _, _, _ := setupConfigMux(t, cfg)

	req := httptest.NewRequest("GET", "/api/config", nil)
	// No auth header
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("expected 401 for unauthorized access, got %d", w.Code)
	}
}

func TestGetConfig_MissingFile_ReturnsDefault(t *testing.T) {
	mux := http.NewServeMux()
	secret, _ := GenerateSecret()
	token, _ := GenerateToken(secret)
	RegisterConfigAPI(mux, "/tmp/nonexistent-picoclaw-launcher-test/config.json", secret)

	req := httptest.NewRequest("GET", "/api/config", nil)
	addAuth(req, token)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	// LoadConfig returns a default empty config when file is missing
	if w.Code != http.StatusOK {
		t.Errorf("expected 200 for missing file (default config), got %d", w.Code)
	}
}

func TestPutConfig(t *testing.T) {
	cfg := &config.Config{}
	mux, path, _, token := setupConfigMux(t, cfg)

	newCfg := config.Config{
		ModelList: []config.ModelConfig{
			{ModelName: "claude", Model: "anthropic/claude-sonnet-4.6", AuthMethod: "token"},
		},
	}
	body, _ := json.Marshal(newCfg)

	req := httptest.NewRequest("PUT", "/api/config", strings.NewReader(string(body)))
	req.Header.Set("Content-Type", "application/json")
	addAuth(req, token)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("PUT /api/config: expected 200, got %d: %s", w.Code, w.Body.String())
	}

	saved, err := config.LoadConfig(path)
	if err != nil {
		t.Fatalf("load saved config: %v", err)
	}
	if len(saved.ModelList) != 1 {
		t.Fatalf("expected 1 model saved, got %d", len(saved.ModelList))
	}
}

// ── Auth API tests ───────────────────────────────────────────────

func TestAuthStatus(t *testing.T) {
	cfg := &config.Config{}
	mux, _, _, token := setupConfigMux(t, cfg)

	req := httptest.NewRequest("GET", "/api/auth/status", nil)
	addAuth(req, token)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("GET /api/auth/status: expected 200, got %d: %s", w.Code, w.Body.String())
	}

	var resp struct {
		Providers     []providerStatus `json:"providers"`
		PendingDevice map[string]any   `json:"pending_device"`
	}
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
}

func TestAuthLogout_InvalidBody(t *testing.T) {
	cfg := &config.Config{}
	mux, _, _, token := setupConfigMux(t, cfg)

	req := httptest.NewRequest("POST", "/api/auth/logout", strings.NewReader("{bad"))
	req.Header.Set("Content-Type", "application/json")
	addAuth(req, token)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400 for invalid body, got %d", w.Code)
	}
}

func TestOAuthCallback_InvalidState(t *testing.T) {
	cfg := &config.Config{}
	mux, _, _, _ := setupConfigMux(t, cfg)

	req := httptest.NewRequest("GET", "/auth/callback?state=invalid&code=test", nil)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("expected 400 for invalid state, got %d", w.Code)
	}
}

// ── Utility tests ────────────────────────────────────────────────

func TestDefaultConfigPath(t *testing.T) {
	path := DefaultConfigPath()
	if path == "" {
		t.Error("defaultConfigPath should not return empty")
	}
	if !strings.HasSuffix(path, filepath.Join(".picoclaw", "config.json")) {
		t.Errorf("expected path ending with .picoclaw/config.json, got %q", path)
	}
}

func TestGetLocalIP(t *testing.T) {
	// Just ensure it doesn't panic; IP may or may not be available
	ip := GetLocalIP()
	if ip != "" {
		// If returned, should look like an IP
		if !strings.Contains(ip, ".") {
			t.Errorf("getLocalIP returned non-IPv4 looking string: %q", ip)
		}
	}
}
