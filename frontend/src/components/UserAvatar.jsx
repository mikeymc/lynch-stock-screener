import React, { useState, useRef, useEffect, useLayoutEffect } from 'react';
import { createPortal } from 'react-dom';
import { useAuth } from '../context/AuthContext';

const API_BASE = '/api';

export default function UserAvatar() {
  const { user, logout } = useAuth();
  const [showDropdown, setShowDropdown] = useState(false);
  const dropdownRef = useRef(null);
  const buttonRef = useRef(null);
  const [dropdownPosition, setDropdownPosition] = useState({ top: 0, left: 0 });

  useEffect(() => {
    const updatePosition = () => {
      if (showDropdown && buttonRef.current && dropdownRef.current) {
        const buttonRect = buttonRef.current.getBoundingClientRect();
        const dropdownWidth = dropdownRef.current.offsetWidth;
        setDropdownPosition({
          top: buttonRect.bottom + 8,           // 8px gap below button
          left: buttonRect.right - dropdownWidth // Align right edges
        });
      }
    };

    const handleClickOutside = (event) => {
      if (
        buttonRef.current &&
        !buttonRef.current.contains(event.target) &&
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target)
      ) {
        setShowDropdown(false);
      }
    };

    if (showDropdown) {
      updatePosition();
      window.addEventListener('scroll', updatePosition, true);
      window.addEventListener('resize', updatePosition);
      document.addEventListener('mousedown', handleClickOutside);

      return () => {
        window.removeEventListener('scroll', updatePosition, true);
        window.removeEventListener('resize', updatePosition);
        document.removeEventListener('mousedown', handleClickOutside);
      };
    }
  }, [showDropdown]);

  // Recalculate position after dropdown is rendered
  useLayoutEffect(() => {
    if (showDropdown && buttonRef.current && dropdownRef.current) {
      const buttonRect = buttonRef.current.getBoundingClientRect();
      const dropdownWidth = dropdownRef.current.offsetWidth;
      setDropdownPosition({
        top: buttonRect.bottom + 8,
        left: buttonRect.right - dropdownWidth
      });
    }
  }, [showDropdown]);

  const handleLogout = async () => {
    await logout();
    setShowDropdown(false);
  };

  if (!user) return null;

  return (
    <>
      <button
        ref={buttonRef}
        onClick={() => setShowDropdown(!showDropdown)}
        className="hover:opacity-80 transition-opacity focus:outline-none focus:ring-2 focus:ring-blue-500"
        style={{
          width: '24px',
          height: '24px',
          minWidth: '24px',
          minHeight: '24px',
          maxWidth: '24px',
          maxHeight: '24px',
          padding: 0,
          borderRadius: '50%',
          border: '2px solid #d1d5db',
          overflow: 'hidden'
        }}
        title={user.name || user.email}
      >
        {user.picture ? (
          <img
            src={user.picture}
            alt={user.name || 'User'}
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              display: 'block'
            }}
          />
        ) : (
          <div style={{
            width: '100%',
            height: '100%',
            backgroundColor: '#3b82f6',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'white',
            fontWeight: 'bold',
            fontSize: '10px'
          }}>
            {(user.name || user.email || '?')[0].toUpperCase()}
          </div>
        )}
      </button>

      {showDropdown && createPortal(
        <div
          ref={dropdownRef}
          className="rounded-md shadow-lg border"
          style={{
            position: 'fixed',
            top: `${dropdownPosition.top}px`,
            left: `${dropdownPosition.left}px`,
            zIndex: 1000,
            backgroundColor: '#334155',
            borderColor: '#475569'
          }}
        >
          <button
            onClick={handleLogout}
            className="block w-full text-left px-4 py-2 text-sm transition-colors whitespace-nowrap"
            style={{
              color: '#f1f5f9',
              background: 'transparent',
              padding: '0.5rem 1rem'
            }}
            onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#475569'}
            onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
          >
            Sign out
          </button>
        </div>,
        document.body
      )}
    </>
  );
}
