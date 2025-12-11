import React, { useState } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:5001/api';

export default function LoginModal() {
  const [loading, setLoading] = useState(false);

  const handleGoogleLogin = async () => {
    try {
      setLoading(true);

      const response = await fetch(`${API_BASE}/auth/google/url`, {
        credentials: 'include',
      });

      if (!response.ok) {
        throw new Error('Failed to get authorization URL');
      }

      const data = await response.json();
      window.location.href = data.url;
    } catch (err) {
      console.error('Login error:', err);
      setLoading(false);
    }
  };

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center'
    }}>
      <div
        onClick={loading ? undefined : handleGoogleLogin}
        style={{
          fontSize: '40px',
          color: '#e2e8f0',
          cursor: 'pointer',
          userSelect: 'none'
        }}
        onMouseEnter={(e) => e.target.style.opacity = '0.7'}
        onMouseLeave={(e) => e.target.style.opacity = '1'}
      >
        {loading ? 'Signing in...' : 'Sign In'}
      </div>
    </div>
  );
}
