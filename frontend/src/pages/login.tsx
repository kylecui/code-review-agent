import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useLogin, useRegister } from '@/hooks/use-auth'
import { cn } from '@/lib/utils'
import { buttonVariants } from '@/components/ui/button'

export function LoginPage() {
  const login = useLogin()
  const register = useRegister()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const isSubmitting = login.isPending || register.isPending
  const isLogin = mode === 'login'

  const handleSubmit: NonNullable<React.ComponentProps<'form'>['onSubmit']> = (event) => {
    event.preventDefault()
    setErrorMessage(null)

    const onError = (error: unknown) => {
      if (error instanceof Error && error.message) {
        setErrorMessage(error.message)
        return
      }
      setErrorMessage(isLogin ? 'Login failed. Please try again.' : 'Registration failed. Please try again.')
    }

    if (isLogin) {
      login.mutate({ email, password }, { onError })
    } else {
      register.mutate(
        { email, password, full_name: fullName || undefined },
        { onError },
      )
    }
  }

  const toggleMode = () => {
    setMode(isLogin ? 'register' : 'login')
    setErrorMessage(null)
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-100 p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-center text-2xl">Agent Review</CardTitle>
          <p className="text-center text-sm text-zinc-500">
            {isLogin ? 'Sign in to your account' : 'Create a new account'}
          </p>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={handleSubmit}>
            {!isLogin && (
              <div className="space-y-2">
                <Label htmlFor="fullName">Full Name</Label>
                <Input
                  id="fullName"
                  type="text"
                  autoComplete="name"
                  placeholder="Optional"
                  value={fullName}
                  onChange={(event) => setFullName(event.target.value)}
                />
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete={isLogin ? 'current-password' : 'new-password'}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </div>

            {errorMessage ? <p className="text-sm text-red-600">{errorMessage}</p> : null}

            <Button type="submit" className="w-full" disabled={isSubmitting}>
              {isSubmitting
                ? (isLogin ? 'Signing In...' : 'Creating Account...')
                : (isLogin ? 'Sign In' : 'Create Account')}
            </Button>

            <div className="flex items-center gap-3 py-1">
              <div className="h-px flex-1 bg-zinc-200" />
              <span className="text-xs uppercase tracking-wide text-zinc-500">or</span>
              <div className="h-px flex-1 bg-zinc-200" />
            </div>

            <a
              href="/api/auth/github/login"
              className={cn(buttonVariants({ variant: 'outline' }), 'w-full')}
            >
              {isLogin ? 'Sign in with GitHub' : 'Sign up with GitHub'}
            </a>

            <p className="text-center text-sm text-zinc-500">
              {isLogin ? "Don't have an account?" : 'Already have an account?'}{' '}
              <button
                type="button"
                className="font-medium text-zinc-900 underline underline-offset-2 hover:text-zinc-700"
                onClick={toggleMode}
              >
                {isLogin ? 'Sign up' : 'Sign in'}
              </button>
            </p>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
