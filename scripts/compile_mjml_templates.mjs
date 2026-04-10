import fs from "node:fs"
import path from "node:path"
import mjml2html from "mjml"

const rootDir = process.cwd()
const sourceDir = path.join(rootDir, "app", "templates", "emails", "mjml")
const outputDir = path.join(rootDir, "app", "templates", "emails", "compiled")

fs.mkdirSync(outputDir, { recursive: true })

const sourceFiles = fs.readdirSync(sourceDir).filter((entry) => entry.endsWith(".mjml"))
for (const sourceFile of sourceFiles) {
  const sourcePath = path.join(sourceDir, sourceFile)
  const outputPath = path.join(outputDir, sourceFile.replace(/\.mjml$/, ".html"))
  const source = fs.readFileSync(sourcePath, "utf8")
  const result = mjml2html(source, {
    filePath: sourcePath,
    keepComments: false,
    validationLevel: "strict",
  })

  if (result.errors.length > 0) {
    const errorLines = result.errors.map((error) => `${error.formattedMessage ?? error.message}`).join("\n")
    throw new Error(`MJML compilation failed for ${sourceFile}\n${errorLines}`)
  }

  fs.writeFileSync(outputPath, result.html)
}
