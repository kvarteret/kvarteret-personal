import { AccessCode, EmailLayout, Paragraph } from "./components"

export interface AccessCodeProps { access_code: string; expires_in_minutes: number | string }

export default function MobileCardAccessCode({ access_code, expires_in_minutes }: AccessCodeProps) {
  return <EmailLayout lang="nb" title="Din innlogging til Personal er klar" heading="Din innlogging til Personal er klar" preview="Bruk koden for å logge inn i Personal.">
    <Paragraph>Bruk denne koden for å logge inn i Personal.</Paragraph>
    <AccessCode>{access_code}</AccessCode>
    <Paragraph>Koden er gyldig i {expires_in_minutes} minutter.</Paragraph>
    <Paragraph muted>Hvis du ikke ba om koden, kan du se bort fra denne e-posten.</Paragraph>
  </EmailLayout>
}

MobileCardAccessCode.PreviewProps = { access_code: "123456", expires_in_minutes: 10 } satisfies AccessCodeProps
