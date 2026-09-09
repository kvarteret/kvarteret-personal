import { timingSafeEqual } from "node:crypto"
import { transform } from "../transform.mjs"

export default async function handler(request, response) {
  if (request.method !== "POST") return response.status(405).end()
  const secret = process.env.VERCEL_DRAIN_SECRET
  const token = process.env.POSTHOG_PROJECT_TOKEN
  if (!secret || !token) return response.status(503).end()
  const supplied = Buffer.from(request.headers.authorization || "")
  const expected = Buffer.from(`Bearer ${secret}`)
  if (supplied.length !== expected.length || !timingSafeEqual(supplied, expected)) {
    return response.status(401).end()
  }
  let payload
  try {
    let body = request.body
    if (body === undefined) {
      const chunks = []
      let size = 0
      for await (const chunk of request) {
        size += chunk.length
        if (size > 4 * 1024 * 1024) return response.status(413).end()
        chunks.push(chunk)
      }
      body = Buffer.concat(chunks).toString("utf8")
    }
    if (typeof body === "string" || Buffer.isBuffer(body)) body = JSON.parse(body.toString())
    payload = transform(body)
  } catch { return response.status(400).end() }
  if (!payload.resourceLogs.length) return response.status(204).end()
  try {
    // Chunk transformed records to stay below ingestion payload limits.
    for (let i = 0; i < payload.resourceLogs.length; i += 100) {
      const result = await fetch("https://eu.i.posthog.com/i/v1/logs", {
        method:"POST", headers:{Authorization:`Bearer ${token}`, "Content-Type":"application/json"},
        body:JSON.stringify({resourceLogs:payload.resourceLogs.slice(i,i+100)}),
        signal:AbortSignal.timeout(15000),
      })
      if (!result.ok) return response.status(502).end()
      const text = await result.text()
      if (text && Number(JSON.parse(text).partialSuccess?.rejectedLogRecords || 0) > 0) {
        return response.status(502).end()
      }
    }
    return response.status(204).end()
  } catch { return response.status(502).end() }
}
