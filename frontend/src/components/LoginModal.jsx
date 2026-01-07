import React, { useState } from 'react';

const API_BASE = '/api';

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
    <div className="fixed inset-0 flex items-center justify-center">
      <div
        onClick={loading ? undefined : handleGoogleLogin}
        className={`text-[40px] text-slate-200 cursor-pointer select-none transition-opacity hover:opacity-70 ${loading ? '' : 'active:opacity-100'}`}
      >
        {loading ? 'Signing in...' : 'Sign In'}
      </div>
    </div>
  );
}
