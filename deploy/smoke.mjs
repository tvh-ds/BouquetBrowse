// Dependency-free check through the deployed standalone web server, including cookies.
import assert from "node:assert/strict";
const base=process.env.SMOKE_ORIGIN || "http://127.0.0.1:3000";
const login=await fetch(`${base}/api/auth/login`,{
  method:"POST",headers:{"Content-Type":"application/json",Origin:base},
  body:JSON.stringify({email:"tester@bouquetbrowse.local",password:"demo-tester"})
});
assert.equal(login.status,200,"Local demo sign-in must work through standalone Next");
const cookies=login.headers.getSetCookie().map(value=>value.split(";")[0]).join("; ");
assert.ok(cookies.includes("bb_access="));
const request=async path=>fetch(`${base}${path}`,{headers:{Cookie:cookies}});
const catalogResponse=await request("/api/v1/catalog");
assert.equal(catalogResponse.status,200);
const catalog=await catalogResponse.json();
assert.ok(catalog.total>=30);
assert.ok(catalog.items.some(item=>item.is_demo));
const comparison=await request(`/api/v1/listings/${catalog.items[0].id}/comparison`);
assert.equal(comparison.status,200);
assert.equal((await request("/api/v1/admin/jobs")).status,403);
assert.equal((await fetch(`${base}/api/v1/catalog`)).status,401);
console.log("Standalone sign-in, private catalog, comparison and role enforcement passed.");
