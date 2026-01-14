// ABOUTME: Chat history sidebar component for agent mode
// ABOUTME: Displays list of conversations with selection and delete functionality

import { Trash2 } from 'lucide-react'
import { useChatContext } from '@/context/ChatContext'
import {
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
} from '@/components/ui/sidebar'

export default function ChatHistory({ onSelectConversation, onDeleteConversation }) {
  const {
    conversations,
    activeConversationId,
    setActiveConversationId
  } = useChatContext()

  const handleSelect = (conversationId) => {
    setActiveConversationId(conversationId)
    if (onSelectConversation) {
      onSelectConversation(conversationId)
    }
  }

  const handleDelete = (e, conversationId) => {
    e.stopPropagation()
    if (onDeleteConversation) {
      onDeleteConversation(conversationId)
    }
  }

  // Truncate title to prevent layout issues
  const truncateTitle = (title) => {
    if (!title) return 'New Chat'
    return title.length > 25 ? title.substring(0, 25) + '...' : title
  }

  if (!conversations) {
    return null
  }

  if (conversations.length === 0) {
    return (
      <div className="pl-6 py-2 text-sm text-muted-foreground">
        No conversations yet
      </div>
    )
  }

  return (
    <div className="w-full" style={{ maxWidth: '100%', overflow: 'hidden' }}>
      <SidebarMenu>
        {conversations.map((conv) => (
          <SidebarMenuItem key={conv.id} className="group">
            <SidebarMenuButton
              onClick={() => handleSelect(conv.id)}
              isActive={activeConversationId === conv.id}
              className="pl-6 font-normal text-muted-foreground data-[active=true]:font-medium data-[active=true]:text-sidebar-primary"
              title={conv.title || 'New Chat'}
            >
              <span className="flex-1 truncate min-w-0">{truncateTitle(conv.title)}</span>
            </SidebarMenuButton>
            {onDeleteConversation && (
              <button
                className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:text-destructive"
                onClick={(e) => handleDelete(e, conv.id)}
              >
                <Trash2 className="h-3 w-3" />
              </button>
            )}
          </SidebarMenuItem>
        ))}
      </SidebarMenu>
    </div>
  )
}
