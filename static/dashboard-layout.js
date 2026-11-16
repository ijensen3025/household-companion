/* Move existing section nodes so forms, tabs and their event handlers survive. */
const dashboardLayout = (() => {
 const host = document.getElementById("dashboard-cards");
 const status = document.getElementById("dashboard-layout-status");
 const cards = new Map([
  ["family", document.getElementById("family-panel")],
  ["planner", host.querySelector("section.planning")],
  ["management", document.getElementById("chore-management")],
  ["tracker", host.querySelector("section.tasks")]
 ]);
 const defaults = [...cards.keys()];
 let member = null, dragged = null;
 const key = () => `household-companion:dashboard-layout:v1:${member}`;
 const visible = () => [...host.children].filter(card => !card.hidden);
 const announce = text => { status.textContent = text; };
 function refreshButtons() {
  const items = visible();
  for (const card of cards.values()) {
   card.querySelector("[data-layout-up]").disabled = card === items[0];
   card.querySelector("[data-layout-down]").disabled = card === items[items.length - 1];
  }
 }
 function persist() {
  refreshButtons();
  try {
   localStorage.setItem(key(), JSON.stringify([...host.children].map(card => card.dataset.dashboardCard)));
   announce("Card order saved for your account in this browser only.");
  } catch {
   announce("Card order changed, but this browser could not save it. It will reset on refresh.");
  }
 }
 function move(card, direction) {
  if (!member || card.hidden) return;
  const items = visible(), target = items[items.indexOf(card) + direction];
  if (!target) return;
  const control = card.querySelector(direction < 0 ? "[data-layout-up]" : "[data-layout-down]");
  host.insertBefore(card, direction < 0 ? target : target.nextSibling);
  persist();
  // The moving button can become disabled at a boundary; keep focus on this card.
  (control.disabled ? card.querySelector(".layout-drag") : control).focus();
 }
 for (const [id, card] of cards) {
  card.dataset.dashboardCard = id;
  const title = card.querySelector("h2").textContent;
  const controls = document.createElement("div"); controls.className = "card-layout-controls";
  const handle = document.createElement("button");
  handle.type = "button"; handle.className = "layout-drag"; handle.draggable = true;
  handle.textContent = "⠿ Move card";
  handle.setAttribute("aria-label", `Move ${title}; drag or use the up and down buttons`);
  controls.append(handle);
  for (const [direction, name] of [[-1, "up"], [1, "down"]]) {
   const button = document.createElement("button"); button.type = "button";
   button.textContent = direction < 0 ? "↑" : "↓";
   button.setAttribute(`data-layout-${name}`, "");
   button.setAttribute("aria-label", `Move ${title} ${name}`);
   button.addEventListener("click", () => move(card, direction));
   controls.append(button);
  }
  controls.hidden = true; card.prepend(controls);
  handle.addEventListener("dragstart", event => {
   if (!member || card.hidden) { event.preventDefault(); return; }
   dragged = card; card.classList.add("layout-dragging");
   event.dataTransfer.effectAllowed = "move";
   event.dataTransfer.setData("text/plain", id);
  });
  handle.addEventListener("dragend", () => {
   dragged = null;
   for (const item of cards.values()) item.classList.remove("layout-dragging", "layout-drop-target");
  });
  card.addEventListener("dragover", event => {
   if (!dragged || dragged === card || card.hidden) return;
   event.preventDefault(); event.dataTransfer.dropEffect = "move";
   card.classList.add("layout-drop-target");
  });
  card.addEventListener("dragleave", event => {
   if (!card.contains(event.relatedTarget)) card.classList.remove("layout-drop-target");
  });
  card.addEventListener("drop", event => {
   if (!dragged || dragged === card || card.hidden) return;
   event.preventDefault();
   const items = visible();
   host.insertBefore(dragged, items.indexOf(dragged) < items.indexOf(card) ? card.nextSibling : card);
   persist();
   for (const item of cards.values()) item.classList.remove("layout-drop-target");
  });
 }
 document.getElementById("reset-dashboard-layout").addEventListener("click", () => {
  if (!member) return;
  defaults.forEach(id => host.append(cards.get(id)));
  persist();
 });
 return {setMember(value) {
  if (!["Ida", "Husband", "Daughter"].includes(value)) return;
  if (member !== value) {
   member = value;
   let order = [];
   try {
    const saved = JSON.parse(localStorage.getItem(key()));
    if (Array.isArray(saved)) order = saved.filter(id => cards.has(id));
   } catch { /* Unavailable storage or malformed preferences use the default. */ }
   [...new Set([...order, ...defaults])].forEach(id => host.append(cards.get(id)));
   announce("Card order saves for your account in this browser only.");
  }
  // Only renderManagement controls role visibility; reordering never unhides cards.
  for (const card of cards.values()) card.querySelector(".card-layout-controls").hidden = false;
  document.getElementById("dashboard-layout-tools").hidden = false;
  refreshButtons();
 }};
})();
