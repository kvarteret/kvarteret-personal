import { Action, DirectLink, EmailLayout, Paragraph } from "./components"

export interface PasswordResetProps { setup_url: string }

export default function PasswordReset({ setup_url }: PasswordResetProps) {
  return <EmailLayout title="Tilbakestill passord" heading="Tilbakestill passord" lang="nb">
    <Paragraph>Vi har mottatt en forespørsel om å velge et nytt passord for kontoen din hos Samfunnet i Bergen.</Paragraph>
    <Action href={setup_url}>Velg nytt passord</Action>
    <Paragraph>Hvis du ikke ba om dette, kan du se bort fra e-posten. Passordet ditt blir ikke endret.</Paragraph>
    <Paragraph>Hvis knappen ikke virker, åpne denne lenken direkte:</Paragraph>
    <DirectLink href={setup_url} />
  </EmailLayout>
}

PasswordReset.PreviewProps = { setup_url: "https://personal.samfunnetibergen.no/account-setup/preview" } satisfies PasswordResetProps
