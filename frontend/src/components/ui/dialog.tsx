import * as React from 'react'

import { cn } from '@/lib/utils'

type DialogContextValue = {
  open: boolean
  setOpen: (open: boolean) => void
}

const DialogContext = React.createContext<DialogContextValue | null>(null)

function useDialogContext() {
  const context = React.useContext(DialogContext)
  if (!context) {
    throw new Error('Dialog components must be used inside <Dialog>')
  }
  return context
}

interface DialogProps {
  open?: boolean
  defaultOpen?: boolean
  onOpenChange?: (open: boolean) => void
  children: React.ReactNode
}

function Dialog({ open: controlledOpen, defaultOpen = false, onOpenChange, children }: DialogProps) {
  const [uncontrolledOpen, setUncontrolledOpen] = React.useState(defaultOpen)
  const isControlled = controlledOpen !== undefined
  const open = isControlled ? controlledOpen : uncontrolledOpen

  const setOpen = React.useCallback(
    (nextOpen: boolean) => {
      if (!isControlled) {
        setUncontrolledOpen(nextOpen)
      }
      onOpenChange?.(nextOpen)
    },
    [isControlled, onOpenChange],
  )

  return <DialogContext.Provider value={{ open, setOpen }}>{children}</DialogContext.Provider>
}

function DialogTrigger({ className, onClick, ...props }: React.ComponentProps<'button'>) {
  const { setOpen } = useDialogContext()

  return (
    <button
      className={className}
      onClick={(event) => {
        onClick?.(event)
        if (!event.defaultPrevented) {
          setOpen(true)
        }
      }}
      {...props}
    />
  )
}

function DialogContent({ className, children, ...props }: React.ComponentProps<'div'>) {
  const { open, setOpen } = useDialogContext()

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-900/40 p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          setOpen(false)
        }
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        className={cn('w-full max-w-lg rounded-lg border border-zinc-200 bg-white p-6 shadow-xl', className)}
        {...props}
      >
        {children}
      </div>
    </div>
  )
}

function DialogHeader({ className, ...props }: React.ComponentProps<'div'>) {
  return <div className={cn('mb-4 flex flex-col space-y-1.5', className)} {...props} />
}

function DialogTitle({ className, ...props }: React.ComponentProps<'h2'>) {
  return <h2 className={cn('text-lg font-semibold leading-none tracking-tight', className)} {...props} />
}

function DialogFooter({ className, ...props }: React.ComponentProps<'div'>) {
  return <div className={cn('mt-6 flex items-center justify-end gap-2', className)} {...props} />
}

export { Dialog, DialogTrigger, DialogContent, DialogHeader, DialogTitle, DialogFooter }
