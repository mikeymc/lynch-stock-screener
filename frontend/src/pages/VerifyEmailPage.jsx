import React, { useEffect, useState, useRef } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Button } from "@/components/ui/button"
import {
    Card,
    CardContent,
    CardHeader,
    CardTitle,
    CardDescription
} from "@/components/ui/card"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"

export default function VerifyEmailPage() {
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    const token = searchParams.get('token');

    const [status, setStatus] = useState('verifying'); // verifying, success, error
    const [message, setMessage] = useState('');
    const verifiedRef = useRef(false);

    useEffect(() => {
        if (!token) {
            setStatus('error');
            setMessage('Invalid verification link.');
            return;
        }

        if (verifiedRef.current) return;
        verifiedRef.current = true;

        const verifyToken = async () => {
            try {
                const response = await fetch('/api/auth/verify', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ token })
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.error || 'Verification failed');
                }

                setStatus('success');
            } catch (err) {
                console.error('Verification error:', err);
                setStatus('error');
                setMessage(err.message || 'Verification failed. The link may have expired.');
            }
        };

        verifyToken();
    }, [token]);

    return (
        <div className="container relative h-screen flex-col items-center justify-center grid lg:max-w-none lg:grid-cols-2 lg:px-0">
            <div className="relative hidden h-full flex-col bg-muted p-10 text-white lg:flex dark:border-r">
                <div className="absolute inset-0 bg-zinc-900" />
                <div className="relative z-20 flex items-center text-lg font-medium">
                    <svg
                        xmlns="http://www.w3.org/2000/svg"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        className="mr-2 h-6 w-6"
                    >
                        <path d="M15 6v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3V6a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3" />
                    </svg>
                    Lynch Stock Screener
                </div>
            </div>
            <div className="lg:p-8 flex h-full items-center justify-center bg-background">
                <div className="mx-auto flex w-full flex-col justify-center space-y-6 sm:w-[350px]">
                    <Card>
                        <CardHeader>
                            <CardTitle>Email Verification</CardTitle>
                            <CardDescription>
                                {status === 'verifying' && "Verifying your account..."}
                                {status === 'success' && "Account verified!"}
                                {status === 'error' && "Verification issue"}
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            {status === 'success' && (
                                <Alert className="border-green-500 text-green-500">
                                    <AlertTitle>Success</AlertTitle>
                                    <AlertDescription>
                                        Your email has been verified successfully.
                                    </AlertDescription>
                                </Alert>
                            )}

                            {status === 'error' && (
                                <Alert variant="destructive">
                                    <AlertTitle>Error</AlertTitle>
                                    <AlertDescription>
                                        {message}
                                    </AlertDescription>
                                </Alert>
                            )}

                            <Button
                                className="w-full"
                                onClick={() => navigate('/login')}
                            >
                                Continue to Login
                            </Button>
                        </CardContent>
                    </Card>
                </div>
            </div>
        </div>
    );
}
