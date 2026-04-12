import { useMemo, useState } from 'react'
import { Link as LinkIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useCreateUser, useDeactivateUser, useUpdateUser, useUsers } from '@/hooks/use-users'
import type { UserRead } from '@/lib/api'
import { cn } from '@/lib/utils'

interface UsersPageProps {
  currentUserId: string
}

function roleBadgeClass(isSuperuser: boolean) {
  return isSuperuser
    ? 'bg-indigo-100 text-indigo-800 border-indigo-200'
    : 'bg-zinc-100 text-zinc-700 border-zinc-200'
}

function statusBadgeClass(isActive: boolean) {
  return isActive
    ? 'bg-emerald-100 text-emerald-800 border-emerald-200'
    : 'bg-zinc-100 text-zinc-700 border-zinc-200'
}

function CreateUserDialog() {
  const createUser = useCreateUser()
  const [open, setOpen] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [isSuperuser, setIsSuperuser] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleCreate = () => {
    setError(null)
    createUser.mutate(
      {
        email,
        password,
        full_name: fullName || undefined,
        is_superuser: isSuperuser,
      },
      {
        onSuccess: () => {
          setOpen(false)
          setEmail('')
          setPassword('')
          setFullName('')
          setIsSuperuser(false)
        },
        onError: (mutationError) => {
          if (mutationError instanceof Error) {
            setError(mutationError.message)
          } else {
            setError('Failed to create user')
          }
        },
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger className={cn(buttonVariants({ variant: 'default' }))}>Create User</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create User</DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <Input placeholder="Email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
          <Input
            placeholder="Password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <Input placeholder="Full Name" value={fullName} onChange={(event) => setFullName(event.target.value)} />
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={isSuperuser}
              onChange={(event) => setIsSuperuser(event.target.checked)}
            />
            Is superuser
          </label>
          {error ? <p className="text-sm text-red-600">{error}</p> : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleCreate}
            disabled={createUser.isPending || !email.trim() || !password.trim()}
          >
            {createUser.isPending ? 'Creating…' : 'Create'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function EditableUserRow({ user, currentUserId }: { user: UserRead; currentUserId: string }) {
  const updateUser = useUpdateUser()
  const deactivateUser = useDeactivateUser()

  const [fullName, setFullName] = useState(user.full_name ?? '')
  const isSelf = user.id === currentUserId

  return (
    <TableRow>
      <TableCell className="font-medium">{user.email}</TableCell>
      <TableCell>
        <Input value={fullName} onChange={(event) => setFullName(event.target.value)} className="h-8" />
      </TableCell>
      <TableCell>
        <Badge className={roleBadgeClass(user.is_superuser)}>{user.is_superuser ? 'admin' : 'viewer'}</Badge>
      </TableCell>
      <TableCell>
        <Badge className={statusBadgeClass(user.is_active)}>{user.is_active ? 'active' : 'inactive'}</Badge>
      </TableCell>
      <TableCell>
        {user.github_login ? (
          <span className="inline-flex items-center gap-1 text-sm text-zinc-700">
            <LinkIcon className="h-3.5 w-3.5" />
            {user.github_login}
          </span>
        ) : (
          '—'
        )}
      </TableCell>
      <TableCell>
        <div className="flex flex-wrap justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              updateUser.mutate({
                userId: user.id,
                body: {
                  full_name: fullName || null,
                },
              })
            }
          >
            Save Name
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={isSelf}
            onClick={() =>
              updateUser.mutate({
                userId: user.id,
                body: { is_superuser: !user.is_superuser },
              })
            }
          >
            {user.is_superuser ? 'Make Viewer' : 'Make Admin'}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              updateUser.mutate({
                userId: user.id,
                body: { is_active: !user.is_active },
              })
            }
            disabled={isSelf}
          >
            {user.is_active ? 'Deactivate' : 'Activate'}
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={() => deactivateUser.mutate(user.id)}
            disabled={isSelf || deactivateUser.isPending}
          >
            Deactivate
          </Button>
        </div>
      </TableCell>
    </TableRow>
  )
}

export function UsersPage({ currentUserId }: UsersPageProps) {
  const usersQuery = useUsers()

  const users = useMemo(() => usersQuery.data ?? [], [usersQuery.data])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-semibold tracking-tight">User Management</h2>
        <CreateUserDialog />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Users</CardTitle>
        </CardHeader>
        <CardContent>
          {usersQuery.isLoading ? <p className="text-sm text-zinc-500">Loading users…</p> : null}
          {usersQuery.isError ? <p className="text-sm text-red-600">Failed to load users.</p> : null}

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Email</TableHead>
                <TableHead>Full Name</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>GitHub</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.map((user) => (
                <EditableUserRow key={user.id} user={user} currentUserId={currentUserId} />
              ))}
              {users.length === 0 && !usersQuery.isLoading ? (
                <TableRow>
                  <TableCell colSpan={6} className="py-6 text-center text-zinc-500">
                    No users found.
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
