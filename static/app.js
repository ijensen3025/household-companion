let familyEnabled=false, member=null, assigned={}, familyRequests=[];
let undoable={}, availableAreas=[];
let chores = [], energy = "medium", minutes = 20, activeView = "todo", planningMode = "maintain", focusRoom = "";
const $ = id => document.getElementById(id);
const viewNames = {todo:"To Do",daily:"Completed Daily",weekly:"Completed Weekly",monthly:"Completed Monthly",quarterly:"Completed Quarterly",yearly:"Completed Yearly",as_needed:"Completed As Needed"};
const viewInfo = {
 todo:"Chores never completed or whose next suggested date is today or earlier. No recorded date does not mean overdue.",
 daily:"Completed daily chores (every 1 day). They return to To Do on their next suggested date.",
 weekly:"Completed weekly and biweekly chores (every 2–14 days). They return to To Do on their next suggested date.",
 monthly:"Completed monthly chores (every 15–45 days). They return to To Do on their next suggested date.",
 quarterly:"Completed quarterly chores (every 46–120 days). They return to To Do on their next suggested date.",
 yearly:"Completed yearly and semiannual chores (more than 120 days). They return to To Do on their next suggested date.",
 as_needed:"Completed chores without a fixed interval. They have no automatic next suggested date."
};
const $el = (tag, cls, text) => {const x=document.createElement(tag);if(cls)x.className=cls;if(text!==undefined)x.textContent=text;return x;};
function showError(text){$("error").textContent=text;$("error").classList.remove("hidden");}
function formatDate(iso){
 if(!iso)return "—";
 const parts=iso.split("-").map(Number);
 if(parts.length!==3||parts.some(x=>!x))return iso;
 return new Date(Date.UTC(parts[0],parts[1]-1,parts[2])).toLocaleDateString("en-US",{timeZone:"UTC",month:"short",day:"numeric",year:"numeric"});
}
function frequencyLabel(days){
 if(days===1)return "Daily";
 if(days>=2&&days<=7)return "Weekly";
 if(days>=8&&days<=14)return "Biweekly";
 if(days>=15&&days<=45)return "Monthly";
 if(days>=46&&days<=120)return "Quarterly";
 if(days>120&&days<=240)return "Semiannually";
 if(days>240)return "Yearly";
 return "As needed";
}
function frequencyBadge(c){return $el("span","pill",frequencyLabel(c.frequency_days));}
function selectField(label, field, value, options){
 const wrap=$el("label","attr-field",label), select=document.createElement("select");select.name=field;
 for(const item of options)select.add(new Option(item,item));select.value=value;wrap.append(select);return wrap;
}
function renderEditor(c, host){
 host.replaceChildren();
 const d=c.attributes, form=$el("form","attribute-editor");
 const number=$el("label","attr-field","Estimated time (minutes)");
 const input=document.createElement("input");input.type="number";input.name="estimated_minutes";input.min="1";input.max="240";input.step="1";input.required=true;input.value=d.estimated_minutes;number.append(input);
 form.append(number,
   selectField("Physical effort","physical_effort",d.physical_effort,["Low","Medium","High"]),
   selectField("Mental effort","mental_effort",d.mental_effort,["Low","Medium","High"]),
   selectField("Age suitability","age_suitability",d.age_suitability,["Adults only","Child with supervision","All ages","Child-specific"]));
 const actions=$el("div","attr-buttons"), save=$el("button","complete","Save attributes"), cancel=$el("button","attr-edit","Cancel"), feedback=$el("span","quiet","");
 save.type="submit";cancel.type="button";cancel.addEventListener("click",()=>host.replaceChildren());actions.append(save,cancel,feedback);form.append(actions);
 form.addEventListener("submit",async e=>{
  e.preventDefault();const entries=Object.fromEntries(new FormData(form).entries());
  entries.estimated_minutes=Number(entries.estimated_minutes);
  entries.priority=c.priority; // Preserve legacy field required by existing API; ranking ignores it.
  save.disabled=true;feedback.textContent="Saving…";
  try{
   const response=await fetch(`/api/attributes/${encodeURIComponent(c.id)}`,{method:"POST",headers:{"Content-Type":"application/json","X-Household-Request":"1"},body:JSON.stringify(entries)});
   if(!response.ok)throw Error((await response.json()).detail||"Save failed");
   await load();feedback.textContent="Saved";host.replaceChildren();
  }catch(error){feedback.textContent=error.message;save.disabled=false;}
 });host.append(form);
}
function renderList(){
 const area=$("area").value, status=$("status").value, q=$("search").value.toLowerCase();
 const completedView = activeView !== "todo";
 const filtered=chores.filter(c=>c.views?.[activeView] && (completedView || !c.assigned_to) && (!area||c.area===area) && (!status||c.status===status) && (!q||`${c.name} ${c.area}`.toLowerCase().includes(q)));
 $("count").textContent=`${filtered.length} ${filtered.length===1?"chore":"chores"}`;
 const list=$("chore-list");list.replaceChildren();
 if(!filtered.length){list.append($el("p","quiet",completedView?"No chores waiting in this completed category.":"No chores in To Do right now."));return;}
 filtered.sort((a,b)=>a.area.localeCompare(b.area)||a.name.localeCompare(b.name));
 filtered.forEach(c=>{
  const row=$el("div","chore"), info=$el("div"), title=$el("div","chore-title",c.name);
  let detail;
  if(completedView){detail=`${c.area} · Last completed ${formatDate(c.last_completed)} · Next suggested: ${c.next_suggested ? formatDate(c.next_suggested) : "As needed"}`;}
  else {detail=`${c.area} · ${c.status}`+(c.next_suggested?` · Suggested ${formatDate(c.next_suggested)}`:"");}
  info.append(title,$el("div","meta",detail),frequencyBadge(c),$el("div","meta",`${c.attributes.estimated_minutes} min · Physical ${c.attributes.physical_effort} · Mental ${c.attributes.mental_effort} · ${c.attributes.age_suitability}`));
  const actions=$el("div","chore-actions"), edit=$el("button","attr-edit","Edit attributes"), editor=$el("div");
  if(c.assigned_to){info.append($el("div","family-info",`Assigned to ${c.assigned_to}`));}
  else if(c.pending_for?.length){info.append($el("div","family-info",`Request pending: ${c.pending_for.join(", ")}`));}
  edit.type="button";edit.addEventListener("click",()=>renderEditor(c,editor));
  if(member==="Ida" || member==="Husband") actions.append(edit);
  if(completedView){actions.append($el("span","pill completed-pill","✓ Completed"));
   if(undoable[c.id]) actions.append(undoButton(c));
   row.append(info,actions);}
  else {
   if(familyEnabled && member && !c.assigned_to){
     const own=$el("button","attr-edit","Claim for myself");
     own.addEventListener("click",()=>familyAction("CLAIM",c.id));actions.append(own);
     if(member!=="Daughter") {
     const tools=$el("div","request-tools"), select=$el("select");
     const options=["Ida","Husband","Daughter"].filter(x=>x!==member);
     select.append(new Option("Suggest to…",""),...options.map(x=>new Option(x,x)));
     const ask=$el("button","","Send request");ask.addEventListener("click",()=>{
       if(select.value)familyAction("REQUEST",c.id,{recipient:select.value});
     });tools.append(select,ask);info.append(tools);
     }
   }
   const btn=$el("button","complete","✓ Done today");
   btn.title=`Record completion of ${c.name}`;
   if(c.assigned_to && c.assigned_to!==member){btn.disabled=true;btn.title=`Assigned to ${c.assigned_to}`;}
   btn.addEventListener("click",async()=>{
    btn.disabled=true;btn.textContent="Saving…";
    try{
      const resp=await fetch("/api/complete",{method:"POST",headers:{"Content-Type":"application/json","X-Household-Request":"1"},body:JSON.stringify({task_id:c.id,operation_id:crypto.randomUUID()})});
      if(!resp.ok)throw Error((await resp.json()).detail||"Could not save");
      await load();
    }catch(e){showError(e.message);btn.disabled=false;btn.textContent="✓ Done today";}
   });
   actions.append(btn);
   if(undoable[c.id]) actions.append(undoButton(c));
   row.append(info,actions);
  }
  const container=$el("div","chore-wrapper");container.append(row,editor);list.append(container);
 });
}
function renderRecs(items){
 const wrap=$("recommendations");wrap.replaceChildren();
 if(!items.length){wrap.append($el("p","quiet","No available chores fit your energy and time right now. Rest or choose another plan."));return;}
 items.forEach(c=>{let box=$el("div","recommend");box.append($el("small","",c.area),$el("b","",c.name),$el("small","",`${c.estimated_minutes} min · ${c.attributes.physical_effort} physical effort · ${c.status}`));if(familyEnabled && member){let btn=$el("button","rec-action","Claim this chore");btn.onclick=()=>familyAction("CLAIM",c.id);box.append(btn);}wrap.append(box);});
}
function setView(view){
 if (!Object.prototype.hasOwnProperty.call(viewNames, view)) return;
 activeView=view;
 $("tab-heading").textContent=viewNames[view];
 $("tab-explanation").textContent=viewInfo[view];
 document.querySelectorAll("[data-view]").forEach(b=>{const selected=b.dataset.view===view;b.classList.toggle("active",selected);b.setAttribute("aria-pressed",String(selected));});
 $("status").value="";
 $("status").disabled=view!=="todo";
 renderList();
}
async function load(){
 $("error").classList.add("hidden");
 try{
  const resp=await fetch(`/api/chores?energy=${energy}&minutes=${minutes}&mode=${planningMode}&room=${encodeURIComponent(focusRoom)}`,{cache:"no-store"});
  if(!resp.ok)throw Error((await resp.json()).detail||"Could not load chores");
  const data=await resp.json();
  if (data.ui_contract !== "firestore-v2" || !Array.isArray(data.chores) ||
      data.chores.some(c => !c.views || typeof c.views.todo !== "boolean")) {
    throw Error("The page and server versions don't match. Refresh the page to load the current tracker.");
  }
  chores=data.chores;
  familyEnabled=data.family_enabled;member=data.member;
  assigned=data.assigned||{};familyRequests=data.requests||[];
  undoable=data.undoable||{}; availableAreas=data.areas||[];
  renderManagement();
  renderFamily(data);
  const values=[["Chores",data.summary.total],["Areas",data.summary.areas],["Completions",data.summary.completions]];
  $("stats").replaceChildren(...values.map(([label,val])=>{let s=$el("div","stat");s.append($el("b","",String(val)),$el("span","",label));return s;}));
  const current=$("area").value,areas=availableAreas.length?availableAreas:[...new Set(chores.map(c=>c.area))].sort();
  $("area").replaceChildren(new Option("All areas",""),...areas.map(a=>new Option(a,a)));$("area").value=current;
  $("updated").textContent=`Updated ${data.as_of}`;
  for(const view of Object.keys(viewNames)){const badge=document.querySelector(`[data-tab-count="${view}"]`);if(badge)badge.textContent=String(chores.filter(c=>c.views?.[view] && (view!=="todo" || !c.assigned_to)).length);}
  const currentRoom=$("focus-room").value || focusRoom;
  $("focus-room").replaceChildren(...areas.map(a=>new Option(a,a)));
  focusRoom=areas.includes(currentRoom)?currentRoom:(areas[0]||"");$("focus-room").value=focusRoom;
  renderRecs(data.suggestions);renderList();
 }catch(e){showError(e.message);$("chore-list").replaceChildren($el("p","quiet","Could not load the tracker."));$("recommendations").replaceChildren();}
}
document.querySelectorAll("[data-energy]").forEach(b=>b.addEventListener("click",()=>{energy=b.dataset.energy;document.querySelectorAll("[data-energy]").forEach(x=>x.classList.toggle("selected",x===b));load();}));
document.querySelectorAll("[data-mode]").forEach(button=>button.addEventListener("click",()=>{
 planningMode=button.dataset.mode;document.querySelectorAll("[data-mode]").forEach(b=>b.classList.toggle("selected",b===button));
 $("room-filter").hidden=planningMode!=="room";
 focusRoom=$("focus-room").value||focusRoom;load();
}));
$("focus-room").addEventListener("change",e=>{focusRoom=e.target.value;load();});
$("minutes").addEventListener("change",e=>{minutes=Number(e.target.value);load();});
["search","area","status"].forEach(id=>$(id).addEventListener(id==="search"?"input":"change",renderList));
// Delegate clicks to the tabs container, so tab controls also work if the
// navigation is regenerated later and event handlers are not lost.
$("tracker-tabs").addEventListener("click",e=>{
 const button=e.target.closest("button[data-view]");
 if(button) setView(button.dataset.view);
});
setView("todo");load();


