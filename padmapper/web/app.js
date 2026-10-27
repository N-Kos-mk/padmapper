"use strict";

// padmapper の設定画面。サーバー (padmapper/server.py) の API を呼び、変更はその場で保存・反映する。

const token = new URLSearchParams(location.search).get("token") || "";
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const clone = (v) => structuredClone(v);
const isEmpty = (o) => !o || Object.keys(o).length === 0;
const fmt = (v) => (Number.isInteger(v) ? String(v) : String(Number(v.toFixed(2))));

const BUTTON_LABELS = {
  A: "A", B: "B", X: "X", Y: "Y", LB: "LB", RB: "RB", LT: "LT", RT: "RT",
  BACK: "Back", START: "Start", GUIDE: "Guide", LS: "左スティック押し込み", RS: "右スティック押し込み",
  UP: "十字キー 上", DOWN: "十字キー 下", LEFT: "十字キー 左", RIGHT: "十字キー 右",
  LS_UP: "左スティック 上", LS_DOWN: "左スティック 下", LS_LEFT: "左スティック 左", LS_RIGHT: "左スティック 右",
  RS_UP: "右スティック 上", RS_DOWN: "右スティック 下", RS_LEFT: "右スティック 左", RS_RIGHT: "右スティック 右",
};
const BUTTON_GROUPS = [
  ["フェイスボタン", ["A", "B", "X", "Y"]],
  ["ショルダー・トリガー", ["LB", "RB", "LT", "RT"]],
  ["十字キー", ["UP", "DOWN", "LEFT", "RIGHT"]],
  ["その他", ["BACK", "START", "GUIDE", "LS", "RS"]],
  ["スティックの方向（スティックを「方向ボタン」にしたとき）", ["LS_UP", "LS_DOWN", "LS_LEFT", "LS_RIGHT", "RS_UP", "RS_DOWN", "RS_LEFT", "RS_RIGHT"]],
];
const KIND_LABELS = {
  same: "通常と同じ", none: "なし", key: "キー", mouse: "マウスボタン", wheel: "ホイール",
  layer: "レイヤー（押している間）", layer_toggle: "レイヤー（切り替え）", profile: "プロファイル切り替え",
};
const MOUSE_LABELS = { left: "左クリック", right: "右クリック", middle: "中クリック", x1: "戻るボタン (X1)", x2: "進むボタン (X2)" };
const WHEEL_LABELS = { up: "上へスクロール", down: "下へスクロール", left: "左へスクロール", right: "右へスクロール" };
const MODE_LABELS = { none: "使わない", mouse: "カーソル", scroll: "スクロール", buttons: "方向ボタン" };
const MODE_HINTS = {
  none: "変換しません。ゲームやエミュレーターにはそのまま届きます。",
  mouse: "倒した方向にカーソルが動きます。",
  scroll: "倒した方向にスクロールします。",
  buttons: "倒した方向をボタンとして扱います。ボタンタブの「スティックの方向」で割り当てます。",
};
const SPECIAL_KEYS = [
  "win", "apps", "printscreen", "volume_up", "volume_down", "volume_mute",
  "media_play_pause", "media_next", "media_prev", "media_stop", "browser_back", "browser_forward", "browser_refresh",
];
const KEY_DISPLAY = {
  ctrl: "Ctrl", shift: "Shift", alt: "Alt", win: "Win", rwin: "右Win", enter: "Enter", esc: "Esc", tab: "Tab",
  space: "Space", backspace: "BackSpace", delete: "Delete", insert: "Insert", home: "Home", end: "End",
  pageup: "PageUp", pagedown: "PageDown", up: "↑", down: "↓", left: "←", right: "→",
  lctrl: "左Ctrl", rctrl: "右Ctrl", lshift: "左Shift", rshift: "右Shift", lalt: "左Alt", ralt: "右Alt",
  volume_up: "音量+", volume_down: "音量-", volume_mute: "ミュート", media_play_pause: "再生/一時停止",
  media_next: "次の曲", media_prev: "前の曲", media_stop: "停止", browser_back: "ブラウザの戻る",
  browser_forward: "ブラウザの進む", browser_refresh: "ブラウザの更新", apps: "アプリケーションキー",
  printscreen: "PrintScreen", capslock: "CapsLock", convert: "変換", nonconvert: "無変換",
};

const ui = {
  data: null, // GET /api/profiles の内容
  live: null, // /api/stream の最新状態
  selected: null, // 編集中のプロファイル
  tab: "buttons", // buttons | sticks | apps
  layer: "", // 編集中のレイヤー ("" は通常)
  button: "A", // 編集中のボタン
  draft: null, // 値が決まる前の割り当て { btn, layer, kind, arg, repeat }
  stickDraft: {}, // スライダー操作中の値 (保存前のプレビュー用)
  capture: null, // キーボード入力の記録中 { order, down }
  apps: null, // 起動中のアプリ
  lastManual: undefined,
  logTimer: null,
};

// 通信

async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: { "X-Token": token, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let json = {};
  try {
    json = await res.json();
  } catch {
    // 本文が JSON でない場合はステータスだけで判断する
  }
  if (!res.ok) throw new Error(json.error || `${res.status} ${res.statusText}`);
  return json;
}

function toast(message, kind = "ok") {
  const el = $("#toast");
  el.textContent = message;
  el.className = `toast show ${kind}`;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (el.className = "toast"), kind === "error" ? 6000 : 1500);
}

// 保存は順番に行う。変更内容は実行する時点の最新の設定から作るので、連続した変更が失われない
let saving = Promise.resolve();
function enqueueSave(request) {
  saving = saving.then(async () => {
    try {
      const result = await request();
      if (result) {
        ui.data = result;
        toast("保存しました");
      }
    } catch (e) {
      toast(e.message, "error");
    }
    render();
  });
  return saving;
}

function saveConfig(patch) {
  return enqueueSave(() => api("PUT", "/api/config", { raw: { ...ui.data.config, ...patch } }));
}

// プロファイルの内容

const profile = () => ui.data.profiles[ui.selected];
const profileNames = () => Object.keys(ui.data.profiles).sort((a, b) => a.localeCompare(b));
const layerNames = () => Object.keys(profile().merged.layers || {});

function parentMerged(name = ui.selected) {
  const parent = ui.data.profiles[name].raw.inherit;
  return (parent && ui.data.profiles[parent]?.merged) || {};
}

function buttonsOf(obj, layer = ui.layer) {
  return (layer ? obj.layers?.[layer]?.buttons : obj.buttons) || {};
}

function parseBinding(value) {
  if (value === undefined) return null;
  let action = value;
  let repeat = false;
  if (typeof value === "object") {
    action = value.do;
    repeat = !!value.repeat;
  }
  if (action === "none") return { kind: "none", arg: "", repeat: false };
  const i = action.indexOf(":");
  return { kind: action.slice(0, i), arg: action.slice(i + 1), repeat };
}

function makeBinding(kind, arg, repeat) {
  if (kind === "none") return "none";
  const action = `${kind}:${arg}`;
  return repeat ? { do: action, repeat: true } : action;
}

