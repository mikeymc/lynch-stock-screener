
import { useState, useEffect } from 'react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { MessageSquare, User, Calendar, Search } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import ChatMessage from '@/components/ChatMessage'
import { Input } from '@/components/ui/input'
import { useAuth } from '@/context/AuthContext'

const API_BASE = '/api'

export default function AdminConversations() {
    const [conversations, setConversations] = useState([])
    const [selectedId, setSelectedId] = useState(null)
    const [messages, setMessages] = useState([])
    const [loading, setLoading] = useState(true)
    const [messagesLoading, setMessagesLoading] = useState(false)
    const [searchQuery, setSearchQuery] = useState('')

    // Mock user for ChatMessage since we are viewing as admin
    // The ChatMessage component usage useAuth to get user picture, but here we are viewing OTHER users' messages.
    // We might need to adjust ChatMessage or wrap it.
    // Actually ChatMessage uses useAuth() to decide if it's "ME" (right side) or "BOT" (left side).
    // In admin view, "User" messages should probably be on right (or left? usually right is "me").
    // But here "me" is the admin observing.
    // Let's keep User on right to match the user's experience.

    useEffect(() => {
        fetchConversations()
    }, [])

    useEffect(() => {
        if (selectedId) {
            fetchMessages(selectedId)
        } else {
            setMessages([])
        }
    }, [selectedId])

    const fetchConversations = async () => {
        setLoading(true)
        try {
            const response = await fetch(`${API_BASE}/admin/conversations`, {
                credentials: 'include'
            })
            if (!response.ok) throw new Error('Failed to fetch conversations')
            const data = await response.json()
            setConversations(data.conversations || [])
        } catch (err) {
            console.error('Error fetching conversations:', err)
        } finally {
            setLoading(false)
        }
    }

    const fetchMessages = async (id) => {
        setMessagesLoading(true)
        try {
            const response = await fetch(`${API_BASE}/admin/conversations/${id}/messages`, {
                credentials: 'include'
            })
            if (!response.ok) throw new Error('Failed to fetch messages')
            const data = await response.json()
            setMessages(data.messages || [])
        } catch (err) {
            console.error('Error fetching messages:', err)
        } finally {
            setMessagesLoading(false)
        }
    }

    const filteredConversations = conversations.filter(c =>
        (c.title && c.title.toLowerCase().includes(searchQuery.toLowerCase())) ||
        (c.user_email && c.user_email.toLowerCase().includes(searchQuery.toLowerCase()))
    )

    return (
        <div className="flex h-[calc(100vh-100px)] gap-4">
            {/* Sidebar: Conversation List */}
            <Card className="w-1/3 flex flex-col">
                <CardHeader className="p-4 border-b">
                    <CardTitle className="text-lg flex items-center justify-between">
                        <span>Conversations</span>
                        <Badge variant="secondary">{conversations.length}</Badge>
                    </CardTitle>
                    <div className="relative mt-2">
                        <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                        <Input
                            placeholder="Search user or title..."
                            className="pl-8"
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                        />
                    </div>
                </CardHeader>
                <ScrollArea className="flex-1">
                    <div className="divide-y">
                        {loading ? (
                            <div className="p-4 text-center text-muted-foreground">Loading...</div>
                        ) : filteredConversations.length === 0 ? (
                            <div className="p-4 text-center text-muted-foreground">No conversations found</div>
                        ) : (
                            filteredConversations.map((conv) => (
                                <button
                                    key={conv.id}
                                    onClick={() => setSelectedId(conv.id)}
                                    className={`w-full text-left p-3 hover:bg-muted/50 transition-colors ${selectedId === conv.id ? 'bg-muted' : ''
                                        }`}
                                >
                                    <div className="flex justify-between items-start mb-1">
                                        <span className="font-medium truncate block max-w-[180px]" title={conv.title}>
                                            {conv.title || 'New Chat'}
                                        </span>
                                        <span className="text-xs text-muted-foreground whitespace-nowrap">
                                            {formatDistanceToNow(new Date(conv.updated_at || conv.created_at), { addSuffix: true })}
                                        </span>
                                    </div>
                                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                        <User className="h-3 w-3" />
                                        <span className="truncate">{conv.user_email}</span>
                                    </div>
                                </button>
                            ))
                        )}
                    </div>
                </ScrollArea>
            </Card>

            {/* Main Content: Messages */}
            <Card className="flex-1 flex flex-col">
                <CardHeader className="p-4 border-b min-h-[60px] flex justify-center">
                    {selectedId ? (
                        <div className="flex justify-between items-center">
                            <div>
                                <CardTitle className="text-lg">
                                    {conversations.find(c => c.id === selectedId)?.title || 'Chat'}
                                </CardTitle>
                                <div className="text-xs text-muted-foreground mt-1">
                                    User: {conversations.find(c => c.id === selectedId)?.user_email}
                                </div>
                            </div>
                        </div>
                    ) : (
                        <div className="text-muted-foreground">Select a conversation to view</div>
                    )}
                </CardHeader>
                <ScrollArea className="flex-1 p-4 bg-muted/10">
                    {messagesLoading ? (
                        <div className="flex justify-center p-8">Loading messages...</div>
                    ) : selectedId ? (
                        <div className="space-y-4 max-w-3xl mx-auto">
                            {messages.map((msg, idx) => (
                                <ChatMessage
                                    key={idx}
                                    role={msg.role}
                                    content={msg.content}
                                    sources={msg.sources} // Assuming API returns sources if stored
                                    // We might need to mock components or pass simplified ones
                                    components={{}} // ChatMessage handles defaults
                                />
                            ))}
                            {messages.length === 0 && (
                                <div className="text-center text-muted-foreground italic">No messages in this conversation.</div>
                            )}
                        </div>
                    ) : (
                        <div className="flex h-full items-center justify-center text-muted-foreground">
                            <div className="text-center">
                                <MessageSquare className="h-12 w-12 mx-auto mb-2 opacity-20" />
                                <p>Select a conversation from the list</p>
                            </div>
                        </div>
                    )}
                </ScrollArea>
            </Card>
        </div>
    )
}
