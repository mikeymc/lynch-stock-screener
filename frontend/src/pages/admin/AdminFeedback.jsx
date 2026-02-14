import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
    Megaphone,
    ExternalLink,
    Calendar,
    User,
    Mail,
    Globe,
    Image as ImageIcon,
    Maximize2,
    X
} from 'lucide-react';
import { format } from 'date-fns';

const API_BASE = '/api';

export default function AdminFeedback() {
    const [feedbackItems, setFeedbackItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [selectedImage, setSelectedImage] = useState(null);

    const fetchFeedback = async () => {
        try {
            setLoading(true);
            const response = await fetch(`${API_BASE}/admin/feedback`, {
                credentials: 'include'
            });

            if (!response.ok) {
                throw new Error('Failed to fetch feedback');
            }

            const data = await response.json();
            setFeedbackItems(data.feedback);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchFeedback();
    }, []);

    if (loading) {
        return (
            <div className="space-y-6">
                <div className="flex items-center justify-between">
                    <Skeleton className="h-8 w-48" />
                </div>
                <div className="grid gap-6">
                    {[1, 2, 3].map((i) => (
                        <Skeleton key={i} className="h-48 w-full rounded-xl" />
                    ))}
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <Alert variant="destructive">
                <AlertTitle>Error</AlertTitle>
                <AlertDescription>{error}</AlertDescription>
            </Alert>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold tracking-tight">User Feedback</h1>
                    <p className="text-muted-foreground">Review feedback and bug reports from users</p>
                </div>
                <Badge variant="outline" className="px-3 py-1">
                    {feedbackItems.length} Total Entries
                </Badge>
            </div>

            {feedbackItems.length === 0 ? (
                <Card className="flex flex-col items-center justify-center p-12 text-center">
                    <Megaphone className="h-12 w-12 text-muted-foreground opacity-20 mb-4" />
                    <h3 className="text-lg font-medium">No feedback received yet</h3>
                    <p className="text-muted-foreground max-w-sm mx-auto mt-2">
                        When users submit feedback through the widget, it will appear here.
                    </p>
                </Card>
            ) : (
                <div className="grid gap-6">
                    {feedbackItems.map((item) => (
                        <FeedbackCard
                            key={item.id}
                            item={item}
                            onViewImage={setSelectedImage}
                        />
                    ))}
                </div>
            )}

            {selectedImage && (
                <ImageOverlay
                    src={selectedImage}
                    onClose={() => setSelectedImage(null)}
                />
            )}
        </div>
    );
}

function FeedbackCard({ item, onViewImage }) {
    const metadata = typeof item.metadata === 'string'
        ? JSON.parse(item.metadata)
        : item.metadata || {};

    const formattedDate = format(new Date(item.created_at), 'PPP p');

    return (
        <Card className="overflow-hidden hover:shadow-md transition-shadow">
            <CardHeader className="pb-3 border-b bg-muted/30">
                <div className="flex justify-between items-start">
                    <div className="space-y-1">
                        <div className="flex items-center gap-2">
                            <CardTitle className="text-base font-semibold">
                                {item.user_name || 'Anonymous User'}
                            </CardTitle>
                            {item.status === 'new' && (
                                <Badge variant="default" className="bg-blue-500 hover:bg-blue-600">New</Badge>
                            )}
                        </div>
                        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                            <span className="flex items-center gap-1">
                                <Mail className="h-3 w-3" /> {item.email || 'No email provided'}
                            </span>
                            <span className="flex items-center gap-1">
                                <Calendar className="h-3 w-3" /> {formattedDate}
                            </span>
                            {item.page_url && (
                                <span className="flex items-center gap-1">
                                    <Globe className="h-3 w-3" />
                                    <a
                                        href={item.page_url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="hover:underline text-primary flex items-center gap-0.5"
                                    >
                                        Source Page <ExternalLink className="h-2 w-2" />
                                    </a>
                                </span>
                            )}
                        </div>
                    </div>
                    <Badge variant="outline" className="font-mono text-[10px]">
                        ID: {item.id}
                    </Badge>
                </div>
            </CardHeader>
            <CardContent className="pt-4 grid md:grid-cols-[1fr,200px] gap-6">
                <div className="space-y-4">
                    <div className="text-sm leading-relaxed whitespace-pre-wrap">
                        {item.feedback_text}
                    </div>

                    {Object.keys(metadata).length > 0 && (
                        <div className="pt-4 border-t mt-4">
                            <h4 className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-2">Technical Info</h4>
                            <div className="grid grid-cols-2 gap-2 text-[10px] bg-muted/50 p-2 rounded-md font-mono">
                                {Object.entries(metadata).map(([key, val]) => (
                                    <div key={key} className="truncate">
                                        <span className="text-muted-foreground">{key}:</span> {String(val)}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>

                <div className="space-y-4">
                    {item.screenshot_data ? (
                        <div className="group relative rounded-lg border bg-background overflow-hidden cursor-pointer aspect-square flex items-center justify-center"
                            onClick={() => onViewImage(item.screenshot_data)}>
                            <img
                                src={item.screenshot_data}
                                alt="Feedback Screenshot"
                                className="object-cover w-full h-full opacity-90 group-hover:opacity-100 transition-opacity"
                            />
                            <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                                <div className="bg-background rounded-full p-2 h-10 w-10 flex items-center justify-center shadow-lg">
                                    <Maximize2 className="h-5 w-5" />
                                </div>
                            </div>
                        </div>
                    ) : (
                        <div className="rounded-lg border border-dashed flex flex-col items-center justify-center p-8 bg-muted/20 text-muted-foreground aspect-square">
                            <ImageIcon className="h-8 w-8 opacity-20 mb-2" />
                            <span className="text-[10px] font-medium uppercase tracking-tight">No Image</span>
                        </div>
                    )}
                </div>
            </CardContent>
        </Card>
    );
}

function ImageOverlay({ src, onClose }) {
    return (
        <div
            className="fixed inset-0 z-[100] bg-black/90 flex items-center justify-center p-4 md:p-12 animate-in fade-in duration-200"
            onClick={onClose}
        >
            <Button
                variant="ghost"
                size="icon"
                className="absolute top-4 right-4 text-white hover:bg-white/20 rounded-full h-12 w-12"
                onClick={onClose}
            >
                <X className="h-6 w-6" />
            </Button>

            <div className="relative w-full h-full flex items-center justify-center" onClick={e => e.stopPropagation()}>
                <img
                    src={src}
                    alt="Enlarged feedback screenshot"
                    className="max-w-full max-h-full object-contain rounded-lg shadow-2xl"
                />
            </div>
        </div>
    );
}