function keyLabel(key) {
  let k = key.trim().toLowerCase();
  k = ui.data.schema.aliases[k] || k;
  if (KEY_DISPLAY[k]) return KEY_DISPLAY[k];
  return k.length === 1 ? k.toUpperCase() : k.charAt(0).toUpperCase() + k.slice(1);
}

function keysHtml(text) {
  if (!text) return `<span class="muted">未設定</span>`;
  return text.split("+").map((k) => `<kbd>${esc(keyLabel(k))}</kbd>`).join("<span>+</span>");
}

function validKeys(text) {
  const parts = text.split("+").map((s) => s.trim().toLowerCase());
  const { keys, aliases } = ui.data.schema;
  return parts.length > 0 && parts.every((p) => /^0x[0-9a-f]{1,2}$/.test(p) || p in keys || p in aliases);
}

function describeBinding(b) {
  if (!b) return "未割り当て";
  const rep = b.repeat ? "（連続入力）" : "";
  switch (b.kind) {
    case "none": return "なし";
    case "key": return b.arg.split("+").map(keyLabel).join(" + ") + rep;
    case "mouse": return MOUSE_LABELS[b.arg] || b.arg;
    case "wheel": return (WHEEL_LABELS[b.arg] || b.arg) + rep;
    case "layer": return `レイヤー「${b.arg}」（押している間）`;
    case "layer_toggle": return `レイヤー「${b.arg}」を切り替え`;
    case "profile": return b.arg === "auto" ? "プロファイルを自動に戻す" : `プロファイル「${b.arg}」に固定`;
    default: return b.kind;
  }
}

// ボタンの割り当てがどこから来ているか
function bindingInfo(btn, layer = ui.layer) {
  const p = profile();
  const own = buttonsOf(p.raw, layer)[btn];
  const merged = buttonsOf(p.merged, layer)[btn];
  const parent = buttonsOf(parentMerged(), layer)[btn];
  if (merged !== undefined) return { own, parent, value: merged, source: own !== undefined ? "own" : "inherit" };
  if (layer) {
    const base = buttonsOf(p.merged, "")[btn];
    if (base !== undefined) return { own, parent, value: base, source: "base" };
  }
  return { own, parent, value: undefined, source: "empty" };
}

// 編集欄に表示する割り当て (値の決まっていない draft を優先)
function editorState() {
  const btn = ui.button;
  const info = bindingInfo(btn);
  const draft = ui.draft && ui.draft.btn === btn && ui.draft.layer === ui.layer ? ui.draft : null;
  if (draft) return { info, kind: draft.kind, arg: draft.arg, repeat: draft.repeat };
  const b = parseBinding(info.value);
  const kind = info.source === "base" ? "same" : b ? b.kind : "none";
  return { info, kind, arg: b?.arg ?? "", repeat: b?.repeat ?? false };
}

function ensure(obj, ...path) {
  let o = obj;
  for (const k of path) {
    if (typeof o[k] !== "object" || o[k] === null || Array.isArray(o[k])) o[k] = {};
    o = o[k];
  }
  return o;
}

// 空になったテーブルを消す。レイヤー自体とレイヤーのスティック設定は、空でも意味があるので残す
function prune(raw) {
  for (const k of ["settings", "buttons"]) if (raw[k] && isEmpty(raw[k])) delete raw[k];
  if (raw.sticks) {
    for (const side of Object.keys(raw.sticks)) if (isEmpty(raw.sticks[side])) delete raw.sticks[side];
    if (isEmpty(raw.sticks)) delete raw.sticks;
  }
  if (raw.layers) {
    for (const layer of Object.values(raw.layers)) {
      if (layer.buttons && isEmpty(layer.buttons)) delete layer.buttons;
      if (layer.sticks && isEmpty(layer.sticks)) delete layer.sticks;
    }
    if (isEmpty(raw.layers)) delete raw.layers;
  }
  if (raw.match && raw.match.length === 0) delete raw.match;
}

function mutate(fn, name = ui.selected) {
  return enqueueSave(() => {
    if (!ui.data.profiles[name]) return null;
    const raw = clone(ui.data.profiles[name].raw);
    fn(raw);
    prune(raw);
    return api("PUT", `/api/profiles/${encodeURIComponent(name)}`, { raw });
  });
}

function setBinding(btn, value) {
  ui.draft = null;
  ui.capture = null;
  const layer = ui.layer;
  return mutate((raw) => {
    if (value === undefined) {
      const table = layer ? raw.layers?.[layer]?.buttons : raw.buttons;
      if (table) delete table[btn];
    } else {
      (layer ? ensure(raw, "layers", layer, "buttons") : ensure(raw, "buttons"))[btn] = value;
    }
  });
}

// 「なし」: 継承元や通常レイヤーに割り当てがあれば打ち消す必要がある
function clearBinding(btn) {
  const info = bindingInfo(btn);
  const shadowed = info.parent !== undefined || (ui.layer && bindingInfo(btn, "").value !== undefined);
  return setBinding(btn, shadowed ? "none" : undefined);
}

function setStickField(side, key, value) {
  delete ui.stickDraft[side];
  const layer = ui.layer;
  return mutate((raw) => {
    (layer ? ensure(raw, "layers", layer, "sticks", side) : ensure(raw, "sticks", side))[key] = value;
  });
}

function stickValues(side, layer = ui.layer) {
  const p = profile();
  const base = { ...ui.data.schema.stick_defaults, ...(p.merged.sticks?.[side] || {}) };
  if (!layer) return base;
  return { ...base, ...(p.merged.layers?.[layer]?.sticks?.[side] || {}) };
}

// 描画

function icons() {
  if (window.lucide) window.lucide.createIcons();
}

function render() {
  if (!ui.data) return;
  if (!ui.selected || !ui.data.profiles[ui.selected]) {
    const live = ui.live?.profile;
    ui.selected = live && ui.data.profiles[live] ? live : ui.data.config.default_profile;
  }
  if (ui.layer && !layerNames().includes(ui.layer)) ui.layer = "";
  renderSidebar();
  renderMain();
  icons();
  updateLive();
}

function renderSidebar() {
  const def = ui.data.config.default_profile;
  $("#profile-list").innerHTML = profileNames()
    .map((name) => {
      const raw = ui.data.profiles[name].raw;
      const tags = [];
      if (name === def) tags.push(`<span class="tag">既定</span>`);
      if (raw.match?.length) tags.push(`<span class="tag subtle">アプリ ${raw.match.length}</span>`);
      return `<li><button class="profile-item ${name === ui.selected ? "active" : ""}" data-profile="${esc(name)}">
        <span class="pi-top"><span class="live-dot" data-live-profile="${esc(name)}" title="使用中"></span>
        <span class="pi-name">${esc(name)}</span>${tags.join("")}</span>
        <span class="pi-desc">${esc(raw.description || "")}</span></button></li>`;
    })
    .join("");
}

