import { EmailLayout, Paragraph } from "./components"

export default function ApplicationReceived() {
  return <EmailLayout title="Den første døren er nå åpen" heading="Den første døren er nå åpen" preview="Vi har mottatt frivilligsøknaden din." lang="nb">
    <Paragraph>Det gleder oss å se at du er interessert i å bli frivillig hos oss på Samfunnet i Bergen. Vi tar kontakt så fort som mulig.</Paragraph>
    <Paragraph>We are delighted that you are interested in becoming a volunteer at Samfunnet i Bergen. We will contact you as soon as possible.</Paragraph>
  </EmailLayout>
}
