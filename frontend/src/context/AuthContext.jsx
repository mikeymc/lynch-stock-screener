import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';

const AuthContext = createContext(null);

const API_BASE = '/api';

// =============================================================================
// Dev Auth Bypass Configuration
// =============================================================================
// Only allow bypass if we are in DEV mode AND the URL has ?dev_auth_bypass=true
// This supports "Dual-Mode":
// 1. Manual User (no param) -> Strict Auth
// 2. Automation/Robot (with param) -> Mock User
const DEV_AUTH_BYPASS = import.meta.env.DEV && new URLSearchParams(window.location.search).get('dev_auth_bypass') === 'true';

if (DEV_AUTH_BYPASS) {
  console.warn('⚠️ DEV AUTH BYPASS IS ENABLED - Using mock user for development');
}

// Mock user for dev bypass
const DEV_MOCK_USER = {
  id: 'dev-user-id',
  email: 'dev@localhost',
  name: 'Dev User',
  is_admin: true,
  has_completed_onboarding: true,
};

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const checkAuth = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/auth/user`, {
        credentials: 'include',
      });

      if (response.ok) {
        const userData = await response.json();
        setUser(userData);
      } else if (DEV_AUTH_BYPASS) {
        // Dev bypass enabled - use mock user
        setUser(DEV_MOCK_USER);
      } else {
        // No auth and no bypass
        setUser(null);
      }
    } catch (error) {
      console.error('Error checking auth:', error);
      if (DEV_AUTH_BYPASS) {
        // Dev bypass enabled - use mock user even on error
        setUser(DEV_MOCK_USER);
      } else {
        setUser(null);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = async () => {
    try {
      await fetch(`${API_BASE}/auth/logout`, {
        method: 'POST',
        credentials: 'include',
      });
    } catch (error) {
      console.error('Error logging out:', error);
    } finally {
      setUser(null);
    }
  };

  useEffect(() => {
    checkAuth();
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, checkAuth, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

