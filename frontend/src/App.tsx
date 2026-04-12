import { List, Settings, Shield, Users } from 'lucide-react'

const navItems = [
  { label: 'Scans', icon: List },
  { label: 'Settings', icon: Settings },
  { label: 'Policies', icon: Shield },
  { label: 'Users', icon: Users },
]

export default function App() {
  return (
    <div className="flex min-h-screen bg-zinc-100 text-zinc-900">
      <aside className="w-64 bg-zinc-900 text-white">
        <div className="border-b border-zinc-800 px-6 py-5">
          <h1 className="text-lg font-semibold tracking-wide">Agent Review</h1>
        </div>
        <nav className="px-3 py-4">
          <ul className="space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon
              return (
                <li key={item.label}>
                  <button
                    type="button"
                    className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-sm text-zinc-200 transition-colors hover:bg-zinc-800 hover:text-white"
                  >
                    <Icon className="h-4 w-4" />
                    <span>{item.label}</span>
                  </button>
                </li>
              )
            })}
          </ul>
        </nav>
      </aside>

      <main className="flex flex-1 items-center justify-center p-8">
        <p className="text-zinc-600">Select a page from the sidebar</p>
      </main>
    </div>
  )
}
