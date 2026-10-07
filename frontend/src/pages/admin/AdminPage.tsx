// Admin tools: models and providers, the global activity log, admin
// rights. The backend checks admin rights on every call; this page only
// hides itself from others.
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router'

import { ActivityLine } from '@/entities/activity'
import { useAdminModels, useGlobalActivity, useProviders } from '@/entities/admin'
import { useSession } from '@/entities/session'
import { AdminRights } from '@/features/admin-admins'
import { AddModelButton, AvailableCheckbox } from '@/features/admin-models'
import { AddProviderButton } from '@/features/admin-providers'
import { errorText } from '@/shared/api'
import { Card, CardContent, CardHeader, CardTitle, FormError, Tabs, TabsContent, TabsList, TabsTrigger } from '@/shared/ui'

const TABS = ['models', 'providers', 'activity', 'admins'] as const
type Tab = (typeof TABS)[number]

function ModelsTab() {
  const { t } = useTranslation()
  const models = useAdminModels()
  const providers = useProviders()
  const providerName = (id: number) => providers.data?.find((p) => p.id === id)?.name ?? `#${id}`
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('admin.tabs.models')}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4">
        <p className="text-sm text-muted-foreground">{t('admin.modelsText')}</p>
        <div>
          <AddModelButton providers={providers.data ?? []} />
        </div>
        {models.isError && <FormError error={errorText(models.error)} />}
        {models.data?.length === 0 && <p className="text-muted-foreground">{t('admin.noModels')}</p>}
        <ul className="divide-y divide-border">
          {models.data?.map((model) => (
            <li key={model.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
              <div className="grid">
                <span className="font-medium">{model.name}</span>
                <span className="text-sm text-muted-foreground">
                  {providerName(model.provider_id)} · {t('admin.contextShort', { n: model.context_length })}
                  {model.vram_mb !== null && ` · ${model.vram_mb} MB VRAM`}
                </span>
                {model.description && <span className="text-sm text-muted-foreground">{model.description}</span>}
              </div>
              <AvailableCheckbox model={model} />
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}

function ProvidersTab() {
  const { t } = useTranslation()
  const providers = useProviders()
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('admin.tabs.providers')}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div>
          <AddProviderButton />
        </div>
        {providers.isError && <FormError error={errorText(providers.error)} />}
        <ul className="divide-y divide-border">
          {providers.data?.map((p) => (
            <li key={p.id} className="grid py-3">
              <span className="font-medium">{p.name}</span>
              <span className="text-sm text-muted-foreground">
                {p.adapter}
                {p.base_url && ` · ${p.base_url}`}
              </span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}

function ActivityTab() {
  const { t } = useTranslation()
  const events = useGlobalActivity()
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('admin.tabs.activity')}</CardTitle>
      </CardHeader>
      <CardContent>
        {events.isError && <FormError error={errorText(events.error)} />}
        {events.data?.length === 0 && <p className="text-muted-foreground">{t('activity.empty')}</p>}
        <ul className="divide-y divide-border text-sm">
          {events.data?.map((event) => (
            <li key={event.id}>
              <ActivityLine event={event} />
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}

export function AdminPage() {
  const { t } = useTranslation()
  const { me } = useSession()
  const [params, setParams] = useSearchParams()
  if (!me?.is_admin) return <p className="text-muted-foreground">{t('admin.onlyAdmins')}</p>
  const tab: Tab = TABS.find((name) => name === params.get('tab')) ?? 'models'
  const panels: Record<Tab, ReactNode> = {
    models: <ModelsTab />,
    providers: <ProvidersTab />,
    activity: <ActivityTab />,
    admins: (
      <Card>
        <CardHeader>
          <CardTitle>{t('admin.tabs.admins')}</CardTitle>
        </CardHeader>
        <CardContent>
          <AdminRights />
        </CardContent>
      </Card>
    ),
  }
  return (
    <section className="grid gap-6">
      <h1 className="font-heading text-3xl font-semibold">{t('admin.title')}</h1>
      <Tabs value={tab} onValueChange={(v) => setParams(v === 'models' ? {} : { tab: String(v) }, { replace: true })} className="gap-4">
        <TabsList>
          {TABS.map((name) => (
            <TabsTrigger key={name} value={name}>
              {t(`admin.tabs.${name}`)}
            </TabsTrigger>
          ))}
        </TabsList>
        {TABS.map((name) => (
          <TabsContent key={name} value={name}>
            {panels[name]}
          </TabsContent>
        ))}
      </Tabs>
    </section>
  )
}
