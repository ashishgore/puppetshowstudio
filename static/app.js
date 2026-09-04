const $ = (id) => document.getElementById(id);

let CONFIG = null;
let VOICES = [];
let LINES = [];
let POLL = null;

const SAMPLE = `Bansi: गाँववालों! आज पंचायत में एक बहुत ही सीरियस केस आया है। [sfx_before:dholak_hit]
Phoolwati: केस है — नेहा और अभय के पच्चीस साल की शादी का! [sfx:tadaa] [pause:0.35]
Bansi: पच्चीस साल हो गए... और दोनों अभी भी एक ही घर में रह रहे हैं। [laugh:chuckle] [pause:0.3]
Phoolwati: तो पंचायत को लगा... कुछ तो राज़ है! [sfx:dun_dun_duun] [laugh:medium] [cutaway:कुछ तो राज़ है...?] [pause:0.55]
Bansi: इसलिए नेहा जी और अभय जी को पंचायत के सामने बुलाया जाता है।
Phoolwati: और वार्निंग — यहाँ झूठ बोलना मना है। [laugh:chuckle] [pause:0.3]
Bansi: एस्पेशियली नेहा के सामने। क्योंकि उसको दो हज़ार आठ में किसने क्या बोला था... वो भी याद है! [laugh:applause] [sfx:rimshot] [cutaway:पंचायत स्पेशल] [cutaway_sub:25 साल की कहानी] [cutaway_style:title] [pause:0.6]`;

// ------------------------------------------------------------------- config

async function loadConfig() {
  CONFIG = await (await fetch("/api/config")).json();
  renderVoiceRows();
  $("keyHint").textContent = CONFIG.api_key_set
    ? `Key saved (${CONFIG.api_key_hint}). Stored locally in config.json — only ever sent to ElevenLabs.`
    : "Stored locally in config.json on this machine. Never sent anywhere except ElevenLabs.";
  const intro = CONFIG.intro || {};
  $("optIntro").checked = !!intro.enabled;
  $("introPath").value = intro.path || "";
  $("introSecs").value = intro.seconds != null ? intro.seconds : 13;
  const film = CONFIG.film || {};
  $("optFilm").checked = !!film.enabled;
  $("filmStrength").value = film.strength != null ? film.strength : 0.85;
  $("filmStrengthVal").textContent = $("filmStrength").value;
  $("stability").value = CONFIG.stability;
  $("similarity").value = CONFIG.similarity;
  $("style").value = CONFIG.style;
  if (!CONFIG.api_key_set) $("settings").hidden = false;
}

async function saveConfig(body) {
  await fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  await loadConfig();
}

function renderVoiceRows() {
  const wrap = $("voiceRows");
  wrap.innerHTML = "";
  for (const ch of CONFIG.characters) {
    if (ch.voice === false) continue;   // "Both" borrows the other two voices
    const row = document.createElement("div");
    row.className = "voice-row";
    const saved = (CONFIG.voice_ids || {})[ch.id] || "";

    const left = document.createElement("div");
    left.innerHTML = `<div class="who">${ch.name}</div><div class="blurb">${ch.blurb}</div>`;

    const right = document.createElement("div");

    // Always a free-text field: any voice ID can be pasted, whether or not the
    // voice list loaded. When it did load, the datalist turns the same field
    // into a pick-by-name dropdown without ever locking out manual entry.
    const inp = document.createElement("input");
    inp.type = "text";
    inp.setAttribute("list", `voicelist-${ch.id}`);
    inp.placeholder = VOICES.length
      ? "pick a voice, or paste any voice ID"
      : "paste a voice ID, or click “Load my voices”";
    inp.value = saved;

    const named = document.createElement("div");
    named.className = "voice-named";
    const showName = () => {
      const hit = VOICES.find(v => v.voice_id === inp.value.trim());
      named.textContent = hit ? hit.name : (inp.value.trim() ? "custom ID" : "");
    };
    showName();
    inp.onchange = () => {
      saveConfig({ voice_ids: { [ch.id]: inp.value.trim() } });
      showName();
    };

    const list = document.createElement("datalist");
    list.id = `voicelist-${ch.id}`;
    list.innerHTML = VOICES.map(v => {
      const bits = [v.gender, v.age, v.accent].filter(Boolean).join(" · ");
      return `<option value="${v.voice_id}">${v.name}${bits ? " — " + bits : ""}</option>`;
    }).join("");

    right.append(inp, list, named);

    row.append(left, right);
    wrap.appendChild(row);
  }
}

