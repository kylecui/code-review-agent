import { List, LogOut, Settings, Shield, Users } from 'lucide-react'

import { cn } from '@/lib/utils'

interface SidebarProps {
  user: {
    email: string
    full_name: string | null
    is_superuser: boolean
  }
  activePage: string
  onNavigate: (page: string) => void
  onLogout: () => void
}

export function Sidebar({ user, activePage, onNavigate, onLogout }: SidebarProps) {
  const navItems = [
    { id: 'scans', label: 'Scans', icon: List, adminOnly: false },
    { id: 'settings', label: 'Settings', icon: Settings, adminOnly: true },
    { id: 'policies', label: 'Policies', icon: Shield, adminOnly: true },
    { id: 'users', label: 'Users', icon: Users, adminOnly: true },
  ]

  const visibleItems = navItems.filter((item) => !item.adminOnly || user.is_superuser)

  return (
    <aside className="flex w-64 flex-col bg-zinc-900 text-white">
      <div className="border-b border-zinc-800 px-6 py-5">
        <h1 className="text-lg font-semibold tracking-wide">Agent Review</h1>
      </div>
      <nav className="flex-1 px-3 py-4">
        <ul className="space-y-1">
          {visibleItems.map((item) => {
            const Icon = item.icon
            const isActive = activePage === item.id
            return (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => onNavigate(item.id)}
                  className={cn(
                    'flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-sm transition-colors',
                    isActive
                      ? 'bg-zinc-800 text-white'
                      : 'text-zinc-400 hover:bg-zinc-800 hover:text-white',
                  )}
                >
                  <Icon className="h-4 w-4" />
                  <span>{item.label}</span>
                </button>
              </li>
            )
          })}
        </ul>
      </nav>
      <div className="border-t border-zinc-800 px-3 py-4">
        <div className="mb-2 truncate px-3 text-xs text-zinc-500">{user.full_name || user.email}</div>
        <button
          type="button"
          onClick={onLogout}
          className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-sm text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-white"
        >
          <LogOut className="h-4 w-4" />
          <span>Sign Out</span>
        </button>
      </div>
    </aside>
  )
}
