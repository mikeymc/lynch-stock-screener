import React, { createContext, useContext, useState, useEffect } from 'react';

const AuthContext = createContext(null);

const API_BASE = '/api';

// =============================================================================
// Dev Auth Bypass Configuration
// =============================================================================
// Only allow bypass if VITE_DEV_AUTH_BYPASS is explicitly "true"
// In production builds, this env var should never be set
const DEV_AUTH_BYPASS = import.meta.env.VITE_DEV_AUTH_BYPASS === 'true';

if (DEV_AUTH_BYPASS) {
  console.warn('⚠️ DEV AUTH BYPASS IS ENABLED - Using mock user for development');
}

// Mock user for dev bypass
const DEV_MOCK_USER = {
  email: 'dev@localhost',
  name: 'Dev User',
  is_admin: true,
};

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const checkAuth = async () => {
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
  };

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

