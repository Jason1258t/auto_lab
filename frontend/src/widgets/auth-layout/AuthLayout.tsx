import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { ThemeToggle } from '@/features/theme-toggle'
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/ui'

/** The frame of the login and signup pages. */
export function AuthLayout({ title, children }: { title: string; children: ReactNode }) {
  const { t } = useTranslation()
  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-6 bg-background px-4">
      <div className="absolute top-3 right-3">
        <ThemeToggle />
      </div>
      <div className="text-center">
        <h1 className="font-heading text-4xl font-semibold">{t('app.name')}</h1>
        <p className="mt-2 text-muted-foreground">{t('app.tagline')}</p>
      </div>
      <Card className="w-full max-w-sm">
        <CardHeader>
          {/* CardTitle is a div; the page title must be a real heading. */}
          <CardTitle>
            <h2>{title}</h2>
          </CardTitle>
        </CardHeader>
        <CardContent>{children}</CardContent>
      </Card>
    </div>
  )
}