function renderMain() {
  const main = $("#main");
  const scroll = main.scrollTop;
  const name = ui.selected;
  const raw = profile().raw;
  const pinned = ui.live?.manual === name;
  const tabs = [
    ["buttons", "ボタン", "gamepad-2"],
    ["sticks", "スティック・感度", "move"],
    ["apps", "対象アプリ・基本設定", "app-window"],
  ];
  const body = ui.tab === "buttons" ? renderButtonsTab() : ui.tab === "sticks" ? renderSticksTab() : renderAppsTab();
  main.innerHTML = `
    <section class="profile-head">
      <div>
        <h1>${esc(name)}</h1>
        <p class="muted">${esc(raw.description || "説明はありません")}</p>
        <div class="head-tags">
          ${raw.inherit ? `<span class="tag subtle"><i data-lucide="git-branch"></i>${esc(raw.inherit)} を継承</span>` : ""}
          ${name === ui.data.config.default_profile ? `<span class="tag">既定のプロファイル</span>` : ""}
        </div>
      </div>
      <div class="head-actions">
        <button class="btn ${pinned ? "primary" : ""}" data-action="pin" title="前面のアプリに関係なく、このプロファイルを使います">
          <i data-lucide="${pinned ? "pin-off" : "pin"}"></i>${pinned ? "固定を解除" : "このプロファイルで試す"}</button>
        <button class="btn" data-action="duplicate"><i data-lucide="copy"></i>複製</button>
        <button class="btn danger" data-action="delete"><i data-lucide="trash-2"></i>削除</button>
      </div>
    </section>
    <nav class="tabs">${tabs
      .map(([id, label, icon]) => `<button class="tab ${ui.tab === id ? "active" : ""}" data-tab="${id}"><i data-lucide="${icon}"></i>${label}</button>`)
      .join("")}</nav>
    ${body}`;
  main.scrollTop = scroll;
}

function renderLayerBar() {
  const p = profile();
  const own = Object.keys(p.raw.layers || {});
  const inherited = Object.keys(parentMerged().layers || {});
  let del = "";
  if (ui.layer && own.includes(ui.layer)) {
    const label = inherited.includes(ui.layer) ? "このプロファイルでの変更を消す" : "このレイヤーを削除";
    del = `<button class="btn ghost small danger" data-action="delete-layer"><i data-lucide="trash-2"></i>${label}</button>`;
  }
  return `<div class="layer-bar">
      <span class="bar-label"><i data-lucide="layers"></i>レイヤー</span>
      <button class="chip-btn ${ui.layer === "" ? "active" : ""}" data-layer="">通常</button>
      ${layerNames().map((l) => `<button class="chip-btn ${ui.layer === l ? "active" : ""}" data-layer="${esc(l)}">${esc(l)}</button>`).join("")}
      <button class="btn ghost small" data-action="add-layer"><i data-lucide="plus"></i>追加</button>
      ${del}
    </div>
    ${ui.layer ? `<p class="hint">${layerHint(ui.layer)}</p>` : ""}`;
}

function layerHint(layer) {
  const triggers = [];
  for (const btn of ui.data.schema.buttons) {
    const b = parseBinding(buttonsOf(profile().merged, "")[btn]);
    if (b && (b.kind === "layer" || b.kind === "layer_toggle") && b.arg === layer) {
      triggers.push(`${BUTTON_LABELS[btn]}（${b.kind === "layer" ? "押している間" : "押すたびに切り替え"}）`);
    }
  }
  const how = triggers.length
    ? `${triggers.join("、")}で有効になります。`
    : "まだどのボタンからも使われていません。通常レイヤーでボタンの動作を「レイヤー」にすると使えます。";
  return `レイヤー「${esc(layer)}」は${how}ここで割り当てていないボタンは、通常の割り当てのまま動きます。`;
}

// ボタンタブ

function renderButtonsTab() {
  return `${renderLayerBar()}
    <div class="pad-layout">
      <div class="card">${padSvg()}
        <p class="hint center">図のボタンをクリックして選びます。実機のボタンを押すと光ります。<br>
        この画面が前面にある間は変換を止めているので、コントローラーを押しても入力は送られません。割り当てを試すときは、試したいアプリを前面にしてください。</p>
      </div>
      <div class="card">${renderEditor()}</div>
    </div>
    <div class="card">${renderBindingList()}</div>`;
}

function padClass(btn) {
  const b = parseBinding(bindingInfo(btn).value);
  return `${b && b.kind !== "none" ? "assigned" : ""} ${ui.button === btn ? "selected" : ""}`;
}

function padSvg() {
  const g = (btn, inner) => {
    const title = `${BUTTON_LABELS[btn]}: ${describeBinding(parseBinding(bindingInfo(btn).value))}`;
    return `<g class="pbtn ${padClass(btn)}" data-btn="${btn}"><title>${esc(title)}</title>${inner}</g>`;
  };
  const face = (btn, cx, cy) => g(btn, `<circle cx="${cx}" cy="${cy}" r="17"/><text class="face-${btn}" x="${cx}" y="${cy + 5}">${btn}</text>`);
  return `<svg class="pad" viewBox="0 0 600 350" role="img" aria-label="コントローラーの図">
    <path class="pad-body" d="M150 96 C108 96 82 118 68 156 L34 262 C22 302 44 338 80 338 C104 338 120 324 134 304 L170 260 L430 260 L466 304 C480 324 496 338 520 338 C556 338 578 302 566 262 L532 156 C518 118 492 96 450 96 Z"/>
    ${g("LT", `<rect x="112" y="14" width="96" height="38" rx="12"/><rect class="fill" data-fill="lt" x="112" y="14" width="0" height="38" rx="12"/><text x="160" y="39">LT</text>`)}
    ${g("RT", `<rect x="392" y="14" width="96" height="38" rx="12"/><rect class="fill" data-fill="rt" x="392" y="14" width="0" height="38" rx="12"/><text x="440" y="39">RT</text>`)}
    ${g("LB", `<rect x="104" y="62" width="124" height="26" rx="13"/><text x="166" y="80">LB</text>`)}
    ${g("RB", `<rect x="372" y="62" width="124" height="26" rx="13"/><text x="434" y="80">RB</text>`)}
    <circle class="stick-well" cx="178" cy="160" r="38"/>
    ${g("LS", `<circle cx="178" cy="160" r="22"/><text x="178" y="165">L</text>`)}
    <circle class="stick-well" cx="362" cy="214" r="38"/>
    ${g("RS", `<circle cx="362" cy="214" r="22"/><text x="362" y="219">R</text>`)}
    <rect class="dpad-center" x="226" y="202" width="24" height="24"/>
    ${g("UP", `<rect x="226" y="176" width="24" height="27" rx="4"/>`)}
    ${g("DOWN", `<rect x="226" y="225" width="24" height="27" rx="4"/>`)}
    ${g("LEFT", `<rect x="199" y="202" width="28" height="24" rx="4"/>`)}
    ${g("RIGHT", `<rect x="249" y="202" width="28" height="24" rx="4"/>`)}
    ${g("BACK", `<rect x="255" y="142" width="30" height="16" rx="8"/>`)}
    ${g("START", `<rect x="315" y="142" width="30" height="16" rx="8"/>`)}
    ${g("GUIDE", `<circle cx="300" cy="116" r="17"/>`)}
    ${face("Y", 444, 122)}${face("X", 408, 158)}${face("B", 480, 158)}${face("A", 444, 194)}
  </svg>`;
}

