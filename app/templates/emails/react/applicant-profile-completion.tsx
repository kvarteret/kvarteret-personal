import { Action, DirectLink, EmailLayout, Paragraph } from "./components"
import type { InvitationProps } from "./applicant-invitation"

export default function ProfileCompletion({ invitation_url }: InvitationProps) {
  return <EmailLayout title="Din reise starter nå" heading="Din reise starter nå / Your journey starts now" preview="Prøveperioden din har startet.">
    <Paragraph>Your trial period has now started. Complete your profile to access your temporary staff ID, internal benefits, and relevant information during your trial period.</Paragraph>
    <Paragraph>Din prøveperiode er nå i gang. Fullfør profilen din for å få tilgang til midlertidig internbevis, interne goder og relevant informasjon gjennom prøveperioden.</Paragraph>
    <Paragraph muted>For a valid staff ID or temporary staff ID, complete the form and upload a profile photo.</Paragraph>
    <Paragraph muted>Fullfør skjemaet og last opp et profilbilde for å få et gyldig internbevis eller midlertidig internbevis.</Paragraph>
    <Action href={invitation_url}>Complete your profile / Fullfør profilen din</Action>
    <Paragraph muted>Direct link / Direkte lenke</Paragraph>
    <DirectLink href={invitation_url} />
  </EmailLayout>
}

ProfileCompletion.PreviewProps = { invitation_url: "https://personal.samfunnetibergen.no/apply/preview" } satisfies InvitationProps
