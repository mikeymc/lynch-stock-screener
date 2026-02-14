
import { Outlet, useLocation, useNavigate, Link } from 'react-router-dom'
import {
    Sidebar,
    SidebarContent,
    SidebarFooter,
    SidebarHeader,
    SidebarInset,
    SidebarMenu,
    SidebarMenuButton,
    SidebarMenuItem,
    SidebarProvider,
    SidebarRail,
} from '@/components/ui/sidebar'
import {
    LayoutDashboard,
    MessageSquare,
    Briefcase,
    Layers,
    Activity,
    LogOut,
    ChevronLeft,
    BarChart3,
    Megaphone
} from 'lucide-react'
import UserAvatar from '@/components/UserAvatar'

export default function AdminLayout() {
    const location = useLocation()
    const navigate = useNavigate()

    const isActive = (path) => location.pathname === path

    const menuItems = [
        { name: 'Job Stats', path: '/admin', icon: BarChart3 },
        { name: 'Conversations', path: '/admin/conversations', icon: MessageSquare },
        { name: 'Strategies', path: '/admin/strategies', icon: Layers },
        { name: 'Portfolios', path: '/admin/portfolios', icon: Briefcase },
        { name: 'User Actions', path: '/admin/user_actions', icon: Activity },
        { name: 'Feedback', path: '/admin/feedback', icon: Megaphone },
    ]

    return (
        <SidebarProvider>
            <div className="flex h-screen w-full overflow-hidden bg-background">
                <Sidebar className="border-r">
                    <SidebarHeader className="border-b h-14 flex items-center px-4">
                        <div className="flex items-center gap-2 font-semibold text-lg">
                            <span className="text-primary">Admin</span>
                            <span>Panel</span>
                        </div>
                    </SidebarHeader>

                    <SidebarContent>
                        <SidebarMenu className="px-2 py-4">
                            {menuItems.map((item) => (
                                <SidebarMenuItem key={item.path}>
                                    <SidebarMenuButton
                                        onClick={() => navigate(item.path)}
                                        isActive={isActive(item.path)}
                                        tooltip={item.name}
                                    >
                                        <item.icon className="h-4 w-4" />
                                        <span>{item.name}</span>
                                    </SidebarMenuButton>
                                </SidebarMenuItem>
                            ))}
                        </SidebarMenu>
                    </SidebarContent>

                    <SidebarFooter className="border-t p-2">
                        <SidebarMenu>
                            <SidebarMenuItem>
                                <SidebarMenuButton asChild>
                                    <Link to="/dashboard">
                                        <ChevronLeft className="h-4 w-4" />
                                        <span>Back to App</span>
                                    </Link>
                                </SidebarMenuButton>
                            </SidebarMenuItem>
                        </SidebarMenu>
                    </SidebarFooter>
                    <SidebarRail />
                </Sidebar>

                <SidebarInset className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
                    <header className="flex h-14 items-center justify-between border-b px-6 shrink-0 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
                        <div className="font-medium text-lg">
                            {menuItems.find(i => isActive(i.path))?.name || 'Admin'}
                        </div>
                        <div className="flex items-center gap-4">
                            <UserAvatar />
                        </div>
                    </header>

                    <main className="flex-1 overflow-auto p-6">
                        <Outlet />
                    </main>
                </SidebarInset>
            </div>
        </SidebarProvider>
    )
}