function renderEditor() {
  const btn = ui.button;
  const { info, kind, arg, repeat } = editorState();
  const kinds = [...(ui.layer ? ["same"] : []), "none", "key", "mouse", "wheel", "layer", "layer_toggle", "profile"];
  const source = {
    own: "このプロファイルで設定",
    inherit: `${esc(profile().raw.inherit || "")} から継承`,
    base: "通常と同じ",
    empty: "未割り当て",
  }[info.source];
  const reset =
    info.source === "own" && info.parent !== undefined
      ? `<button class="btn ghost small" data-action="reset-binding"><i data-lucide="rotate-ccw"></i>継承元の設定に戻す</button>`
      : "";
  return `<div class="editor-head"><h2>${esc(BUTTON_LABELS[btn])}</h2><span class="tag subtle">${source}</span></div>
    <label class="field-label">動作</label>
    <div class="kind-grid">${kinds
      .map((k) => `<button class="kind ${k === kind ? "active" : ""}" data-kind="${k}">${KIND_LABELS[k]}</button>`)
      .join("")}</div>
    ${renderKindFields(kind, arg, repeat)}
    <div class="row">${reset}</div>`;
}

function options(labels, current) {
  return Object.entries(labels)
    .map(([v, label]) => `<option value="${esc(v)}" ${v === current ? "selected" : ""}>${esc(label)}</option>`)
    .join("");
}

function repeatBox(repeat) {
  return `<label class="check"><input type="checkbox" id="repeat" ${repeat ? "checked" : ""}>押し続けると連続で入力する</label>`;
}

function renderKindFields(kind, arg, repeat) {
  switch (kind) {
    case "same":
      return `<p class="hint">通常レイヤーの割り当て（${esc(describeBinding(parseBinding(bindingInfo(ui.button, "").value)))}）がそのまま使われます。</p>`;
    case "none":
      return `<p class="hint">押しても何も送りません。ゲームやエミュレーターには、コントローラーの入力がそのまま届きます。</p>`;
    case "key":
      return `<label class="field-label" for="key-text">キー（同時押しは + でつなぐ）</label>
        <div class="key-row">
          <input id="key-text" class="input mono" value="${esc(arg)}" placeholder="例: ctrl+shift+s" spellcheck="false" autocomplete="off">
          <button class="btn ${ui.capture ? "primary" : ""}" data-action="capture"><i data-lucide="keyboard"></i>${ui.capture ? "入力待ち（クリックで中止）" : "キーボードで入力"}</button>
        </div>
        <div class="key-preview" id="key-preview">${keysHtml(arg)}</div>
        <p class="hint">「キーボードで入力」を押してから、割り当てたいキーを押してください。同時押しは押したまま次のキーを押します。Win キーとの組み合わせなど、Windows が先に受け取るキーは下の一覧か手入力で指定します。</p>
        <label class="field-label" for="key-special">特殊キーから選ぶ</label>
        <select id="key-special" class="input"><option value="">選択してください</option>${SPECIAL_KEYS.map((k) => `<option value="${k}">${esc(keyLabel(k))}</option>`).join("")}</select>
        ${repeatBox(repeat)}`;
    case "mouse":
      return `<label class="field-label" for="arg-select">ボタン</label><select id="arg-select" class="input">${options(MOUSE_LABELS, arg)}</select>`;
    case "wheel":
      return `<label class="field-label" for="arg-select">方向</label><select id="arg-select" class="input">${options(WHEEL_LABELS, arg)}</select>${repeatBox(repeat)}`;
    case "layer":
    case "layer_toggle": {
      const layers = layerNames();
      const placeholder = arg ? "" : `<option value="" selected>${layers.length ? "選択してください" : "レイヤーがありません"}</option>`;
      return `<label class="field-label" for="arg-select">レイヤー</label>
        <select id="arg-select" class="input">${placeholder}${layers
          .map((l) => `<option value="${esc(l)}" ${l === arg ? "selected" : ""}>${esc(l)}</option>`)
          .join("")}<option value="__new__">新しいレイヤーを作る…</option></select>
        <p class="hint">${kind === "layer" ? "押している間だけ、レイヤーの割り当てが有効になります。" : "押すたびに、レイヤーの有効/無効が切り替わります。"}</p>`;
    }
    case "profile":
      return `<label class="field-label" for="arg-select">切り替え先</label>
        <select id="arg-select" class="input"><option value="auto" ${arg === "auto" ? "selected" : ""}>自動（前面のアプリに合わせる）</option>${profileNames()
          .map((n) => `<option value="${esc(n)}" ${n === arg ? "selected" : ""}>${esc(n)}</option>`)
          .join("")}</select>
        <p class="hint">押すとプロファイルを固定します。「自動」を割り当てたボタンを押すと固定が解除されます。</p>`;
    default:
      return "";
  }
}

function renderBindingList() {
  return BUTTON_GROUPS.map(
    ([title, buttons]) => `<div class="list-group"><h3>${title}</h3>${buttons
      .map((btn) => {
        const info = bindingInfo(btn);
        const b = parseBinding(info.value);
        const badge = { own: "", inherit: `<span class="tag subtle">継承</span>`, base: `<span class="tag subtle">通常と同じ</span>`, empty: "" }[info.source];
        return `<button class="bind-row ${ui.button === btn ? "active" : ""}" data-btn="${btn}">
          <span class="bind-name">${esc(BUTTON_LABELS[btn])}</span>
          <span class="bind-value ${b && b.kind !== "none" ? "" : "muted"}">${esc(describeBinding(b))}</span>${badge}</button>`;
      })
      .join("")}</div>`
  ).join("");
}

function chooseKind(kind) {
  const btn = ui.button;
  const state = editorState();
  if (kind === state.kind && !ui.draft) return;
  ui.capture = null;
  if (kind === "same") return setBinding(btn, undefined);
  if (kind === "none") return clearBinding(btn);
  const otherLayers = layerNames().filter((l) => l !== ui.layer);
  const defaults = { mouse: "left", wheel: "down", profile: "auto", layer: otherLayers[0], layer_toggle: otherLayers[0] };
  if (defaults[kind]) return setBinding(btn, makeBinding(kind, defaults[kind], false));
  ui.draft = { btn, layer: ui.layer, kind, arg: "", repeat: false };
  if (kind === "key") ui.capture = { order: [], down: new Set() };
  render();
}

// キーボード入力の記録

function vkName(code) {
  return ui.data.schema.key_names[String(code)] || `0x${code.toString(16).padStart(2, "0")}`;
}

function finishCapture() {
  const keys = ui.capture.order.join("+");
  ui.capture = null;
  const { kind, repeat } = editorState();
  setBinding(ui.button, makeBinding("key", keys, kind === "key" && repeat));
}

function onCaptureKey(e) {
  if (!ui.capture) return;
  e.preventDefault();
  e.stopPropagation();
  if (e.type === "keydown") {
    if (e.keyCode === 229) {
      toast("日本語入力 (IME) をオフにしてから押してください", "error");
      return;
    }
    const name = vkName(e.keyCode);
    if (!ui.capture.order.includes(name)) ui.capture.order.push(name);
    ui.capture.down.add(name);
    const preview = $("#key-preview");
    if (preview) preview.innerHTML = keysHtml(ui.capture.order.join("+"));
  } else {
    ui.capture.down.delete(vkName(e.keyCode));
    if (ui.capture.down.size === 0 && ui.capture.order.length) finishCapture();
  }
}

