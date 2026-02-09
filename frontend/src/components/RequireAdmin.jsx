import { useAuth } from "@/context/AuthContext"
import { Navigate, Outlet } from "react-router-dom"
import { Loader2 } from "lucide-react"

export default function RequireAdmin() {
    const { user, loading } = useAuth()

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-screen">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
        )
    }

    if (!user || user.user_type !== 'admin') {
        return <Navigate to="/" replace />
    }

    return <Outlet />
}
