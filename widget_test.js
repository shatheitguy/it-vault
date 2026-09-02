const fs=require("fs");
const src=fs.readFileSync(__dirname+"/app.js","utf8");
const a=src.indexOf("function setKV(id,v)");
const b=src.indexOf("function getDragAfterElement");
if(a<0||b<0){console.log("SLICE FAIL");process.exit(1);}
const block=src.slice(a,b).replace(/^const DASH_LAYOUT_KEY/m,"var DASH_LAYOUT_KEY");

// ---- stubs ----
const store={};
globalThis.localStorage={getItem:k=>k in store?store[k]:null,setItem:(k,v)=>{store[k]=String(v)},removeItem:k=>{delete store[k]}};
const els={};
function mk(id){ return els[id]||(els[id]={id,innerHTML:"",textContent:"",style:{},dataset:{},
  classList:{add(){},remove(){},contains:()=>false},querySelector:()=>null,querySelectorAll:()=>[],appendChild(){}}); }
globalThis.document={getElementById:id=>els[id]===undefined?null:els[id], querySelectorAll:()=>[]};
globalThis.esc=v=>String(v==null?"":v);
globalThis.openTicketById=()=>{};

// register only the ids that really exist in index.html
const html=fs.readFileSync(__dirname+"/index.html","utf8");
for(const m of html.matchAll(/\bid="([^"]+)"/g)) mk(m[1]);

let PAYLOAD={}, ASSETS=[], TICKETS=[], AUDIT=[];
globalThis.api=async(u)=>{
  if(u.startsWith("/api/dashboard")) return {json:async()=>PAYLOAD};
  if(u.startsWith("/api/assets"))    return {json:async()=>ASSETS};
  if(u.startsWith("/api/tickets"))   return {json:async()=>TICKETS};
  if(u.startsWith("/api/audit"))     return {json:async()=>AUDIT};
  return null;
};
(0,eval)(block);

const txt=id=>{const e=document.getElementById(id);return e?String(e.textContent):"<<MISSING>>";};
const html_=id=>{const e=document.getElementById(id);return e?String(e.innerHTML):"<<MISSING>>";};
let pass=0,fail=0;
function check(name,got,want){
  const ok=String(got)===String(want);
  ok?pass++:fail++;
  console.log(`  ${ok?"PASS":"FAIL"}  ${name.padEnd(34)} got=${JSON.stringify(String(got)).slice(0,58)}${ok?"":"  want="+JSON.stringify(String(want))}`);
}
function checkHas(name,got,needle){
  const ok=String(got).includes(needle);
  ok?pass++:fail++;
  console.log(`  ${ok?"PASS":"FAIL"}  ${name.padEnd(34)} ${ok?"contains "+JSON.stringify(needle):"MISSING "+JSON.stringify(needle)+" in "+JSON.stringify(String(got)).slice(0,80)}`);
}

(async()=>{
  console.log("\n=== CASE 1: populated data ===");
  PAYLOAD={total:240,checked_out:31,maintenance:7,due_soon:4,warranty_expiring:12,
           by_status:{"Available":180,"Checked-Out":31,"Under-Maintenance":7,"Retired":22},
           by_type:{"Laptop":90,"Phone":60,"CCTV":50,"Switch":40}};
  ASSETS=[{Name:"Dell 5540",Type:"Laptop",Serial:"SN-001",Status:"Available"},
          {Name:"Cisco SW",Type:"Switch",Serial:"SN-002",Status:"Checked-Out"}];
  TICKETS=[{id:1,code:"TK-1",subject:"Printer jam",status:"Open"},
           {id:2,code:"TK-2",subject:"VPN down",status:"In Progress"},
           {id:3,code:"TK-3",subject:"Done thing",status:"Closed"}];
  AUDIT=[{actor:"admin",action:"CREATE",asset_id:"a1",ts:"2026-09-01 10:00"}];
  await loadDashboard();
  await new Promise(r=>setTimeout(r,20));

  console.log(" dashboard KPI row:");
  check("kTotal",txt("kTotal"),240); check("kOut",txt("kOut"),31);
  check("kMaint",txt("kMaint"),7);   check("kDue",txt("kDue"),4);
  check("kWarr",txt("kWarr"),12);
  console.log(" assets page stat cards:");
  check("stTotal",txt("stTotal"),240); check("stOut",txt("stOut"),31);
  check("stMaint",txt("stMaint"),7);   check("stDue",txt("stDue"),4);
  check("stWarr",txt("stWarr"),12);
  console.log(" bar widgets:");
  checkHas("statusBars (Asset status)",html_("statusBars"),"Available");
  checkHas("statusBars sorted desc first",html_("statusBars").slice(0,200),"180");
  checkHas("typeBars (Top asset types)",html_("typeBars"),"Laptop");
  console.log(" table + feed widgets:");
  checkHas("dashRecentBody",html_("dashRecentBody"),"Dell 5540");
  checkHas("dashTicketsBody open only",html_("dashTicketsBody"),"Printer jam");
  check("dashTicketsBody excludes Closed",html_("dashTicketsBody").includes("Done thing"),false);
  checkHas("dashFeed",html_("dashFeed"),"admin");
  console.log(" empty-state flags hidden:");
  check("dashRecentEmpty",document.getElementById("dashRecentEmpty").style.display,"none");
  check("dashTicketsEmpty",document.getElementById("dashTicketsEmpty").style.display,"none");
  check("dashFeedEmpty",document.getElementById("dashFeedEmpty").style.display,"none");

  console.log("\n=== CASE 2: empty database ===");
  PAYLOAD={total:0,checked_out:0,maintenance:0,due_soon:0,warranty_expiring:0,by_status:{},by_type:{}};
  ASSETS=[];TICKETS=[];AUDIT=[];
  await loadDashboard();
  await new Promise(r=>setTimeout(r,20));
  check("kTotal zero",txt("kTotal"),0);
  check("stWarr zero",txt("stWarr"),0);
  checkHas("statusBars empty state",html_("statusBars"),"No data yet");
  checkHas("typeBars empty state",html_("typeBars"),"No data yet");
  check("dashRecentEmpty shown",document.getElementById("dashRecentEmpty").style.display,"block");
  check("dashTicketsEmpty shown",document.getElementById("dashTicketsEmpty").style.display,"block");
  check("dashFeedEmpty shown",document.getElementById("dashFeedEmpty").style.display,"block");

  console.log("\n=== CASE 3: refresh chain after an asset change ===");
  PAYLOAD={total:241,checked_out:31,maintenance:7,due_soon:4,warranty_expiring:12,by_status:{"Available":181},by_type:{"Laptop":91}};
  ASSETS=[{Name:"Brand New Asset",Type:"Laptop",Serial:"SN-NEW",Status:"Available"}];
  await loadDashboard();      // this is what runs after add/delete/checkout
  await new Promise(r=>setTimeout(r,20));
  check("KPI updated",txt("kTotal"),241);
  check("assets stat updated",txt("stTotal"),241);
  checkHas("Recent-assets widget refreshed",html_("dashRecentBody"),"Brand New Asset");

  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail?1:0);
})();
