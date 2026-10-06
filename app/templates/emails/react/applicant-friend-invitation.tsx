import { Action, DirectLink, EmailLayout, Paragraph } from "./components"
import type { InvitationProps } from "./applicant-invitation"

export interface FriendInvitationProps extends InvitationProps { inviter_name: string }

export default function FriendInvitation({ invitation_url, inviter_name }: FriendInvitationProps) {
  return <EmailLayout title="Friend invitation to volunteer at Samfunnet i Bergen" heading="Friend invitation" preview="Apply individually as a volunteer at Samfunnet i Bergen.">
    <Paragraph>{inviter_name} invited you to become a volunteer together at Samfunnet i Bergen.</Paragraph>
    <Paragraph>{inviter_name} har invitert deg til å bli frivillig sammen på Samfunnet i Bergen!</Paragraph>
    <Paragraph>You send your own individual application. Applications are processed separately, while your wish to start together is kept as an informational note. Participation is not binding.</Paragraph>
    <Paragraph>Du sender inn din egen søknad. Søknadene behandles hver for seg, mens ønsket om å begynne sammen beholdes som et informasjonsnotat. Deltakelse er ikke bindende.</Paragraph>
    <Action href={invitation_url}>Apply individually / Søk selv</Action>
    <Paragraph muted>Direct link / Direkte lenke</Paragraph>
    <DirectLink href={invitation_url} />
  </EmailLayout>
}

FriendInvitation.PreviewProps = { invitation_url: "https://personal.samfunnetibergen.no/apply/preview", inviter_name: "Alex" } satisfies FriendInvitationProps
