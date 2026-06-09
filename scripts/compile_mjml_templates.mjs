import { mkdir, readdir, readFile, writeFile } from "node:fs/promises"
import path from "node:path"
import mjml2html from "mjml"

const rootDir = path.resolve("app/templates/emails")
const sourceDir = path.join(rootDir, "mjml")
const outputDir = path.join(rootDir, "compiled")

await mkdir(outputDir, { recursive: true })

for (const entry of await readdir(sourceDir, { withFileTypes: true })) {
  if (!entry.isFile() || !entry.name.endsWith(".mjml")) {
    continue
  }

  const sourcePath = path.join(sourceDir, entry.name)
  const template = await readFile(sourcePath, "utf8")
  const { html, errors } = mjml2html(template, {
    filePath: sourcePath,
    minify: false,
    validationLevel: "strict",
  })

  if (errors.length > 0) {
    throw new Error(
      `MJML compilation failed for ${entry.name}:\n${errors
        .map((error) => error.formattedMessage ?? error.message)
        .join("\n")}`
    )
  }

  const outputName = `${path.basename(entry.name, ".mjml")}.html`
  await writeFile(path.join(outputDir, outputName), normalizeHtml(html), "utf8")
}

function normalizeHtml(html) {
  return `${html
    .split("\n")
    .map((line) => line.trimEnd())
    .join("\n")
    .trimEnd()}\n`
}
