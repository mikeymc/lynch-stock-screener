import { createContext, useContext, useEffect, useState } from "react"

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
        () => localStorage.getItem(storageKey) || defaultTheme
    )
    const [isLoading, setIsLoading] = useState(true)

    // Fetch user's theme from backend on mount
    useEffect(() => {
        fetch('/api/settings/theme', { credentials: 'include' })
            .then(res => {
                if (res.ok) {
                    return res.json()
                }
                // If not authenticated, use localStorage
                throw new Error('Not authenticated')
            })
            .then(data => {
                if (data.theme) {
                    setTheme(data.theme)
                    localStorage.setItem(storageKey, data.theme)
                }
            })
            .catch(() => {
                // Fallback to localStorage if not authenticated
                const localTheme = localStorage.getItem(storageKey) || defaultTheme
                setTheme(localTheme)
            })
            .finally(() => {
                setIsLoading(false)
            })
    }, [storageKey, defaultTheme])

    useEffect(() => {
        const root = window.document.documentElement

        root.classList.remove("light", "dark")

        if (theme === "system") {
            const systemTheme = window.matchMedia("(prefers-color-scheme: dark)")
                .matches
                ? "dark"
                : "light"

            root.classList.add(systemTheme)
            return
        }

        root.classList.add(theme)
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
