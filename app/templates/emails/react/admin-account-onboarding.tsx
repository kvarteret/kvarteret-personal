import { Action, DirectLink, EmailLayout, Paragraph } from "./components"

export interface OnboardingProps { setup_url: string; display_name?: string; username: string; role_name: string }

export default function AdminOnboarding({ setup_url, display_name, username, role_name }: OnboardingProps) {
  return <EmailLayout title="Samfunnet i Bergen admin account" heading="Samfunnet i Bergen admin">
    <Paragraph>A new admin account has been prepared for you.</Paragraph>
    <Paragraph>Hei{display_name ? <> {display_name}</> : null},</Paragraph>
    <Paragraph>Your Samfunnet i Bergen account is ready. Use the button below to set your password and activate access.</Paragraph>
    <Paragraph>Kontoen din hos Samfunnet i Bergen er klar. Bruk knappen under for å sette passord og aktivere tilgangen.</Paragraph>
    <Action href={setup_url}>Set password / Sett passord</Action>
    <Paragraph>Username: <strong>{username}</strong><br />Role: <strong>{role_name}</strong></Paragraph>
    <Paragraph>If the button does not work, open this link directly:</Paragraph>
    <DirectLink href={setup_url} />
  </EmailLayout>
}

AdminOnboarding.PreviewProps = { setup_url: "https://personal.samfunnetibergen.no/account-setup/preview", display_name: "Alex", username: "alex", role_name: "Admin" } satisfies OnboardingProps
