// The members block on the workspace page: who is here, their roles, and
// the controls the current user may use.
import { useTranslation } from 'react-i18next'

import { MemberRow, useMembers } from '@/entities/member'
import { useSession } from '@/entities/session'
import { EXTRA_ROLES, workspaceRights, type Workspace } from '@/entities/workspace'
import { AddMemberForm } from '@/features/member-add'
import { RemoveMemberButton, RoleCheckbox } from '@/features/member-manage'
import { errorText } from '@/shared/api'
import { Badge, Card, CardContent, CardHeader, CardTitle, FormError } from '@/shared/ui'

export function WorkspaceMembers({ workspace }: { workspace: Workspace }) {
  const { t } = useTranslation()
  const { me } = useSession()
  const rights = workspaceRights(workspace)
  const canSee = rights.seeInside || Boolean(me?.is_admin)
  const members = useMembers(workspace.id, canSee)
  if (!canSee) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          {t('members.title')}
          {members.data && <span className="ml-2 text-muted-foreground">{members.data.length}</span>}
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4">
        {rights.addMembers && <AddMemberForm workspaceId={workspace.id} />}
        {members.isPending && <p className="text-muted-foreground">{t('common.loading')}</p>}
        {members.isError && <FormError error={errorText(members.error)} />}
        {members.data?.length === 0 && <p className="text-muted-foreground">{t('members.empty')}</p>}
        <ul className="divide-y divide-border">
          {members.data?.map((member) => (
            <li key={member.user_id}>
              <MemberRow member={member}>
                {EXTRA_ROLES.map((role) =>
                  rights.manageRole(role) ? (
                    <RoleCheckbox key={role} workspaceId={workspace.id} member={member} role={role} />
                  ) : (
                    member.roles.includes(role) && (
                      <Badge key={role} variant="secondary">
                        {t(`roles.${role}`)}
                      </Badge>
                    )
                  ),
                )}
                {rights.removeMembers && <RemoveMemberButton workspaceId={workspace.id} member={member} />}
              </MemberRow>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}