// -------------------------------------------------------------- line editor

function laughOptions(selected) {
  const opts = [`<option value="">— none —</option>`].concat(
    (CONFIG.laughs || []).map(l => `<option value="${l.id}"${l.id === selected ? " selected" : ""}>${l.label}</option>`)
  );
  return opts.join("");
}

function autoHoldFor(laughId) {
  const l = (CONFIG.laughs || []).find(x => x.id === laughId);
  return l ? l.hold : 0;
}

function sfxOptions(selected) {
  const opts = [`<option value="">— none —</option>`].concat(
    (CONFIG.sfx || []).map(s => `<option value="${s.id}"${s.id === selected ? " selected" : ""}>${s.label}</option>`)
  );
  return opts.join("");
}

function renderLines() {
  const tb = document.querySelector("#linesTable tbody");
  tb.innerHTML = "";
  LINES.forEach((line, i) => {
    // a scene heading shows as its own band above the line it introduces,
    // so it is obvious where the chapter cards fall
    if (line.scene_title) {
      const st = document.createElement("tr");
      st.className = "scene-row";
      const td = document.createElement("td");
      td.colSpan = 9;
      td.textContent = (line.scene_kicker ? line.scene_kicker + " — " : "") + line.scene_title;
      st.appendChild(td);
      tb.appendChild(st);
    }

    const tr = document.createElement("tr");

    const num = document.createElement("td");
    num.className = "rownum";
    num.textContent = i + 1;

    const spk = document.createElement("td");
    const sel = document.createElement("select");
    sel.innerHTML = CONFIG.characters
      .map(c => `<option value="${c.id}"${c.id === line.speaker ? " selected" : ""}>${c.name}</option>`)
      .join("");
    sel.onchange = () => { line.speaker = sel.value; };
    spk.appendChild(sel);

    const txt = document.createElement("td");
    const ti = document.createElement("input");
    ti.type = "text";
    ti.value = line.text;
    ti.oninput = () => { line.text = ti.value; };
    txt.appendChild(ti);

    const sfx = document.createElement("td");
    const ss = document.createElement("select");
    ss.innerHTML = sfxOptions(line.sfx_after);
    ss.onchange = () => { line.sfx_after = ss.value; };
    sfx.appendChild(ss);

    const lau = document.createElement("td");
    const ls = document.createElement("select");
    ls.innerHTML = laughOptions(line.laugh);
    lau.appendChild(ls);

    const hold = document.createElement("td");
    const hi = document.createElement("input");
    hi.type = "number"; hi.step = "0.1"; hi.min = "0"; hi.max = "5";
    hi.value = line.hold_before != null ? line.hold_before : "";
    // blank means "use the default for this laugh" -- show that default as
    // the placeholder so the timing is visible without having to type it
    const syncHoldHint = () => {
      hi.placeholder = autoHoldFor(ls.value) ? `${autoHoldFor(ls.value)} auto` : "—";
    };
    syncHoldHint();
    hi.oninput = () => {
      line.hold_before = hi.value === "" ? null : parseFloat(hi.value);
    };
    ls.onchange = () => { line.laugh = ls.value; syncHoldHint(); };
    hold.appendChild(hi);

    const pause = document.createElement("td");
    const pi = document.createElement("input");
    pi.type = "number"; pi.step = "0.05"; pi.min = "0"; pi.max = "5";
    pi.value = line.pause_after;
    pi.oninput = () => { line.pause_after = parseFloat(pi.value || "0"); };
    pause.appendChild(pi);

    const cut = document.createElement("td");
    const ci = document.createElement("input");
    ci.type = "text";
    ci.placeholder = "— none —";
    ci.value = line.cutaway_text || "";
    ci.oninput = () => { line.cutaway_text = ci.value; };
    cut.appendChild(ci);

    const del = document.createElement("td");
    const db = document.createElement("button");
    db.className = "del"; db.textContent = "×"; db.title = "Remove line";
    db.onclick = () => { LINES.splice(i, 1); renderLines(); };
    del.appendChild(db);

    tr.append(num, spk, txt, sfx, lau, hold, pause, cut, del);
    tb.appendChild(tr);
  });

  $("lineCount").textContent = LINES.length ? `(${LINES.length})` : "";
  $("linesCard").hidden = LINES.length === 0;
  $("generateCard").hidden = LINES.length === 0;
}

// ---------------------------------------------------------------- generate

