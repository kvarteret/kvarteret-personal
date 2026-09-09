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
 const output = transform([{...record,traceId:"1234567890abcdef1234567890abcdef",spanId:"1234567890abcdef",message:JSON.stringify({event:"booking.failed",registration_id:4,password:"secret"})}])
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
