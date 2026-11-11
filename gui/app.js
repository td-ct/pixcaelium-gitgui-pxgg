const S = {
  repo: localStorage.getItem("gitgui.repo") || "",
  lang: localStorage.getItem("gitgui.lang") || "en",
  i18n: {},
  workflows: [],
  catalog: null,
  currentCmd: null,
};

const $ = (s) => document.querySelector(s);

function t(key) {
  return S.i18n[key] !== undefined ? S.i18n[key] : key;
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

async function api(path, opts) {
  opts = opts || {};
  if (window.GitguiBridge) {
    const res = JSON.parse(window.GitguiBridge.call(opts.method || "GET", "/api" + path, opts.body || null));
    const data = res.data;
    if (res.status >= 400) throw new Error((data && data.error) || ("HTTP " + res.status));
    return data;
  }
  opts.headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
  const r = await fetch("/api" + path, opts);
  const txt = await r.text();
  let data;
  try { data = JSON.parse(txt); } catch (e) { data = { error: txt }; }
  if (!r.ok) throw new Error(data.error || ("HTTP " + r.status));
  return data;
}

async function loadI18n() {
  S.i18n = await api("/i18n/" + S.lang);
  document.documentElement.lang = S.lang;
  document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll("[data-i18n-ph]").forEach((el) => { el.placeholder = t(el.dataset.i18nPh); });
  renderGuided();
  renderCmdTree();
  renderCredTable();
}

async function loadMeta() {
  const meta = await api("/meta");
  const sel = $("#lang-select");
  sel.innerHTML = "";
  for (const l of meta.langs) {
    const o = document.createElement("option");
    o.value = l; o.textContent = l;
    if (l === S.lang) o.selected = true;
    sel.appendChild(o);
  }
}

async function loadRepos() {
  const data = await api("/repos");
  const sel = $("#repo-select");
  sel.innerHTML = "";
  for (const r of data.repos) {
    const o = document.createElement("option");
    o.value = r.path;
    const name = r.path.split("/").filter(Boolean).pop() || r.path;
    o.textContent = r.is_repo
      ? `${name} [${r.branch || "?"}${r.dirty ? " *" : ""}]`
      : `${name} (${t("ui.not_a_repo")})`;
    sel.appendChild(o);
    if (r.path === S.repo) sel.value = r.path;
  }
  if (!sel.value && data.repos.length) sel.value = data.repos[0].path;
  S.repo = sel.value || "";
  localStorage.setItem("gitgui.repo", S.repo);
}

async function loadWorkflows() {
  const data = await api("/workflows");
  S.workflows = data.workflows;
  renderGuided();
}

async function loadCatalog() {
  S.catalog = await api("/commands", { method: "POST", body: JSON.stringify({ repo: S.repo || null }) });
  renderCmdTree();
}

function renderAll() {
  renderGuided();
  renderCmdTree();
}

function renderGuided() {
  const host = $("#workflow-cards");
  if (!host) return;
  host.innerHTML = "";
  for (const wf of S.workflows) {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `<h3>${esc(t(wf.title_key))}</h3><p class="desc">${esc(t(wf.desc_key))}</p>`;
    const fields = [];
    for (const p of wf.params) {
      const f = document.createElement("div");
      f.className = "field" + (p.type === "bool" ? " bool" : "");
      const label = document.createElement("span");
      label.textContent = t(p.label_key) + (p.required ? " *" : "");
      f.appendChild(label);
      let input;
      if (p.type === "bool") {
        input = document.createElement("input");
        input.type = "checkbox";
        f.insertBefore(input, label);
      } else if (p.type === "select") {
        input = document.createElement("select");
        for (const o of p.options) {
          const opt = document.createElement("option");
          opt.value = o; opt.textContent = t("wfopt." + wf.id + "." + p.key + "." + o) !== ("wfopt." + wf.id + "." + p.key + "." + o) ? t("wfopt." + wf.id + "." + p.key + "." + o) : o;
          input.appendChild(opt);
        }
      } else if (p.type === "int") {
        input = document.createElement("input");
        input.type = "number";
      } else if (p.type === "files") {
        input = document.createElement("div");
        input.className = "files-list";
        const btn = document.createElement("button");
        btn.textContent = t("ui.load_files");
        btn.onclick = async () => {
          const res = await api("/workflow/run", { method: "POST", body: JSON.stringify({ repo: S.repo || null, id: "status", params: {} }) });
          input.innerHTML = "";
          for (const f of (res.data.files || [])) {
            const lab = document.createElement("label");
            const cb = document.createElement("input");
            cb.type = "checkbox"; cb.value = f.path; cb.checked = f.x !== "?";
            lab.appendChild(cb);
            lab.appendChild(document.createTextNode(`${f.code} ${f.path}`));
            input.appendChild(lab);
          }
        };
        input.appendChild(btn);
      } else {
        input = document.createElement("input");
        input.type = "text";
        if (p.complete && p.complete !== "none") attachCompletion(input, (v) => completeWords(p.complete, v));
      }
      input.dataset.key = p.key;
      input.dataset.type = p.type;
      f.appendChild(input);
      card.appendChild(f);
      fields.push({ spec: p, input });
    }
    const run = document.createElement("button");
    run.className = "primary";
    run.textContent = t("ui.run");
    run.onclick = () => runWorkflow(wf, fields, card);
    card.appendChild(run);
    const out = document.createElement("div");
    card.appendChild(out);
    host.appendChild(card);
  }
}

function completeWords(hint, value) {
  const map = {
    branch: ["git", "checkout", value],
    remote: ["git", "push", value],
    file: ["git", "add", value],
    path: ["git", "clone", value],
    tag: ["git", "checkout", value],
  };
  return map[hint] || ["git", value];
}

async function runWorkflow(wf, fields, card) {
  const params = {};
  for (const { spec, input } of fields) {
    if (spec.type === "bool") params[spec.key] = input.checked;
    else if (spec.type === "files") {
      params[spec.key] = Array.from(input.querySelectorAll("input:checked")).map((c) => c.value);
    } else params[spec.key] = input.value;
  }
  const out = card.lastElementChild;
  out.innerHTML = `<div class="output"><span class="badge">${esc(t("ui.loading"))}</span></div>`;
  try {
    const res = await api("/workflow/run", { method: "POST", body: JSON.stringify({ repo: S.repo || null, id: wf.id, params }) });
    renderResult(out, res);
  } catch (e) {
    out.innerHTML = `<div class="output"><pre class="stderr">${esc(e.message)}</pre></div>`;
  }
}

function renderResult(out, res) {
  let html = `<div class="output"><span class="badge ${res.ok ? "ok" : "err"}">${t("ui.exit")}: ${res.ok ? 0 : "≠0"}</span>`;
  for (const s of res.steps || []) {
    html += `<div class="cmdline">$ git ${esc(s.args.join(" "))}</div>`;
    if (s.stdout) html += `<pre>${esc(s.stdout)}</pre>`;
    if (s.stderr) html += `<pre class="stderr">${esc(s.stderr)}</pre>`;
  }
  html += `</div>`;
  if (res.error) {
    const e = res.error;
    html += `<div class="error-box"><h4>${esc(t(e.title_key))}</h4><p>${esc(t(e.detail_key))}</p>`;
    if (e.matched) html += `<div class="matched">${esc(e.matched)}</div>`;
    html += `<div class="sugg">`;
    for (const s of e.suggestions || []) {
      html += `<button class="${s.danger ? "danger" : ""}" data-sugg="${esc(JSON.stringify(s))}">${esc(t(s.label_key))}</button>`;
    }
    html += `</div></div>`;
  }
  out.innerHTML = html;
  out.querySelectorAll("[data-sugg]").forEach((btn) => {
    btn.onclick = () => handleSuggestion(JSON.parse(btn.dataset.sugg), out);
  });
}

async function handleSuggestion(s, out) {
  if (s.type === "exec") {
    switchTab("pro");
    const res = await api("/exec", { method: "POST", body: JSON.stringify({ repo: S.repo || null, args: s.args }) });
    showProOutput(res);
  } else if (s.type === "workflow") {
    const res = await api("/workflow/run", { method: "POST", body: JSON.stringify({ repo: S.repo || null, id: s.workflow, params: s.params || {} }) });
    renderResult(out, res);
  } else if (s.type === "open") {
    if (s.target === "credentials") $("#cred-modal").classList.remove("hidden");
    if (s.target === "repo") $("#browse-modal").classList.remove("hidden");
  }
}

function renderCmdTree() {
  const host = $("#cmd-tree");
  if (!host || !S.catalog) return;
  host.innerHTML = "";
  for (const cat of S.catalog.categories) {
    const d = document.createElement("details");
    d.open = true;
    const sum = document.createElement("summary");
    sum.textContent = t(cat.label_key);
    d.appendChild(sum);
    for (const cmd of cat.commands) {
      const b = document.createElement("button");
      b.className = "cmd-btn" + (S.currentCmd === cmd ? " active" : "");
      b.textContent = cmd.name;
      b.title = t("cmd." + cmd.name);
      b.onclick = () => selectCommand(cmd);
      d.appendChild(b);
    }
    host.appendChild(d);
  }
}

function selectCommand(cmd) {
  S.currentCmd = cmd;
  renderCmdTree();
  const host = $("#cmd-form");
  const desc = t("cmd." + cmd.name);
  const live = cmd.live_desc ? ` <span class="cmd-desc">${esc(cmd.live_desc)}</span>` : "";
  host.innerHTML = `<h3>git ${esc(cmd.name)}</h3><p class="cmd-desc">${esc(desc)}${live}</p>`;
  const fields = [];
  for (const a of cmd.args) {
    const f = document.createElement("div");
    f.className = "field" + (a.type === "flag" ? " bool" : "");
    const label = document.createElement("span");
    label.textContent = t(a.label_key) + (a.required ? " *" : "") + (a.flag ? `  (${a.flag})` : "");
    f.appendChild(label);
    let input;
    if (a.type === "flag") {
      input = document.createElement("input");
      input.type = "checkbox";
      f.insertBefore(input, label);
    } else {
      input = document.createElement("input");
      input.type = "text";
      if (a.complete && a.complete !== "none") {
        attachCompletion(input, () => proWords(cmd, fields, input));
      }
    }
    input.dataset.key = a.key;
    input.dataset.arg = JSON.stringify(a);
    f.appendChild(input);
    host.appendChild(f);
    fields.push({ spec: a, input });
  }
  const exLab = document.createElement("div");
  exLab.className = "field";
  exLab.innerHTML = `<span>${esc(t("ui.extra_args"))}</span>`;
  const ex = document.createElement("textarea");
  ex.id = "extra-args";
  exLab.appendChild(ex);
  host.appendChild(exLab);
  const actions = document.createElement("div");
  actions.className = "actions";
  const run = document.createElement("button");
  run.className = "primary"; run.textContent = t("ui.run");
  run.onclick = () => runCommand(cmd, fields);
  const hbtn = document.createElement("button");
  hbtn.textContent = "git " + cmd.name + " -h";
  hbtn.onclick = async () => {
    const r = await api("/help?cmd=" + encodeURIComponent(cmd.name) + "&repo=" + encodeURIComponent(S.repo || ""));
    showMan("git " + cmd.name + " -h", r.text);
  };
  const mbtn = document.createElement("button");
  mbtn.textContent = t("ui.man_page");
  mbtn.onclick = async () => {
    const r = await api("/man?cmd=" + encodeURIComponent(cmd.name) + "&repo=" + encodeURIComponent(S.repo || ""));
    showMan("man git-" + cmd.name + (r.source ? "  [" + r.source + "]" : ""), r.text || r.error || "");
  };
  actions.appendChild(run); actions.appendChild(hbtn); actions.appendChild(mbtn);
  host.appendChild(actions);
}

function proWords(cmd, fields, current) {
  const words = ["git", cmd.name];
  for (const { input } of fields) {
    words.push(input === current ? input.value : (input.type === "checkbox" ? (input.checked ? (JSON.parse(input.dataset.arg).flag || "") : "") : input.value));
    if (input === current) break;
  }
  return words;
}

async function runCommand(cmd, fields) {
  const args = [];
  for (const { spec, input } of fields) {
    if (spec.type === "flag") {
      if (input.checked) args.push(spec.flag);
    } else {
      const v = input.value;
      if (!v) continue;
      if (spec.flag) args.push(spec.flag);
      if (spec.multi) args.push(...v.split(/\s+/).filter(Boolean));
      else args.push(v);
    }
  }
  const extra = $("#extra-args").value.split("\n").map((l) => l.trim()).filter(Boolean);
  args.push(...extra);
  const res = await api("/exec", { method: "POST", body: JSON.stringify({ repo: S.repo || null, args: [cmd.name, ...args] }) });
  showProOutput(res);
}

function showProOutput(res) {
  const out = $("#pro-output");
  out.classList.remove("hidden");
  let html = `<span class="badge ${res.exit_code === 0 ? "ok" : "err"}">${t("ui.exit")}: ${res.exit_code}</span>`;
  html += `<div class="cmdline">$ git ${esc((res.args || []).join(" "))}</div>`;
  if (res.stdout) html += `<pre>${esc(res.stdout)}</pre>`;
  if (res.stderr) html += `<pre class="stderr">${esc(res.stderr)}</pre>`;
  if (!res.stdout && !res.stderr) html += `<pre>${esc(t("ui.no_output"))}</pre>`;
  out.innerHTML = html;
}

function attachCompletion(input, getWords) {
  let dd = null;
  function hide() { if (dd) dd.classList.remove("show"); }
  function show(cands) {
    if (!dd) {
      dd = document.createElement("div");
      dd.className = "dropdown";
      input.parentElement.appendChild(dd);
    }
    dd.innerHTML = "";
    for (const c of cands.slice(0, 50)) {
      const item = document.createElement("div");
      item.textContent = c;
      item.onclick = () => { input.value = c; hide(); input.focus(); };
      dd.appendChild(item);
    }
    dd.classList.add("show");
  }
  async function fetchC() {
    const words = getWords();
    try {
      return await api("/complete", { method: "POST", body: JSON.stringify({ repo: S.repo || null, words, cword: words.length - 1 }) });
    } catch (e) { return null; }
  }
  input.addEventListener("input", async () => {
    const r = await fetchC();
    if (r && r.candidates.length) show(r.candidates); else hide();
  });
  input.addEventListener("keydown", async (e) => {
    if (e.key === "Tab") {
      e.preventDefault();
      const r = await fetchC();
      if (!r) return;
      const v = input.value;
      if (r.candidates.length === 1) input.value = r.candidates[0];
      else if (r.common_prefix && r.common_prefix.length > v.length) input.value = r.common_prefix;
      if (r.candidates.length) show(r.candidates); else hide();
    } else if (e.key === "Escape") hide();
  });
  input.addEventListener("blur", () => setTimeout(hide, 150));
}

function showMan(title, text) {
  $("#man-panel").classList.remove("hidden");
  $("#man-title").textContent = title;
  const pre = $("#man-text");
  pre.dataset.full = text;
  pre.textContent = text;
  $("#man-search").value = "";
}

$("#man-search").addEventListener("input", (e) => {
  const pre = $("#man-text");
  const q = e.target.value.toLowerCase();
  const full = pre.dataset.full || "";
  if (!q) { pre.textContent = full; return; }
  pre.textContent = full.split("\n").filter((l) => l.toLowerCase().includes(q)).join("\n");
});
$("#man-close").onclick = () => $("#man-panel").classList.add("hidden");

function switchTab(name) {
  $("#tab-guided").classList.toggle("active", name === "guided");
  $("#tab-pro").classList.toggle("active", name === "pro");
  $("#view-guided").classList.toggle("active", name === "guided");
  $("#view-pro").classList.toggle("active", name === "pro");
}
$("#tab-guided").onclick = () => switchTab("guided");
$("#tab-pro").onclick = () => switchTab("pro");

$("#repo-select").onchange = (e) => {
  S.repo = e.target.value;
  localStorage.setItem("gitgui.repo", S.repo);
  loadCatalog();
};
$("#lang-select").onchange = (e) => {
  S.lang = e.target.value;
  localStorage.setItem("gitgui.lang", S.lang);
  loadI18n();
};
$("#cred-btn").onclick = () => { renderCredTable(); $("#cred-modal").classList.remove("hidden"); };
$("#cred-close").onclick = () => $("#cred-modal").classList.add("hidden");
$("#cred-save").onclick = async () => {
  await api("/credentials/set", { method: "POST", body: JSON.stringify({
    protocol: $("#cred-proto").value, host: $("#cred-host").value,
    username: $("#cred-user").value, password: $("#cred-pass").value,
  })});
  renderCredTable();
};
async function renderCredTable() {
  try {
    const data = await api("/credentials");
    const tbl = $("#cred-table");
    tbl.innerHTML = `<tr><th>${esc(t("ui.protocol"))}</th><th>${esc(t("ui.host"))}</th><th>${esc(t("ui.username"))}</th><th></th></tr>`;
    for (const c of data.credentials) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${esc(c.protocol)}</td><td>${esc(c.host)}</td><td>${esc(c.username)}</td>`;
      const td = document.createElement("td");
      const del = document.createElement("button");
      del.className = "danger"; del.textContent = t("ui.delete");
      del.onclick = async () => { await api("/credentials/delete", { method: "POST", body: JSON.stringify({ protocol: c.protocol, host: c.host }) }); renderCredTable(); };
      td.appendChild(del);
      tr.appendChild(td);
      tbl.appendChild(tr);
    }
  } catch (e) { /* ignore */ }
}

$("#repo-add-btn").onclick = () => { $("#browse-path").value = S.repo || ""; browseList(S.repo || ""); $("#browse-modal").classList.remove("hidden"); };
$("#browse-close").onclick = () => $("#browse-modal").classList.add("hidden");
$("#browse-go").onclick = () => browseList($("#browse-path").value);
$("#browse-up").onclick = () => { const d = $("#browse-path").value; $("#browse-path").value = d.replace(/\/[^/]*\/?$/, "") || "/"; browseList($("#browse-path").value); };
$("#browse-select").onclick = async () => {
  const p = $("#browse-path").value;
  await api("/repos/add", { method: "POST", body: JSON.stringify({ path: p }) });
  $("#browse-modal").classList.add("hidden");
  await loadRepos();
  $("#repo-select").value = p;
  $("#repo-select").onchange({ target: { value: p } });
};
async function browseList(path) {
  try {
    const r = await api("/fs/list", { method: "POST", body: JSON.stringify({ path }) });
    $("#browse-path").value = r.path;
    const ul = $("#browse-list");
    ul.innerHTML = "";
    for (const d of r.dirs) {
      const li = document.createElement("li");
      li.textContent = d;
      li.onclick = () => browseList(r.path.replace(/\/$/, "") + "/" + d.replace(/\/$/, ""));
      ul.appendChild(li);
    }
  } catch (e) {
    $("#browse-list").innerHTML = `<li>${esc(e.message)}</li>`;
  }
}

(async function init() {
  await loadMeta();
  await loadI18n();
  await loadRepos();
  await loadWorkflows();
  await loadCatalog();
})();
