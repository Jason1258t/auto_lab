// The members block on the workspace page: who is here, their roles, and
// the controls the current user may use.
import { useTranslation } from 'react-i18next'

import { MemberRow, useMembers } from '@/entities/member'
import { EXTRA_ROLES, workspaceRights, type Workspace } from '@/entities/workspace'
import { AddMemberForm } from '@/features/member-add'
import { RemoveMemberButton, RoleCheckbox } from '@/features/member-manage'
import { errorText } from '@/shared/api'
import { Badge, Card, CardContent, CardHeader, CardTitle, FormError } from '@/shared/ui'

export function WorkspaceMembers({ workspace }: { workspace: Workspace }) {
  const { t } = useTranslation()
  const rights = workspaceRights(workspace)
  const members = useMembers(workspace.id)

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('members.title')}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4">
        {rights.addMembers && <AddMemberForm workspaceId={workspace.id} />}
        {members.isPending && <p className="text-muted-foreground">{t('common.loading')}</p>}
        {members.isError && <FormError error={errorText(members.error)} />}
        <ul className="divide-y divide-border">
          {workspace.owner_id !== null && workspace.owner_username && (
            <li>
              <MemberRow
                member={{
                  user_id: workspace.owner_id,
                  username: workspace.owner_username,
                  display_name: workspace.owner_display_name ?? workspace.owner_username,
                  roles: [],
                }}
              >
                <Badge>{t('workspaces.owner')}</Badge>
              </MemberRow>
            </li>
          )}
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
