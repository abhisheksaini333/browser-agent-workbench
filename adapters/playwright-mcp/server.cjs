// Bounded composition of the pinned Playwright MCP server; no dependency source patches.
const {Server}=require('./node_modules/@playwright/mcp/lib/server');
const snapshot=require('./node_modules/@playwright/mcp/lib/tools/snapshot');
const common=require('./node_modules/@playwright/mcp/lib/tools/common');
const origin=new URL(process.env.WORKBENCH_ORIGIN);
if(!['127.0.0.1','localhost'].includes(origin.hostname)||origin.username||origin.password)throw Error('owned origin required');
(async()=>{
 const server=new Server({name:'Owned portal browser',version:'0.0.3',tools:[common.navigate(true),snapshot.snapshot,snapshot.type,snapshot.click,common.close],resources:[]},{headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{}),args:['--no-sandbox']});
 const page=await server._context.ensurePage();
 await page.context().setExtraHTTPHeaders({'X-Dispatch-Token':process.env.WORKBENCH_DISPATCH_TOKEN});
 await page.context().route('**/*',async route=>{
  let allowed=false;try{const u=new URL(route.request().url());allowed=u.origin===origin.origin&&!u.username&&!u.password;}catch{}
  if(allowed)await route.continue();else await route.abort();
 });
 await server.start();
 process.stdin.on('end',async()=>{await server.stop();process.exit(0);});
})().catch(error=>{process.stderr.write(error.message+'\n');process.exit(1);});
