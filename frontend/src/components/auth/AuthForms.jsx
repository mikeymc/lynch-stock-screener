import React, { useState } from 'react';
import { Button } from "@/components/ui/button"
import {
    Card,
    CardContent,
    CardDescription,
    CardFooter,
    CardHeader,
    CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
    Tabs,
    TabsContent,
    TabsList,
    TabsTrigger,
} from "@/components/ui/tabs"
import { Separator } from "@/components/ui/separator"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { useAuth } from "@/context/AuthContext"

const API_BASE = '/api';

export function AuthForms() {
    const [isLoading, setIsLoading] = useState(false)
    const [error, setError] = useState(null)
    const [activeTab, setActiveTab] = useState("login")
    const [verificationSent, setVerificationSent] = useState(false)
    const [email, setEmail] = useState("")

    const { checkAuth } = useAuth()

    const handleGoogleLogin = async () => {
        try {
            setIsLoading(true);
            setError(null);

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
            setError("Failed to initialize Google Login. Please try again.");
            setIsLoading(false);
        }
    };

    const handleEmailAuth = async (e, type) => {
        e.preventDefault();
        setIsLoading(true);
        setError(null);

        const emailStr = e.target.elements.email.value;
        const password = e.target.elements.password.value;

        if (type === 'signup') {
            setEmail(emailStr)
        }

        try {
            const endpoint = type === 'login' ? '/auth/login' : '/auth/register';
            const response = await fetch(`${API_BASE}${endpoint}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ email: emailStr, password }),
                credentials: 'include',
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Authentication failed');
            }

            // Refresh auth state to trigger redirect in App.jsx
            // Refresh auth state to trigger redirect in App.jsx
            if (type === 'login') {
                await checkAuth();
            } else {
                setVerificationSent(true);
                setIsLoading(false);
            }

        } catch (err) {
            console.error('Auth error:', err);
            setError(err.message);
            setIsLoading(false);
        }
    };

    if (verificationSent) {
        return (
            <Card className="w-full">
                <CardHeader>
                    <CardTitle>Check your email</CardTitle>
                    <CardDescription>
                        We've sent a verification link to <span className="font-medium text-foreground">{email}</span>.
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <p className="text-sm text-muted-foreground mb-4">
                        Please check your inbox and click the link to verify your account. You won't be able to log in until you verify your email.
                    </p>
                    <Button
                        variant="outline"
                        className="w-full"
                        onClick={() => {
                            setVerificationSent(false);
                            setActiveTab("login");
                        }}
                    >
                        Back to Login
                    </Button>
                </CardContent>
            </Card>
        )
    }

    return (
        <div className="w-full max-w-[400px]">
            <Tabs defaultValue="login" value={activeTab} className="w-full" onValueChange={setActiveTab}>
                <TabsList className="grid w-full grid-cols-2 mb-4">
                    <TabsTrigger value="login">Login</TabsTrigger>
                    <TabsTrigger value="signup">Sign Up</TabsTrigger>
                </TabsList>

                <TabsContent value="login">
                    <Card>
                        <CardHeader>
                            <CardTitle>Welcome back</CardTitle>
                            <CardDescription>
                                Sign in to your account to continue screening.
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            {error && (
                                <Alert variant="destructive" className="mb-2">
                                    <AlertDescription>{error}</AlertDescription>
                                </Alert>
                            )}

                            <div className="space-y-2">
                                <Button
                                    variant="outline"
                                    className="w-full flex items-center gap-2 h-11"
                                    onClick={handleGoogleLogin}
                                    disabled={isLoading}
                                >
                                    <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden="true"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" /><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" /><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.84z" fill="#FBBC05" /><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" /></svg>
                                    Continue with Google
                                </Button>
                            </div>

                            <div className="relative">
                                <div className="absolute inset-0 flex items-center">
                                    <Separator className="w-full" />
                                </div>
                                <div className="relative flex justify-center text-xs uppercase">
                                    <span className="bg-background px-2 text-muted-foreground">
                                        Or continue with
                                    </span>
                                </div>
                            </div>

                            <form onSubmit={(e) => handleEmailAuth(e, 'login')} className="space-y-4">
                                <div className="space-y-2">
                                    <Label htmlFor="email">Email</Label>
                                    <Input id="email" type="email" placeholder="m@example.com" disabled={isLoading} />
                                </div>
                                <div className="space-y-2">
                                    <Label htmlFor="password">Password</Label>
                                    <Input id="password" type="password" disabled={isLoading} />
                                </div>
                                <Button type="submit" className="w-full" disabled={isLoading}>
                                    {isLoading ? "Signing In..." : "Sign In"}
                                </Button>
                            </form>
                        </CardContent>
                    </Card>
                </TabsContent>

                <TabsContent value="signup">
                    <Card>
                        <CardHeader>
                            <CardTitle>Create an account</CardTitle>
                            <CardDescription>
                                Enter your email below to create your account
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            {error && (
                                <Alert variant="destructive" className="mb-2">
                                    <AlertDescription>{error}</AlertDescription>
                                </Alert>
                            )}

                            <div className="space-y-2">
                                <Button
                                    variant="outline"
                                    className="w-full flex items-center gap-2 h-11"
                                    onClick={handleGoogleLogin}
                                    disabled={isLoading}
                                >
                                    <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden="true"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" /><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" /><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.84z" fill="#FBBC05" /><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" /></svg>
                                    Continue with Google
                                </Button>
                            </div>

                            <div className="relative">
                                <div className="absolute inset-0 flex items-center">
                                    <Separator className="w-full" />
                                </div>
                                <div className="relative flex justify-center text-xs uppercase">
                                    <span className="bg-background px-2 text-muted-foreground">
                                        Or continue with
                                    </span>
                                </div>
                            </div>

                            <form onSubmit={(e) => handleEmailAuth(e, 'signup')} className="space-y-4">
                                <div className="space-y-2">
                                    <Label htmlFor="email">Email</Label>
                                    <Input id="email" type="email" placeholder="m@example.com" disabled={isLoading} />
                                </div>
                                <div className="space-y-2">
                                    <Label htmlFor="password">Password</Label>
                                    <Input id="password" type="password" disabled={isLoading} />
                                </div>
                                <Button type="submit" className="w-full" disabled={isLoading}>
                                    {isLoading ? "Creating Account..." : "Create Account"}
                                </Button>
                            </form>
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>
        </div>
    )
}
