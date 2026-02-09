import React, { useState, useRef, useEffect, useLayoutEffect } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const API_BASE = '/api';

export default function UserAvatar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
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
        className="hover:opacity-80 transition-opacity focus:outline-none focus:ring-2 focus:ring-blue-500 w-6 h-6 min-w-[24px] min-h-[24px] max-w-[24px] max-h-[24px] p-0 rounded-full border-2 border-gray-300 overflow-hidden"
        title={user.name || user.email}
      >
        {user.picture ? (
          <img
            src={user.picture}
            alt={user.name || 'User'}
            className="w-full h-full object-cover block"
          />
        ) : (
          <div className="w-full h-full bg-blue-500 flex items-center justify-center text-white font-bold text-[10px]">
            {(user.name || user.email || '?')[0].toUpperCase()}
          </div>
        )}
      </button>

      {showDropdown && createPortal(
        <div
          ref={dropdownRef}
          className="rounded-md shadow-lg border border-slate-600 bg-slate-700 z-50"
          style={{
            position: 'fixed',
            top: `${dropdownPosition.top}px`,
            left: `${dropdownPosition.left}px`
          }}
        >
          {user.user_type === 'admin' && (
            <button
              onClick={() => {
                navigate('/admin');
                setShowDropdown(false);
              }}
              className="block w-full text-left px-4 py-2 text-sm transition-colors whitespace-nowrap text-slate-100 bg-transparent hover:bg-slate-700"
            >
              Admin Panel
            </button>
          )}
          <button
            onClick={handleLogout}
            className="block w-full text-left px-4 py-2 text-sm transition-colors whitespace-nowrap text-slate-100 bg-transparent hover:bg-slate-700"
          >
            Sign out
          </button>
        </div>,
        document.body
      )}
    </>
  );
}
