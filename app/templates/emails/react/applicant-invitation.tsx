import { Action, DirectLink, EmailLayout, Paragraph } from "./components"

export interface InvitationProps { invitation_url: string }

export default function ApplicantInvitation({ invitation_url }: InvitationProps) {
  return <EmailLayout title="Complete your Samfunnet i Bergen registration" heading="Complete your registration" preview="Complete your registration in Samfunnet i Bergen.">
    <Paragraph>You have been invited to complete your volunteer registration for Samfunnet i Bergen.</Paragraph>
    <Paragraph>Du er invitert til å fullføre frivilligregistreringen din for Samfunnet i Bergen.</Paragraph>
    <Action href={invitation_url}>Complete your details / Fullfør detaljene dine</Action>
    <Paragraph muted>Direct link / Direkte lenke</Paragraph>
    <DirectLink href={invitation_url} />
  </EmailLayout>
}

ApplicantInvitation.PreviewProps = { invitation_url: "https://personal.samfunnetibergen.no/apply/preview" } satisfies InvitationProps
