const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
test('HTMX failures are sanitized, GETs do not count, and success resets the form', async () => {
  const listeners = {}, reports = [];
  const form = {action: 'https://personal.kvarteret.no/volunteers/12?csrf_token=private', closest(){return this}};
  const field = {closest(){return form}, matches(){return false}};
  vm.runInNewContext(fs.readFileSync('app/static/js/client-error-reporting.js','utf8'), {
    document:{addEventListener(name, fn){listeners[name] = fn}},
    window:{addEventListener(){}}, location:{origin:'https://personal.kvarteret.no',pathname:'/volunteers'},
    URL, Blob, navigator:{sendBeacon(url, blob){reports.push(blob.text().then(JSON.parse));return true}},
  });
  const ctx = {request:{method:'GET', action:form.action}, response:{status:422}, text:JSON.stringify({detail:[{loc:['query','role_id'],type:'int_parsing',input:'private',msg:'private'}]})};
  for(let n=0;n<3;n++) listeners['htmx:response:error']({target:field,detail:{ctx}});
  ctx.request.method='POST';
  for(let n=0;n<4;n++) listeners['htmx:response:error']({target:form,detail:{ctx}});
  let payloads = await Promise.all(reports);
  assert.equal(payloads.filter(p=>p.error_type==='RepeatedFormSubmissionFailure').length,1);
  assert.equal(payloads.at(-2).validation_fields,'query.role_id');
  assert.equal(JSON.stringify(payloads).includes('private'),false);
  ctx.response.status=200;
  listeners['htmx:after:request']({target:form,detail:{ctx}});
  ctx.response.status=422;
  for(let n=0;n<3;n++) listeners['htmx:response:error']({target:form,detail:{ctx}});
  payloads = await Promise.all(reports);
  assert.equal(payloads.filter(p=>p.error_type==='RepeatedFormSubmissionFailure').length,2);
});
