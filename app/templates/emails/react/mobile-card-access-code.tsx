import { AccessCode, EmailLayout, Paragraph } from "./components"

export interface AccessCodeProps { access_code: string; expires_in_minutes: number | string }

export default function MobileCardAccessCode({ access_code, expires_in_minutes }: AccessCodeProps) {
  return <EmailLayout title="Samfunnet i Bergen Internkort" heading="Your verification code" preview="Your Samfunnet i Bergen verification code is ready.">
    <Paragraph>Use this code to sign in to Samfunnet i Bergen Internkort.</Paragraph>
    <AccessCode>{access_code}</AccessCode>
    <Paragraph>This code expires in {expires_in_minutes} minutes.</Paragraph>
    <Paragraph muted>If you did not request this code, you can ignore this email.</Paragraph>
  </EmailLayout>
}

MobileCardAccessCode.PreviewProps = { access_code: "123456", expires_in_minutes: 10 } satisfies AccessCodeProps