// スティックタブ

function renderSticksTab() {
  return `${renderLayerBar()}<div class="stick-grid">${renderStickCard("left")}${renderStickCard("right")}</div>`;
}

function slider(side, key, label, value, min, max, step, unit = "") {
  return `<div class="slider"><div class="slider-head"><span>${label}</span><output data-out="${side}-${key}" data-unit="${unit}">${fmt(value)}${unit}</output></div>
    <input type="range" min="${min}" max="${max}" step="${step}" value="${value}" data-stick-num="${key}" data-side="${side}"></div>`;
}

function curvePoints(v) {
  const pts = [];
  for (let i = 0; i <= 48; i++) {
    const m = i / 48;
    const out = m <= v.deadzone ? 0 : Math.min(1, (m - v.deadzone) / (1 - v.deadzone)) ** v.curve;
    pts.push(`${(10 + m * 100).toFixed(1)},${(110 - out * 100).toFixed(1)}`);
  }
  return pts.join(" ");
}

function renderStickCard(side) {
  const v = { ...stickValues(side), ...(ui.stickDraft[side] || {}) };
  const p = profile();
  const own = ui.layer ? p.raw.layers?.[ui.layer]?.sticks?.[side] : p.raw.sticks?.[side];
  const overridden = !ui.layer || p.merged.layers?.[ui.layer]?.sticks?.[side] !== undefined;
  const inheritedOnly = ui.layer && overridden && own === undefined;
  const analog = v.mode === "mouse" || v.mode === "scroll";
  const speed = v.mode === "scroll" ? [1, 60, 1, " ノッチ/秒"] : [100, 4000, 50, " px/秒"];
  const badge = own !== undefined ? "このプロファイルで設定" : ui.layer ? (overridden ? "継承" : "通常と同じ") : "継承";
  const parentHas = ui.layer
    ? parentMerged().layers?.[ui.layer]?.sticks?.[side] !== undefined
    : !isEmpty(parentMerged().sticks?.[side]);
  const reset =
    !ui.layer && own !== undefined
      ? `<button class="btn ghost small" data-action="reset-stick" data-side="${side}"><i data-lucide="rotate-ccw"></i>${parentHas ? "継承元の設定に戻す" : "初期値に戻す"}</button>`
      : "";
  return `<div class="card">
    <div class="editor-head"><h2>${side === "left" ? "左スティック" : "右スティック"}</h2><span class="tag subtle">${badge}</span></div>
    ${ui.layer ? `<label class="check"><input type="checkbox" data-stick-override="${side}" ${overridden ? "checked" : ""} ${inheritedOnly ? "disabled" : ""}>このレイヤーでは設定を変える</label>` : ""}
    <fieldset ${overridden ? "" : "disabled"}>
      <label class="field-label">使い方</label>
      <div class="seg">${Object.keys(MODE_LABELS)
        .map((m) => `<button class="seg-btn ${v.mode === m ? "active" : ""}" data-stick-mode="${m}" data-side="${side}">${MODE_LABELS[m]}</button>`)
        .join("")}</div>
      <p class="hint">${MODE_HINTS[v.mode]}</p>
      <div class="stick-visual">
        <svg viewBox="-70 -70 140 140" aria-label="スティックの位置">
          <circle class="pos-ring" r="60"/>
          <circle class="pos-dz" r="${60 * v.deadzone}" data-pos-dz="${side}"/>
          ${v.mode === "buttons" ? `<rect class="pos-th" x="${-60 * v.threshold}" y="${-60 * v.threshold}" width="${120 * v.threshold}" height="${120 * v.threshold}" data-pos-th="${side}"/>` : ""}
          <circle class="pos-dot" r="6" data-pos-dot="${side}"/>
        </svg>
        ${analog ? `<svg viewBox="0 0 120 124" aria-label="反応カーブ">
          <rect class="curve-bg" x="10" y="10" width="100" height="100"/>
          <rect class="curve-dz" x="10" y="10" width="${100 * v.deadzone}" height="100" data-curve-dz="${side}"/>
          <polyline class="curve-line" points="${curvePoints(v)}" data-curve-line="${side}"/>
          <circle class="curve-dot" r="3.5" cx="10" cy="110" data-curve-dot="${side}"/>
          <text class="curve-label" x="60" y="122" text-anchor="middle">倒した量</text>
          <text class="curve-label" x="6" y="60" text-anchor="middle" transform="rotate(-90 6 60)">出力</text>
        </svg>` : ""}
      </div>
      ${analog ? slider(side, "speed", "速さ（最大まで倒したとき）", v.speed, ...speed) : ""}
      ${v.mode !== "none" ? slider(side, "deadzone", "デッドゾーン（反応しない範囲）", v.deadzone, 0, 0.5, 0.01) : ""}
      ${analog ? slider(side, "curve", "カーブ（大きいほど、少し倒したときに細かく動く）", v.curve, 0.5, 4, 0.1) : ""}
      ${v.mode === "buttons" ? slider(side, "threshold", "押したとみなす倒し具合", v.threshold, 0.1, 0.95, 0.05) : ""}
      ${v.mode !== "none" ? `<label class="check"><input type="checkbox" data-stick-bool="axis_lock" data-side="${side}" ${v.axis_lock ? "checked" : ""}>軸固定（縦横のうち強く倒したほうだけを使う）</label>` : ""}
      ${analog ? `<label class="check"><input type="checkbox" data-stick-bool="invert_y" data-side="${side}" ${v.invert_y ? "checked" : ""}>上下を反転する</label>` : ""}
    </fieldset>
    <div class="row">${reset}</div>
  </div>`;
}

function updateStickPreview(side) {
  const v = { ...stickValues(side), ...(ui.stickDraft[side] || {}) };
  $(`[data-pos-dz="${side}"]`)?.setAttribute("r", 60 * v.deadzone);
  const th = $(`[data-pos-th="${side}"]`);
  if (th) {
    th.setAttribute("x", -60 * v.threshold);
    th.setAttribute("y", -60 * v.threshold);
    th.setAttribute("width", 120 * v.threshold);
    th.setAttribute("height", 120 * v.threshold);
  }
  $(`[data-curve-dz="${side}"]`)?.setAttribute("width", 100 * v.deadzone);
  $(`[data-curve-line="${side}"]`)?.setAttribute("points", curvePoints(v));
}

function toggleStickOverride(side, on) {
  const layer = ui.layer;
  return mutate((raw) => {
    if (on) ensure(raw, "layers", layer, "sticks", side);
    else if (raw.layers?.[layer]?.sticks) delete raw.layers[layer].sticks[side];
  });
}

// 対象アプリ・基本設定タブ

function settingSlider(key, label, value, min, max, step) {
  return `<div class="slider"><div class="slider-head"><span>${label}</span><output data-out="setting-${key}" data-unit="">${fmt(value)}</output></div>
    <input type="range" min="${min}" max="${max}" step="${step}" value="${value}" data-setting="${key}"></div>`;
}

