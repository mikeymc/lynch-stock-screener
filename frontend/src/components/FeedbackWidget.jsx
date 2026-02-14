import React, { useState, useRef, useEffect } from 'react';
import { MessageSquare, X, Camera, Loader2, Send } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Card } from '@/components/ui/card';
import { Label } from '@/components/ui/label';

export function FeedbackWidget({ isOpen, onClose }) {
    const [feedback, setFeedback] = useState('');
    const [screenshot, setScreenshot] = useState(null);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [submitted, setSubmitted] = useState(false);
    const [error, setError] = useState(null);
    const fileInputRef = useRef(null);

    // Reset state when closed
    useEffect(() => {
        if (!isOpen) {
            setFeedback('');
            setScreenshot(null);
            setSubmitted(false);
            setError(null);
        }
    }, [isOpen]);

    const handleScreenshot = (e) => {
        const file = e.target.files[0];
        if (file) {
            if (file.size > 5 * 1024 * 1024) {
                setError("Image size too large (max 5MB)");
                return;
            }

            const reader = new FileReader();
            reader.onloadend = () => {
                setScreenshot(reader.result);
                setError(null);
            };
            reader.readAsDataURL(file);
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!feedback.trim()) return;

        setIsSubmitting(true);
        setError(null);

        try {
            const payload = {
                feedback_text: feedback,
                page_url: window.location.href,
                screenshot_data: screenshot,
                metadata: {
                    userAgent: navigator.userAgent,
                    screenSize: `${window.innerWidth}x${window.innerHeight}`
                }
            };

            const response = await fetch(`/api/feedback`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'include',
                body: JSON.stringify(payload),
            });

            if (!response.ok) {
                throw new Error('Failed to submit feedback');
            }

            setSubmitted(true);
            setTimeout(() => {
                onClose();
            }, 2000);

        } catch (err) {
            setError(err.message);
        } finally {
            setIsSubmitting(false);
        }
    };

    if (!isOpen) return null;

    return (
        <div className="absolute bottom-6 left-6 z-50 animate-in fade-in slide-in-from-bottom-5 duration-300">
            <Card className="w-80 p-4 shadow-2xl border-border bg-card">
                <div className="flex justify-between items-center mb-4">
                    <h3 className="font-semibold">Send Feedback</h3>
                    <Button variant="ghost" size="icon" className="h-6 w-6" onClick={onClose}>
                        <X className="h-4 w-4" />
                    </Button>
                </div>

                {submitted ? (
                    <div className="text-center py-8 text-green-500">
                        <p className="font-medium">Thank you for your feedback!</p>
                    </div>
                ) : (
                    <form onSubmit={handleSubmit} className="space-y-4">
                        <div className="space-y-2">
                            <Label htmlFor="feedback">How can we improve?</Label>
                            <Textarea
                                id="feedback"
                                placeholder="Tell us what you think..."
                                value={feedback}
                                onChange={(e) => setFeedback(e.target.value)}
                                className="min-h-[100px] resize-none"
                            />
                        </div>

                        {screenshot && (
                            <div className="relative group rounded-md overflow-hidden border border-border">
                                <img src={screenshot} alt="Screenshot" className="w-full h-auto max-h-32 object-cover" />
                                <button
                                    type="button"
                                    className="absolute top-1 right-1 bg-black/50 hover:bg-black/70 text-white rounded-full p-1"
                                    onClick={() => setScreenshot(null)}
                                >
                                    <X className="w-3 h-3" />
                                </button>
                            </div>
                        )}

                        {error && <p className="text-sm text-red-500">{error}</p>}

                        <div className="flex justify-between items-center pt-2">
                            <input
                                type="file"
                                accept="image/*"
                                className="hidden"
                                ref={fileInputRef}
                                onChange={handleScreenshot}
                            />
                            <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                className="text-muted-foreground"
                                onClick={() => fileInputRef.current?.click()}
                            >
                                <Camera className="w-4 h-4 mr-2" />
                                Attach Image
                            </Button>

                            <Button type="submit" size="sm" disabled={!feedback.trim() || isSubmitting}>
                                {isSubmitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                            </Button>
                        </div>
                    </form>
                )}
            </Card>
        </div>
    );
}
