// Brand fonts are bundled under app/static/email and served on the sending
// domain. Keep font declarations in the email head with web-safe fallbacks.
export const brandFontCss = `@font-face {
  font-family: 'Fraunces';
  font-style: normal;
  font-weight: 400;
  font-display: swap;
  src: url(https://personal.samfunnetibergen.no/static/email/fraunces-400-3eb6cf0a14fe.ttf) format('truetype');
}
@font-face {
  font-family: 'Fraunces';
  font-style: normal;
  font-weight: 600;
  font-display: swap;
  src: url(https://personal.samfunnetibergen.no/static/email/fraunces-600-ff7cf63717c2.ttf) format('truetype');
}
@font-face {
  font-family: 'Fraunces';
  font-style: normal;
  font-weight: 700;
  font-display: swap;
  src: url(https://personal.samfunnetibergen.no/static/email/fraunces-700-f0a9d39b9f14.ttf) format('truetype');
}

@font-face {
  font-family: 'DM Sans';
  font-style: normal;
  font-weight: 400;
  font-display: swap;
  src: url(https://personal.samfunnetibergen.no/static/email/dm-sans-400-b0ae3e89a7d3.ttf) format('truetype');
}
@font-face {
  font-family: 'DM Sans';
  font-style: normal;
  font-weight: 500;
  font-display: swap;
  src: url(https://personal.samfunnetibergen.no/static/email/dm-sans-500-376427b53221.ttf) format('truetype');
}
@font-face {
  font-family: 'DM Sans';
  font-style: normal;
  font-weight: 700;
  font-display: swap;
  src: url(https://personal.samfunnetibergen.no/static/email/dm-sans-700-2a8e7f713ee7.ttf) format('truetype');
}

@font-face {
  font-family: 'DM Mono';
  font-style: normal;
  font-weight: 400;
  font-display: swap;
  src: url(https://personal.samfunnetibergen.no/static/email/dm-mono-400-c97fcd822f82.ttf) format('truetype');
}
@font-face {
  font-family: 'DM Mono';
  font-style: normal;
  font-weight: 500;
  font-display: swap;
  src: url(https://personal.samfunnetibergen.no/static/email/dm-mono-500-dd60d0861a3e.ttf) format('truetype');
}
`