function renderFamily(data){
 const setup=$("family-setup"),mine=$("my-chores"),inbox=$("my-requests"),overview=$("family-summary");
 [mine,inbox,overview].forEach(x=>x.replaceChildren());
 $("family-identity").textContent=member?`Signed in as ${member}`:"Sign-in required";
 setup.textContent="Recommendations are suggestions, not assignments. Requests remain in To Do until accepted.";
 const assignedIds=Object.keys(assigned).filter(id=>assigned[id]===member);
 for(const id of assignedIds){const chore=chores.find(x=>x.id===id);if(!chore)continue;
   const line=$el("div","family-entry");line.append($el("strong","",chore.name),$el("small","",chore.area));
   const actions=$el("div","row-actions"),release=$el("button","","Release"),complete=$el("button","","✓ Done today");
   complete.onclick=async()=>{
     complete.disabled=true;
     try{
       const resp=await fetch("/api/complete",{method:"POST",headers:{"Content-Type":"application/json","X-Household-Request":"1"},body:JSON.stringify({task_id:id,operation_id:crypto.randomUUID()})});
       if(!resp.ok)throw Error((await resp.json()).detail||"Could not record completion");
       await load();
     }catch(e){showError(e.message);complete.disabled=false;}
   };
   release.onclick=()=>familyAction("RELEASE",id);actions.append(complete,release);line.append(actions);mine.append(line);
 }
 if(!mine.children.length)mine.append($el("p","quiet","Nothing assigned to you yet."));
 const pending=familyRequests.filter(r=>r.status==="pending"&&r.to===member);
 for(const req of pending){const chore=chores.find(x=>x.id===req.task_id);if(!chore)continue;
   const line=$el("div","family-entry");line.append($el("strong","",chore.name),$el("small","",`Suggested by ${req.from}${req.note?" · "+req.note:""}`));
   const actions=$el("div","row-actions");for(const [label,action] of [["Accept","ACCEPT"],["Decline","DECLINE"]]){
     const b=$el("button","",label);b.onclick=()=>familyAction(action,req.task_id,{request_id:req.id});actions.append(b);
   }line.append(actions);inbox.append(line);
 }
 if(!inbox.children.length)inbox.append($el("p","quiet","No pending requests."));
 for(const name of ["Ida","Husband","Daughter"]){const count=Object.values(assigned).filter(n=>n===name).length;
    const box=$el("article","",`${name}: ${count} assigned`);overview.append(box);}
}
async function familyAction(action,task_id,extra={}){
 try{
   const resp=await fetch("/api/family/action",{method:"POST",headers:{"Content-Type":"application/json","X-Household-Request":"1"},body:JSON.stringify({action,task_id,operation_id:crypto.randomUUID(),...extra})});
   if(!resp.ok)throw Error((await resp.json()).detail||"Family action failed");
   await load();
 }catch(e){showError(e.message);}
}