function renderAppsTab() {
  const p = profile();
  const raw = p.raw;
  const name = ui.selected;
  const s = { ...ui.data.schema.settings_defaults, ...(p.merged.settings || {}) };
  const others = profileNames().filter((n) => n !== name);
  const matches = raw.match || [];
  const apps = (ui.apps || [])
    .map((a) => {
      const exe = a.path.split(/[\\/]/).pop();
      return `<option value="${esc(exe)}">${esc(exe)} - ${esc(a.title)}</option>`;
    })
    .join("");
  return `<div class="card">
      <h2>基本</h2>
      <label class="field-label" for="desc">説明</label>
      <input id="desc" class="input" value="${esc(raw.description || "")}" placeholder="例: melonDS 用。右スティックでタッチ">
      <label class="field-label" for="inherit">継承元</label>
      <select id="inherit" class="input"><option value="">なし</option>${others
        .map((n) => `<option value="${esc(n)}" ${raw.inherit === n ? "selected" : ""}>${esc(n)}</option>`)
        .join("")}</select>
      <p class="hint">継承元の割り当てと感度を引き継ぎ、このプロファイルで変更した項目だけが上書きされます。</p>
    </div>
    <div class="card">
      <h2>対象アプリ</h2>
      <p class="hint">${name === ui.data.config.default_profile ? "このプロファイルは既定です。どの対象アプリにも当てはまらないときに使われます。<br>" : ""}
        前面のアプリが次のどれかに当てはまると、このプロファイルに自動で切り替わります。実行ファイル名（例: melonDS.exe）か、
        フォルダを含むパス（例: D:/Games/*）で指定します。* は任意の文字列です。実行ファイル名での指定が優先されます。</p>
      <ul class="match-list">${
        matches.length
          ? matches.map((m, i) => `<li><code>${esc(m)}</code><button class="icon-only" data-action="remove-match" data-index="${i}" title="削除"><i data-lucide="x"></i></button></li>`).join("")
          : `<li class="muted">まだありません</li>`
      }</ul>
      <div class="row">
        <select id="app-pick" class="input"><option value="">${ui.apps ? "起動中のアプリから追加…" : "読み込み中…"}</option>${apps}</select>
        <button class="btn" data-action="refresh-apps"><i data-lucide="refresh-cw"></i>更新</button>
      </div>
      <div class="row">
        <input id="match-text" class="input mono" placeholder="手入力（例: game.exe）" spellcheck="false">
        <button class="btn" data-action="add-match"><i data-lucide="plus"></i>追加</button>
      </div>
    </div>
    <div class="card">
      <h2>入力の細かい設定</h2>
      ${settingSlider("trigger_threshold", "LT/RT を押したとみなす押し込み量", s.trigger_threshold, 0.05, 0.95, 0.05)}
      ${settingSlider("repeat_delay", "連続入力が始まるまでの時間（秒）", s.repeat_delay, 0.1, 1.5, 0.05)}
      ${settingSlider("repeat_rate", "連続入力の速さ（回/秒）", s.repeat_rate, 5, 60, 1)}
      ${settingSlider("scroll_step", "スクロールを送る細かさ（120 でホイール 1 目盛り）", s.scroll_step, 10, 120, 10)}
    </div>`;
}

async function loadApps() {
  try {
    ui.apps = (await api("GET", "/api/apps")).apps;
  } catch (e) {
    toast(e.message, "error");
    ui.apps = [];
  }
  if (ui.tab === "apps") render();
}

function addMatch(pattern) {
  pattern = pattern.trim();
  if (!pattern) return;
  if ((profile().raw.match || []).includes(pattern)) {
    toast("既に追加されています", "error");
    return;
  }
  return mutate((raw) => {
    raw.match = [...(raw.match || []), pattern];
  });
}

// ダイアログ

function showDialog(html, wide = false) {
  const dlg = $("#dialog");
  dlg.className = `dialog ${wide ? "wide" : ""}`;
  dlg.innerHTML = html;
  if (!dlg.open) dlg.showModal();
  icons();
}

function closeDialog() {
  const dlg = $("#dialog");
  if (dlg.open) dlg.close();
}

// 1 行入力のダイアログ。キャンセルなら null
function askText(title, placeholder, hint) {
  return new Promise((resolve) => {
    showDialog(`<h2>${esc(title)}</h2>
      <input id="ask-text" class="input" placeholder="${esc(placeholder)}" autocomplete="off">
      <p class="hint">${esc(hint)}</p>
      <div class="dialog-actions"><button class="btn" id="ask-cancel">キャンセル</button><button class="btn primary" id="ask-ok">OK</button></div>`);
    const input = $("#ask-text");
    const finish = (value) => {
      closeDialog();
      resolve(value);
    };
    $("#ask-ok").onclick = () => finish(input.value.trim() || null);
    $("#ask-cancel").onclick = () => finish(null);
    input.onkeydown = (e) => {
      if (e.key === "Enter") finish(input.value.trim() || null);
    };
    $("#dialog").onclose = () => resolve(null);
    input.focus();
  });
}

function openNewProfile(copyFrom = "") {
  const names = profileNames();
  showDialog(`<h2>プロファイルを作成</h2>
    <label class="field-label" for="new-name">名前</label>
    <input id="new-name" class="input" placeholder="例: genshin" autocomplete="off" value="${copyFrom ? esc(`${copyFrom}-copy`) : ""}">
    <p class="hint">文字・数字・_・- が使えます（40 文字まで）。ファイル名にもなります。</p>
    <label class="field-label" for="new-from">元にする設定</label>
    <select id="new-from" class="input">
      <option value="">空のプロファイル${ui.data.profiles.base ? "（base を継承）" : ""}</option>
      ${names.map((n) => `<option value="${esc(n)}" ${n === copyFrom ? "selected" : ""}>${esc(n)} を複製</option>`).join("")}
    </select>
    <p class="hint">複製では対象アプリは引き継ぎません（同じアプリに 2 つのプロファイルが当たらないように）。</p>
    <div class="dialog-actions"><button class="btn" data-action="close-dialog">キャンセル</button><button class="btn primary" data-action="create-profile">作成</button></div>`);
  $("#new-name").focus();
}

async function createProfile() {
  const name = $("#new-name").value.trim();
  const copyFrom = $("#new-from").value || null;
  try {
    ui.data = await api("POST", "/api/profiles", { name, copy_from: copyFrom });
    ui.selected = name;
    ui.layer = "";
    closeDialog();
    toast("作成しました");
    render();
  } catch (e) {
    toast(e.message, "error");
  }
}

async function deleteProfile() {
  const name = ui.selected;
  if (!confirm(`プロファイル「${name}」を削除しますか？\n（backup フォルダに控えが残ります）`)) return;
  try {
    ui.data = await api("DELETE", `/api/profiles/${encodeURIComponent(name)}`);
    ui.selected = null;
    toast("削除しました");
    render();
  } catch (e) {
    toast(e.message, "error");
  }
}

function cfgSelect(key, choices) {
  const current = String(ui.data.config[key]);
  return `<select class="input" data-cfg="${key}">${choices
    .map(([v, label]) => `<option value="${esc(v)}" ${String(v) === current ? "selected" : ""}>${esc(label)}</option>`)
    .join("")}</select>`;
}

