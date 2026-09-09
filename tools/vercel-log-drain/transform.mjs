// Only the two source applications are accepted. The collector is never a source.
const services = {
  prj_vGMyB9GXNJZkwMCNEAJbzmxxCrZD: "kvarteret-personal-platform",
  prj_OHYAWhiMGYIYvZ2UaBqnVSLRRQQi: "samfunnetibergen-platform",
}
const safeFields = new Set([
  "event", "request_id", "registration_id", "booking_submission_id", "outcome",
  "status", "status_code", "duration_ms", "http_method", "route_template",
  "error_category", "failure_stage", "operation", "count", "attempt_no",
  "logger", "trace_id", "span_id", "origin_trace_id", "crescat_http_status",
])
export function redact(value) {
  return String(value).replace(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi, "[redacted-email]")
    .replace(/\bbearer\s+[^\s"']+/gi, "Bearer [redacted]")
    .replace(/\?[^\s"']*/g, "?[redacted]")
    .replace(/(\/(?:apply|set-password)\/)[^/?#\s"']+/gi, "$1[redacted]")
    .slice(0, 2048)
}
const attributes = fields => Object.entries(fields)
  .filter(([, v]) => v !== undefined && v !== null)
  .map(([key, value]) => ({key, value: typeof value === "number" ? {doubleValue: value}
    : typeof value === "boolean" ? {boolValue: value} : {stringValue: redact(value)}}))
function validId(value, length) {
  return typeof value === "string" && new RegExp(`^[a-f0-9]{${length}}$`, "i").test(value)
    && !/^0+$/.test(value) ? value.toLowerCase() : undefined
}
export function transform(records) {
  if (!Array.isArray(records) || records.length > 10000) throw new Error("Invalid batch")
  return { resourceLogs: records.map(record => {
    if (!record || typeof record !== "object" || !services[record.projectId]
      || !Number.isSafeInteger(record.timestamp) || record.timestamp < 0) {
      throw new Error("Invalid record")
    }
    const proxy = record.proxy || {}
    const status = proxy.statusCode ?? record.statusCode
    const severity = status >= 500 ? "ERROR" : status >= 400 ? "WARN"
      : ({fatal:"FATAL",error:"ERROR",warning:"WARN",warn:"WARN",debug:"DEBUG",trace:"TRACE"}[record.level] || "INFO")
    let parsed = {}
    try { const v = JSON.parse(record.message); if (v && typeof v === "object" && !Array.isArray(v)) parsed = v } catch {}
    const fields = Object.fromEntries(Object.entries(parsed).filter(([key, value]) =>
      safeFields.has(key) && ["string", "number", "boolean"].includes(typeof value)))
    // Never export arbitrary console text: it may include names, bodies or secrets.
    // Keep safe exception types/codes and application fields as searchable attributes.
    const message = typeof record.message === "string" ? record.message : ""
    const errorCode = message.match(/\b(?:E[A-Z_]{3,40}|UND_ERR_[A-Z_]+|FUNCTION_[A-Z_]+)\b/)?.[0]
    const errorType = message.match(/\b(?:TypeError|ReferenceError|SyntaxError|TimeoutError|RuntimeError)\b/)?.[0]
    const event = typeof fields.event === "string" ? fields.event : message ? "vercel.runtime.log" : "vercel.request.completed"
    const log = {
      timeUnixNano: (BigInt(record.timestamp) * 1000000n).toString(),
      severityText: severity,
      severityNumber: {TRACE:1,DEBUG:5,INFO:9,WARN:13,ERROR:17,FATAL:21}[severity],
      body: {stringValue:redact(event)},
      attributes: attributes({
        ...fields, event, "log.source":"vercel", "vercel.source":record.source,
        "vercel.log.id":record.id, "vercel.request.id":record.requestId ?? proxy.requestId ?? record.id,
        "http.request.method":proxy.method ?? record.method,
        "http.response.status_code":status,
        "url.path":record.path ?? proxy.path,
        "server.address":proxy.host ?? record.host,
        "vercel.path_type":proxy.pathType, "error.code":errorCode, "error.type":errorType,
        "http.response.body.size":proxy.responseByteSize,
      }),
      traceId:validId(record.traceId ?? record["trace.id"] ?? fields.trace_id,32),
      spanId:validId(record.spanId ?? record["span.id"] ?? fields.span_id,16),
    }
    return {
      resource:{attributes:attributes({"service.name":services[record.projectId],
        "deployment.environment.name":record.environment,"vercel.project.id":record.projectId,
        "vercel.deployment.id":record.deploymentId,"cloud.region":record.executionRegion ?? proxy.region})},
      scopeLogs:[{scope:{name:"vercel-log-drain"},logRecords:[log]}],
    }
  })}
}
