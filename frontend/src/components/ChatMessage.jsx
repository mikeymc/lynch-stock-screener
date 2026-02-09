
import { memo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Bot } from 'lucide-react'
import { useAuth } from '@/context/AuthContext'

function SourceCitation({ sources }) {
    const [expanded, setExpanded] = useState(false)

    if (!sources || sources.length === 0) return null

    const sourceLabels = {
        'business': 'Business Description',
        'risk_factors': 'Risk Factors',
        'mda': "Management's Discussion & Analysis",
        'market_risk': 'Market Risk Disclosures'
    }

    return (
        <div className="mt-2 text-xs border-t border-border/50 pt-2">
            <button
                className="flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors font-medium"
                onClick={() => setExpanded(!expanded)}
            >
                📚 Sources ({sources.length}) {expanded ? '▼' : '▶'}
            </button>
            {expanded && (
                <ul className="list-disc list-inside mt-2 pl-1 text-muted-foreground space-y-1">
                    {sources.map((source, idx) => (
                        <li key={idx} className="truncate">{sourceLabels[source] || source}</li>
                    ))}
                </ul>
            )}
        </div>
    )
}

// Memoized ChatMessage component - only re-renders when content changes
const ChatMessage = memo(function ChatMessage({ role, content, sources, components, character }) {
    const { user } = useAuth()
    const isUser = role === 'user'
    const isError = role === 'error'
    const isAssistant = role === 'assistant'

    return (
        <div className={`chat-message flex gap-3 mb-6 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
            {/* Avatar/Icon */}
            <div className="flex-shrink-0 mt-1">
                {isUser ? (
                    <div className="h-8 w-8 rounded-full border border-border overflow-hidden bg-muted">
                        {user?.picture ? (
                            <img src={user.picture} alt="User" className="h-full w-full object-cover" />
                        ) : (
                            <div className="h-full w-full flex items-center justify-center text-xs font-medium text-muted-foreground">
                                {(user?.name?.[0] || user?.email?.[0] || 'U').toUpperCase()}
                            </div>
                        )}
                    </div>
                ) : (
                    <>
                        {/* Character Initials Avatars */}
                        {!isError && character && (character === 'buffett' ? (
                            <div className="h-8 w-8 flex items-center justify-center rounded-lg border border-emerald-200 bg-emerald-100 text-emerald-700 shadow-sm font-bold text-xs dark:bg-emerald-900/50 dark:text-emerald-100 dark:border-emerald-800">
                                WB
                            </div>
                        ) : (
                            <div className="h-8 w-8 flex items-center justify-center rounded-lg border border-blue-200 bg-blue-100 text-blue-700 shadow-sm font-bold text-xs dark:bg-blue-900/50 dark:text-blue-100 dark:border-blue-800">
                                PL
                            </div>
                        ))}

                        {/* Fallback/Error Bot Icon */}
                        {(isError || !character) && (
                            <div className="h-8 w-8 flex items-center justify-center rounded-lg border border-border bg-background shadow-sm">
                                {isError ? (
                                    <div className="text-destructive font-bold">!</div>
                                ) : (
                                    <Bot className="h-5 w-5 text-primary" />
                                )}
                            </div>
                        )}
                    </>
                )}
            </div>

            {/* Message Bubble */}
            <div className={`flex flex-col max-w-[85%] min-w-0 ${isUser ? 'items-end' : 'items-start'}`}>
                <div className={`rounded-lg px-4 py-3 ${isUser
                    ? 'bg-primary text-primary-foreground user-message'
                    : isError
                        ? 'bg-destructive/10 text-destructive border border-destructive/20'
                        : 'bg-muted'
                    }`}>
                    <div className="text-sm break-words">
                        <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
                            {content}
                        </ReactMarkdown>
                    </div>
                    {isAssistant && <SourceCitation sources={sources} />}
                </div>
            </div>
        </div>
    )
})

export default ChatMessage