function openGlobal() {
  const c = ui.data.config;
  const comboButtons = ui.data.schema.buttons.filter((b) => !b.includes("_"));
  showDialog(`<h2>全体設定</h2>
    <label class="field-label">既定のプロファイル</label>
    ${cfgSelect("default_profile", profileNames().map((n) => [n, n]))}
    <p class="hint">どのプロファイルの対象アプリにも当てはまらないときに使います。</p>
    <label class="check"><input type="checkbox" data-cfg-bool="start_enabled" ${c.start_enabled ? "checked" : ""}>起動したときに変換を有効にする</label>
    <label class="field-label">変換の有効/無効を切り替える同時押し</label>
    <div class="combo-grid">${comboButtons
      .map((b) => `<label class="check small"><input type="checkbox" data-combo="${b}" ${c.toggle_combo.includes(b) ? "checked" : ""}>${esc(BUTTON_LABELS[b])}</label>`)
      .join("")}</div>
    <div class="slider"><div class="slider-head"><span>長押しの時間（秒）</span><output data-out="cfg-toggle_hold" data-unit="">${fmt(c.toggle_hold)}</output></div>
      <input type="range" min="0.3" max="3" step="0.1" value="${c.toggle_hold}" data-cfg-num="toggle_hold"></div>
    <label class="field-label">カーソルの動かし方</label>
    ${cfgSelect("mouse_mode", [["cursor", "カーソルの位置を直接動かす（推奨）"], ["relative", "マウスの移動として送る（マウス操作のゲーム向け）"]])}
    <label class="field-label">読み取り頻度</label>
    ${cfgSelect("poll_hz", [[125, "125 回/秒"], [250, "250 回/秒"], [500, "500 回/秒（推奨）"], [1000, "1000 回/秒"]])}
    <label class="field-label">使うコントローラー</label>
    ${cfgSelect("pad", [[-1, "自動（最初に見つかったもの）"], [0, "スロット 0"], [1, "スロット 1"], [2, "スロット 2"], [3, "スロット 3"]])}
    <div class="dialog-actions"><button class="btn" data-action="close-dialog">閉じる</button></div>`);
}

async function refreshLogs() {
  const view = $("#log-view");
  if (!view) return;
  try {
    const { lines } = await api("GET", "/api/logs");
    const atBottom = view.scrollTop + view.clientHeight >= view.scrollHeight - 4;
    view.textContent = lines.join("\n") || "（ログはありません）";
    if (atBottom) view.scrollTop = view.scrollHeight;
  } catch (e) {
    view.textContent = e.message;
  }
}

function openLogs() {
  showDialog(`<h2>ログ</h2><pre class="log-view" id="log-view"></pre>
    <div class="dialog-actions"><button class="btn" data-action="close-dialog">閉じる</button></div>`, true);
  refreshLogs();
  clearInterval(ui.logTimer);
  ui.logTimer = setInterval(refreshLogs, 1000);
  $("#dialog").onclose = () => clearInterval(ui.logTimer);
}

// 実機の状態の表示

function updateLive() {
  const s = ui.live;
  if (!s || !ui.data) return;
  const conn = $("#st-conn");
  conn.className = `chip ${s.connected ? "ok" : "warn"}`;
  conn.lastElementChild.textContent = s.connected ? "コントローラー接続中" : "コントローラー未接続";
  $("#st-profile").lastElementChild.textContent = `使用中: ${s.profile}${s.manual ? "（固定）" : ""}${s.layers.length ? ` / レイヤー ${s.layers.join(", ")}` : ""}`;
  $("#st-fg").lastElementChild.textContent = `直前のアプリ: ${s.foreground ? s.foreground.split(/[\\/]/).pop() : "-"}`;
  $("#enabled").checked = s.enabled;
  $("#enabled-label").textContent = s.enabled ? "変換 有効" : "変換 停止中";
  $("#st-suspend").hidden = !(s.enabled && s.suspended);
  for (const el of $$("[data-live-profile]")) el.classList.toggle("on", el.dataset.liveProfile === s.profile);

  const pressed = new Set(s.pressed);
  for (const el of $$(".pad [data-btn]")) el.classList.toggle("pressed", pressed.has(el.dataset.btn));
  const a = s.axes || { lt: 0, rt: 0, lx: 0, ly: 0, rx: 0, ry: 0 };
  $('.pad [data-btn="LS"]')?.setAttribute("transform", `translate(${(a.lx * 14).toFixed(1)} ${(-a.ly * 14).toFixed(1)})`);
  $('.pad [data-btn="RS"]')?.setAttribute("transform", `translate(${(a.rx * 14).toFixed(1)} ${(-a.ry * 14).toFixed(1)})`);
  $('[data-fill="lt"]')?.setAttribute("width", (96 * a.lt).toFixed(1));
  $('[data-fill="rt"]')?.setAttribute("width", (96 * a.rt).toFixed(1));
  for (const [side, x, y] of [["left", a.lx, a.ly], ["right", a.rx, a.ry]]) {
    const dot = $(`[data-pos-dot="${side}"]`);
    if (dot) {
      dot.setAttribute("cx", (x * 60).toFixed(1));
      dot.setAttribute("cy", (-y * 60).toFixed(1));
    }
    const cdot = $(`[data-curve-dot="${side}"]`);
    if (cdot) {
      const v = { ...stickValues(side), ...(ui.stickDraft[side] || {}) };
      const m = Math.min(1, Math.hypot(x, y));
      const out = m <= v.deadzone ? 0 : Math.min(1, (m - v.deadzone) / (1 - v.deadzone)) ** v.curve;
      cdot.setAttribute("cx", (10 + m * 100).toFixed(1));
      cdot.setAttribute("cy", (110 - out * 100).toFixed(1));
    }
  }
  // 固定状態が変わったら見出しのボタンを描き直す
  if (s.manual !== ui.lastManual) {
    ui.lastManual = s.manual;
    renderMain();
    icons();
  }
}

function connectStream() {
  const es = new EventSource(`/api/stream?token=${encodeURIComponent(token)}`);
  es.onmessage = (e) => {
    ui.live = JSON.parse(e.data);
    $("#offline").hidden = true;
    updateLive();
  };
  es.onerror = () => {
    $("#offline").hidden = false;
  };
}

// イベント

