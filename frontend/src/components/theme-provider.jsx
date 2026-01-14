import { createContext, useContext, useEffect, useState } from "react"
import { useAuth } from "@/context/AuthContext"

const ThemeProviderContext = createContext({
    theme: "system",
    setTheme: () => null,
})

export function ThemeProvider({
    children,
    defaultTheme = "light",
    storageKey = "vite-ui-theme",
    ...props
}) {
    const [theme, setTheme] = useState(
        () => {
            // Check URL query param first for override
            if (typeof window !== 'undefined') {
                const params = new URLSearchParams(window.location.search)
                const themeParam = params.get('theme')
                if (themeParam) return themeParam
            }
            return localStorage.getItem(storageKey) || defaultTheme
        }
    )
    const [isLoading, setIsLoading] = useState(true)

    const { user, loading: authLoading } = useAuth()

    // Fetch user's theme from backend on mount
    useEffect(() => {
        // Wait for auth check to complete
        if (authLoading) return

        // If theme was set by URL param, don't fetch from backend to avoid overwriting the preview
        const params = new URLSearchParams(window.location.search)
        if (params.get('theme')) {
            setIsLoading(false)
            return
        }

        // If not authenticated, use localStorage/default and stop
        if (!user) {
            const localTheme = localStorage.getItem(storageKey) || defaultTheme
            setTheme(localTheme)
            setIsLoading(false)
            return
        }

        fetch('/api/settings/theme', { credentials: 'include' })
            .then(res => {
                if (res.ok) {
                    return res.json()
                }
                throw new Error('Failed to fetch theme')
            })
            .then(data => {
                if (data.theme) {
                    setTheme(data.theme)
                    localStorage.setItem(storageKey, data.theme)
                }
            })
            .catch(() => {
                // Fallback to localStorage on error
                const localTheme = localStorage.getItem(storageKey) || defaultTheme
                setTheme(localTheme)
            })
            .finally(() => {
                setIsLoading(false)
            })
    }, [storageKey, defaultTheme, user, authLoading])

    useEffect(() => {
        const root = window.document.documentElement

        // Remove all known theme classes
        root.classList.remove("light", "dark", "theme-paper", "theme-classic2")

        // Handle System preference
        if (theme === "system") {
            const systemTheme = window.matchMedia("(prefers-color-scheme: dark)")
                .matches
                ? "dark"
                : "light"
            root.classList.add(systemTheme)
            return
        }

        // Handle Explicit Themes
        if (theme === "dark" || theme === "midnight") {
            // Midnight is the new default dark
            root.classList.add("dark")
        } else if (theme === "paper") {
            root.classList.add("light", "theme-paper")
        } else if (theme === "classic2") {
            root.classList.add("dark", "theme-classic2")
        } else {
            // Default light (Original Paper in :root)
            root.classList.add("light")
        }
    }, [theme])

    const value = {
        theme,
        setTheme: (newTheme) => {
            localStorage.setItem(storageKey, newTheme)
            setTheme(newTheme)

            // Persist to backend if authenticated
            fetch('/api/settings/theme', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ theme: newTheme }),
                credentials: 'include'
            }).catch(err => {
                console.error('Failed to save theme to backend:', err)
                // Still works locally even if backend save fails
            })
        },
    }

    return (
        <ThemeProviderContext.Provider {...props} value={value}>
            {children}
        </ThemeProviderContext.Provider>
    )
}

export const useTheme = () => {
    const context = useContext(ThemeProviderContext)

    if (context === undefined)
        throw new Error("useTheme must be used within a ThemeProvider")

    return context
}