async function generate() {
  const btn = $("btnGenerate");
  btn.disabled = true;
  $("resultWrap").hidden = true;
  $("progressWrap").hidden = false;
  $("progressLog").className = "log";
  $("progressLog").textContent = "";
  setProgress(0, "Starting…");

  const body = {
    lines: LINES,
    options: {
      subtitles: $("optSubtitles").checked,
      upscale_1080: $("opt1080").checked,
      offline: $("optOffline").checked,
      fps: 24,
    },
  };

  const res = await (await fetch("/api/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })).json();

  if (!res.ok) {
    setProgress(0, res.error || "Could not start.");
    $("progressLog").className = "log error";
    $("progressLog").textContent = res.error || "";
    btn.disabled = false;
    return;
  }
  pollJob(res.job_id);
}

function setProgress(pct, msg) {
  $("bar").style.width = `${pct}%`;
  $("progressMsg").textContent = msg;
}

function pollJob(jobId) {
  clearInterval(POLL);
  POLL = setInterval(async () => {
    const s = await (await fetch(`/api/status/${jobId}`)).json();
    if (!s.ok) return;
    setProgress(s.pct, s.message);
    $("progressLog").textContent = (s.log || []).join("\n");
    $("progressLog").scrollTop = $("progressLog").scrollHeight;

    if (s.status === "done") {
      clearInterval(POLL);
      $("btnGenerate").disabled = false;
      $("resultVideo").src = `/api/video/${jobId}?t=${Date.now()}`;
      $("btnDownload").href = `/api/download/${jobId}`;
      $("resultWrap").hidden = false;
    } else if (s.status === "error") {
      clearInterval(POLL);
      $("btnGenerate").disabled = false;
      $("progressLog").className = "log error";
    }
  }, 1200);
}

// -------------------------------------------------------------------- wiring

$("btnSettings").onclick = () => { $("settings").hidden = !$("settings").hidden; };

$("btnSaveKey").onclick = async () => {
  const v = $("apiKey").value.trim();
  if (!v) return;
  await saveConfig({ api_key: v });
  $("apiKey").value = "";
};

$("optFilm").onchange = () => saveConfig({ film: { enabled: $("optFilm").checked } });
$("filmStrength").oninput = () => { $("filmStrengthVal").textContent = $("filmStrength").value; };
$("filmStrength").onchange = () => saveConfig({ film: { strength: parseFloat($("filmStrength").value) } });

$("optIntro").onchange = () => saveConfig({ intro: { enabled: $("optIntro").checked } });
$("introPath").onchange = () => saveConfig({ intro: { path: $("introPath").value } });
$("introSecs").onchange = () => saveConfig({ intro: { seconds: parseFloat($("introSecs").value || "13") } });

$("btnLoadVoices").onclick = async (e) => {
  const btn = e.target;
  btn.disabled = true; btn.textContent = "Loading…";
  const res = await (await fetch("/api/voices")).json();
  btn.disabled = false; btn.textContent = "Load my voices";
  if (!res.ok) { alert(res.error); return; }
  VOICES = res.voices || [];
  renderVoiceRows();
};

$("btnSaveTuning").onclick = () => saveConfig({
  stability: parseFloat($("stability").value),
  similarity: parseFloat($("similarity").value),
  style: parseFloat($("style").value),
});

$("btnSample").onclick = () => { $("scriptBox").value = SAMPLE; };

$("btnParse").onclick = async () => {
  const res = await (await fetch("/api/parse", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ script: $("scriptBox").value }),
  })).json();
  LINES = res.lines || [];
  renderLines();
  if (LINES.length) $("linesCard").scrollIntoView({ behavior: "smooth", block: "start" });
};

$("btnAddLine").onclick = () => {
  LINES.push({
    speaker: "bansi", text: "", sfx_before: "", sfx_after: "",
    laugh: "", hold_before: null, scene_title: "", scene_kicker: "",
    pause_after: 0.25, cutaway_text: "", cutaway_subtext: "", cutaway_style: "reveal",
  });
  renderLines();
};

$("btnGenerate").onclick = generate;
$("btnAgain").onclick = () => {
  $("resultWrap").hidden = true;
  $("progressWrap").hidden = true;
  window.scrollTo({ top: 0, behavior: "smooth" });
};

$("optOffline").onchange = (e) => {
  $("genNote").textContent = e.target.checked
    ? "Preview mode uses a local placeholder voice — no ElevenLabs credits used."
    : "";
};

(async function init() {
  await loadConfig();
  const h = await (await fetch("/api/health")).json();
  if (!h.ffmpeg) $("ffmpegWarn").hidden = false;
})();