async function onClick(e) {
  const t = e.target.closest("[data-profile],[data-tab],[data-layer],[data-btn],[data-kind],[data-stick-mode],[data-action]");
  if (!t || t.disabled) return;
  const d = t.dataset;
  if (d.profile !== undefined) {
    Object.assign(ui, { selected: d.profile, layer: "", draft: null, stickDraft: {}, capture: null });
    return render();
  }
  if (d.tab) {
    ui.tab = d.tab;
    if (ui.tab === "apps" && !ui.apps) loadApps();
    return render();
  }
  if (d.layer !== undefined) {
    Object.assign(ui, { layer: d.layer, draft: null, stickDraft: {}, capture: null });
    return render();
  }
  if (d.btn) {
    Object.assign(ui, { button: d.btn, draft: null, capture: null });
    return render();
  }
  if (d.kind) return chooseKind(d.kind);
  if (d.stickMode) return setStickField(d.side, "mode", d.stickMode);

  switch (d.action) {
    case "pin": {
      const pinned = ui.live?.manual === ui.selected;
      try {
        ui.live = await api("POST", "/api/manual", { name: pinned ? null : ui.selected });
        updateLive();
      } catch (err) {
        toast(err.message, "error");
      }
      return;
    }
    case "duplicate": return openNewProfile(ui.selected);
    case "delete": return deleteProfile();
    case "new-profile": return openNewProfile();
    case "create-profile": return createProfile();
    case "global": return openGlobal();
    case "logs": return openLogs();
    case "close-dialog": return closeDialog();
    case "add-layer": {
      const name = await askText("レイヤーを追加", "例: fn", "名前は自由です（例: fn, touch）。追加したら、通常レイヤーでボタンの動作を「レイヤー」にして使います。");
      if (!name) return;
      if (layerNames().includes(name)) return toast("同じ名前のレイヤーがあります", "error");
      await mutate((raw) => ensure(raw, "layers", name));
      ui.layer = name;
      return render();
    }
    case "delete-layer": {
      const layer = ui.layer;
      const inherited = Object.keys(parentMerged().layers || {}).includes(layer);
      if (!confirm(inherited ? `レイヤー「${layer}」へのこのプロファイルでの変更を消しますか？` : `レイヤー「${layer}」を削除しますか？\nこのレイヤーを使うボタンの割り当ても外れます。`)) return;
      ui.layer = "";
      return mutate((raw) => {
        delete raw.layers[layer];
        if (inherited) return;
        const strip = (table) => {
          for (const [btn, value] of Object.entries(table || {})) {
            const b = parseBinding(value);
            if (b && (b.kind === "layer" || b.kind === "layer_toggle") && b.arg === layer) delete table[btn];
          }
        };
        strip(raw.buttons);
        for (const l of Object.values(raw.layers || {})) strip(l.buttons);
      });
    }
    case "capture":
      ui.capture = ui.capture ? null : { order: [], down: new Set() };
      if (ui.capture && editorState().kind !== "key") {
        ui.draft = { btn: ui.button, layer: ui.layer, kind: "key", arg: "", repeat: false };
      }
      return render();
    case "reset-binding": return setBinding(ui.button, undefined);
    case "reset-stick":
      return mutate((raw) => {
        if (raw.sticks) delete raw.sticks[d.side];
      });
    case "remove-match":
      return mutate((raw) => {
        raw.match.splice(Number(d.index), 1);
      });
    case "add-match": return addMatch($("#match-text").value);
    case "refresh-apps":
      ui.apps = null;
      render();
      return loadApps();
    default:
  }
}

function onChange(e) {
  const t = e.target;
  const d = t.dataset;
  if (t.id === "enabled") {
    api("POST", "/api/enabled", { enabled: t.checked })
      .then((s) => {
        ui.live = s;
        updateLive();
      })
      .catch((err) => toast(err.message, "error"));
    return;
  }
  if (t.id === "key-text") {
    const keys = t.value.trim().toLowerCase().replace(/\s+/g, "");
    if (!keys) return;
    if (!validKeys(keys)) {
      $("#key-error").innerHTML = `<span class="error">「${esc(t.value)}」には使えないキー名が含まれています。</span>`;
      return;
    }
    return setBinding(ui.button, makeBinding("key", keys, editorState().repeat));
  }
  if (t.id === "key-special" && t.value) return setBinding(ui.button, makeBinding("key", t.value, editorState().repeat));
  if (t.id === "arg-select") {
    const { kind, repeat } = editorState();
    if (t.value === "__new__") return addLayerAndBind(kind);
    if (t.value) return setBinding(ui.button, makeBinding(kind, t.value, repeat));
    return;
  }
  if (t.id === "repeat") {
    const { kind, arg } = editorState();
    if (arg) return setBinding(ui.button, makeBinding(kind, arg, t.checked));
    if (ui.draft) ui.draft.repeat = t.checked;
    return;
  }
  if (d.stickNum) return setStickField(d.side, d.stickNum, Number(t.value));
  if (d.stickBool) return setStickField(d.side, d.stickBool, t.checked);
  if (d.stickOverride) return toggleStickOverride(d.stickOverride, t.checked);
  if (d.setting) {
    return mutate((raw) => {
      ensure(raw, "settings")[d.setting] = Number(t.value);
    });
  }
  if (t.id === "desc") {
    return mutate((raw) => {
      if (t.value.trim()) raw.description = t.value.trim();
      else delete raw.description;
    });
  }
  if (t.id === "inherit") {
    return mutate((raw) => {
      if (t.value) raw.inherit = t.value;
      else delete raw.inherit;
    });
  }
  if (t.id === "app-pick" && t.value) return addMatch(t.value);
  if (d.cfg) {
    const numeric = ["poll_hz", "pad"].includes(d.cfg);
    return saveConfig({ [d.cfg]: numeric ? Number(t.value) : t.value });
  }
  if (d.cfgBool) return saveConfig({ [d.cfgBool]: t.checked });
  if (d.cfgNum) return saveConfig({ [d.cfgNum]: Number(t.value) });
  if (d.combo) {
    const combo = $$("[data-combo]").filter((el) => el.checked).map((el) => el.dataset.combo);
    return saveConfig({ toggle_combo: combo });
  }
}

function onInput(e) {
  const t = e.target;
  const d = t.dataset;
  if (t.type !== "range") return;
  const key = d.stickNum ? `${d.side}-${d.stickNum}` : d.setting ? `setting-${d.setting}` : d.cfgNum ? `cfg-${d.cfgNum}` : null;
  const out = key && $(`[data-out="${key}"]`);
  if (out) out.textContent = fmt(Number(t.value)) + (out.dataset.unit || "");
  if (d.stickNum) {
    (ui.stickDraft[d.side] ||= {})[d.stickNum] = Number(t.value);
    updateStickPreview(d.side);
  }
}

async function addLayerAndBind(kind) {
  const name = await askText("レイヤーを追加", "例: fn", "追加したレイヤーを、このボタンに割り当てます。");
  if (!name) return render();
  if (layerNames().includes(name)) {
    toast("同じ名前のレイヤーがあります", "error");
    return render();
  }
  const btn = ui.button;
  const layer = ui.layer;
  ui.draft = null;
  return mutate((raw) => {
    ensure(raw, "layers", name);
    (layer ? ensure(raw, "layers", layer, "buttons") : ensure(raw, "buttons"))[btn] = makeBinding(kind, name, false);
  });
}

async function init() {
  document.addEventListener("click", onClick);
  document.addEventListener("change", onChange);
  document.addEventListener("input", onInput);
  window.addEventListener("keydown", onCaptureKey, true);
  window.addEventListener("keyup", onCaptureKey, true);
  window.addEventListener("blur", () => {
    if (ui.capture?.order.length) finishCapture();
  });
  icons();
  if (!token) {
    $("#main").innerHTML = `<div class="empty">トレイアイコンから設定画面を開いてください。</div>`;
    return;
  }
  try {
    ui.data = await api("GET", "/api/profiles");
    ui.live = await api("GET", "/api/state");
  } catch (e) {
    $("#main").innerHTML = `<div class="empty">${esc(e.message)}</div>`;
    return;
  }
  ui.selected = ui.live.profile;
  ui.lastManual = ui.live.manual;
  render();
  connectStream();
}

init();
