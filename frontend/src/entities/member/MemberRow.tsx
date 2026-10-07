import type { ReactNode } from 'react'

import type { Member } from './model'

/** Name and username on the left; roles or actions on the right. */
export function MemberRow({ member, children }: { member: Member; children?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 py-3">
      <div className="grid">
        <span className="font-medium">{member.display_name}</span>
        <span className="text-sm text-muted-foreground">@{member.username}</span>
      </div>
      <div className="flex flex-wrap items-center gap-3">{children}</div>
    </div>
  )
}
