import { test } from "node:test"
import assert from "node:assert/strict"
import { transform } from "./transform.mjs"
import handler from "./api/logs.mjs"
const record = {id:"platform-request",projectId:"prj_vGMyB9GXNJZkwMCNEAJbzmxxCrZD",timestamp:1788545598124,source:"static",proxy:{method:"GET",statusCode:413,path:"/apply/secret-token?email=person@example.com",clientIp:"127.0.0.1"}}
test("platform rejection is structured and token paths are redacted", () => {
 const output = transform([record]); const log=output.resourceLogs[0].scopeLogs[0].logRecords[0]
 assert.equal(log.severityText,"WARN"); assert.equal(log.timeUnixNano,"1788545598124000000")
 assert.ok(log.attributes.some(x=>x.key==="vercel.request.id" && x.value.stringValue==="platform-request"))
 for (const value of ["secret-token","person@example.com","127.0.0.1"]) assert.ok(!JSON.stringify(output).includes(value))
 assert.equal(log.traceId,undefined)
})
test("preserves valid context and safe application fields, never arbitrary extras", () => {
 const output = transform([{...record,projectId:"prj_OHYAWhiMGYIYvZ2UaBqnVSLRRQQi",traceId:"1234567890abcdef1234567890abcdef",spanId:"1234567890abcdef",message:JSON.stringify({event:"booking.failed",registration_id:4,password:"secret"})}])
 const log=output.resourceLogs[0].scopeLogs[0].logRecords[0]
 assert.equal(log.traceId,"1234567890abcdef1234567890abcdef"); assert.equal(log.body.stringValue,"booking.failed")
 assert.ok(!JSON.stringify(output).includes("secret"))
})
test("rejects invalid input and unrelated projects",()=> {
 assert.throws(()=>transform({})); assert.throws(()=>transform([{...record,projectId:"collector"}]))
})
test("authentication and upstream failures are not acknowledged", async()=> {
 process.env.VERCEL_DRAIN_SECRET="test-secret";process.env.POSTHOG_PROJECT_TOKEN="test-token"
 const response={status(code){this.code=code;return this},end(){return this}}
 await handler({method:"POST",headers:{},body:[record]},response);assert.equal(response.code,401)
 const original=globalThis.fetch
 try {
  for (const [upstream, expected] of [[new Response("",{status:500}),502],[new Response(JSON.stringify({partialSuccess:{rejectedLogRecords:1}})),502],[new Response("{}"),204]]) {
   globalThis.fetch=async()=>upstream
   await handler({method:"POST",headers:{authorization:"Bearer test-secret"},body:[record]},response)
   assert.equal(response.code,expected)
  }
 } finally {globalThis.fetch=original;delete process.env.VERCEL_DRAIN_SECRET;delete process.env.POSTHOG_PROJECT_TOKEN}
})
test("Personal drops routine requests, runtime noise and duplicate OTLP events", () => {
 const inputs = [
  {...record, proxy:{statusCode:200}},
  {...record, proxy:{statusCode:303}},
  {...record, proxy:{statusCode:200}, message:"HTTP Request GET /health"},
  {...record, proxy:{statusCode:500}, message:JSON.stringify({event:"http.request.failed",level:"ERROR"})},
  {...record, proxy:{statusCode:200}, message:JSON.stringify({event:"volunteer.lifecycle",level:"INFO"})},
 ]
 assert.deepEqual(transform(inputs),{resourceLogs:[]})
})
test("Personal preserves platform failures and unstructured runtime warnings", () => {
 for (const input of [record, {...record,proxy:{statusCode:500}},
  {...record,proxy:{statusCode:200},level:"error",message:"FUNCTION_INVOCATION_FAILED"}]) {
  assert.equal(transform([input]).resourceLogs.length,1)
 }
})
test("website retains domain outcomes while dropping generic successes", () => {
 const website={...record,projectId:"prj_OHYAWhiMGYIYvZ2UaBqnVSLRRQQi",proxy:{statusCode:200},message:JSON.stringify({event:"booking.completed"})}
 assert.equal(transform([website]).resourceLogs.length,1)
 assert.deepEqual(transform([{...website,message:undefined},{...website,message:"HTTP Request 200"}]),{resourceLogs:[]})
})
test("website structured failures retain severity and session context", () => {
 const website={...record,projectId:"prj_OHYAWhiMGYIYvZ2UaBqnVSLRRQQi",proxy:{statusCode:200},message:JSON.stringify({event:"booking.failed",level:"ERROR",session_id:"session-123",trace_id:"1234567890abcdef1234567890abcdef",span_id:"1234567890abcdef",authorization:"secret"})}
 const log=transform([website]).resourceLogs[0].scopeLogs[0].logRecords[0]
 assert.equal(log.severityText,"ERROR")
 assert.equal(log.traceId,"1234567890abcdef1234567890abcdef")
 assert.ok(log.attributes.some(x=>x.key==="session_id" && x.value.stringValue==="session-123"))
 assert.ok(!JSON.stringify(log).includes("secret"))
 for (const statusCode of [400,401,403,404,429,500,502]) {
  assert.equal(transform([{...website,message:undefined,proxy:{statusCode}}]).resourceLogs.length,1)
 }
})
test("filtered batches are acknowledged without an ingestion request", async () => {
 process.env.VERCEL_DRAIN_SECRET="test-secret";process.env.POSTHOG_PROJECT_TOKEN="test-token"
 const response={status(code){this.code=code;return this},end(){return this}}
 const original=globalThis.fetch
 try {
  globalThis.fetch=async()=>{throw new Error("unexpected export")}
  await handler({method:"POST",headers:{authorization:"Bearer test-secret"},body:[{...record,proxy:{statusCode:200}}]},response)
  assert.equal(response.code,204)
 } finally {globalThis.fetch=original;delete process.env.VERCEL_DRAIN_SECRET;delete process.env.POSTHOG_PROJECT_TOKEN}
})
test("telemetry setup failure retains a platform fallback", () => {
 const output=transform([{...record,proxy:{statusCode:200},message:JSON.stringify({event:"telemetry.configuration.failed",level:"WARNING"})}])
 const log=output.resourceLogs[0].scopeLogs[0].logRecords[0]
 assert.equal(log.body.stringValue,"telemetry.configuration.failed")
 assert.equal(log.severityText,"WARN")
})