function undoButton(chore){
 const btn=$el("button","attr-edit","Undo completion");
 btn.type="button";
 btn.addEventListener("click",async()=>{
  const target=undoable[chore.id];
  if(!target)return;
  if(!confirm(`Undo the ${formatDate(target.completed_on)} completion of “${chore.name}”? Earlier completion history will be kept.`))return;
  btn.disabled=true;btn.textContent="Undoing…";
  try{
   await apiWrite("/api/completions/undo",{task_id:chore.id,completion_id:target.completion_id,operation_id:crypto.randomUUID()});
   await load();
   const updated=chores.find(c=>c.id===chore.id);
   if(updated){const view=Object.keys(updated.views).find(v=>updated.views[v]);if(view)setView(view);}
  }catch(e){showError(e.message);btn.disabled=false;btn.textContent="Undo completion";}
 });
 return btn;
}
async function apiWrite(path,payload){
 const response=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json","X-Household-Request":"1"},body:JSON.stringify(payload)});
 if(!response.ok)throw Error((await response.json()).detail||"Could not save");
 return response.json();
}
function renderManagement(){
 const parent=member==="Ida" || member==="Husband";
 $("chore-management").hidden=!parent;
 if(!parent)return;
 const selection=$("new-chore-area"),prev=selection.value;
 selection.replaceChildren(...availableAreas.map(a=>new Option(a,a)));
 if(availableAreas.includes(prev))selection.value=prev;
}
$("area-create-form").addEventListener("submit",async event=>{
 event.preventDefault();
 const form=event.currentTarget,button=form.querySelector('[type="submit"]'),feedback=$("area-form-feedback");
 const name=new FormData(form).get("name");button.disabled=true;feedback.textContent="Saving…";
 try{
  await apiWrite("/api/areas",{name});
  form.reset();await load();feedback.textContent="Area created.";
 }catch(e){feedback.textContent=e.message;}finally{button.disabled=false;}
});
$("chore-create-form").addEventListener("submit",async event=>{
 event.preventDefault();
 const form=event.currentTarget,button=form.querySelector('[type="submit"]'),feedback=$("chore-form-feedback");
 const body=Object.fromEntries(new FormData(form));
 body.estimated_minutes=Number(body.estimated_minutes);
 body.frequency_days=body.frequency_days==="as_needed"?null:Number(body.frequency_days);
 button.disabled=true;feedback.textContent="Saving…";
 try{
  const result=await apiWrite("/api/chores",body);
  form.reset();await load();setView("todo");feedback.textContent=`Added ${result.name} (${result.task_id}).`;
 }catch(e){feedback.textContent=e.message;}finally{button.disabled=false;}
});
