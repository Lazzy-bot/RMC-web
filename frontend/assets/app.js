/* ============================================================
   RMC Report Assistant — app.js
   ============================================================ */

const API = window.location.origin;

/* ── State ─────────────────────────────────────────────────── */
const state = {
  authenticated: false,
  appInitialized: false,
  currentUser: null,
  isAdmin: false,
  currentGroup:  "AEONMALL",
  originalReportText: "",   // luu noi dung bao cao goc, khong bi ghi de boi Contact/Status
  clockRunning:  true,
  clockInterval: null,
  countdownSec:  300,
  countdownJob:  null,
  countdownRunning: false,
  boxFilled:     [false, false, false, false, false, false],
  currentSiteKey: null,
  currentFileId:  null,
  currentFileName: null,
  sitesData:      {},         // {AEONMALL: {ANVL: ..., ATQB: ...}, ...}
  notesList:      [],
  activeSiteBtn:  null,
  activeItemBtn:  null,
  currentAdminTplItems: [],
  currentAdminTplSiteKey: null,
  chartInstances: {},
  needsRefresh: false,
  graphAuthenticated: false,
  siteKeyMap: {},         // name -> code
  pics: [],               // list of PIC names
  editingNoteStt: null,   // STT of note being edited, null if creating
  noteTimeTags: [],       // list of times (strings) for the note form
  userEmails: [],         // list of {name, email} for the note form
};

/* ── Helpers ────────────────────────────────────────────────── */
function $(sel, ctx = document) { return ctx.querySelector(sel); }
function $$(sel, ctx = document) { return [...ctx.querySelectorAll(sel)]; }

async function apiFetch(path, opts = {}) {
  const url = new URL(API + path);
  url.searchParams.set("_t", Date.now()); // Cache buster

  // Timeout mặc định: 30s cho mọi request (trừ khi caller cung cấp signal riêng)
  // Các tác vụ nặng (ghi Excel, sync) dùng timeout dài hơn qua opts.timeout
  const timeoutMs = opts.timeout ?? 60000;
  delete opts.timeout; // Xóa để không truyền vào fetch

  // Nếu caller đã cung cấp signal riêng (ví dụ notification poller), ưu tiên dùng nó
  // Nếu không, tự tạo AbortController với timeout
  let controller = null;
  let timeoutId  = null;
  let signal     = opts.signal ?? null;

  if (!signal) {
    controller = new AbortController();
    signal     = controller.signal;
    timeoutId  = setTimeout(() => controller.abort(), timeoutMs);
  }

  try {
    const res = await fetch(url, {
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      ...opts,
      signal,
    });

    let data = null;
    try {
      data = await res.json();
    } catch {
      data = null;
    }

    if (!res.ok) {
      const err = new Error((data && data.error) ? data.error : `HTTP ${res.status}`);
      err.status = res.status;
      err.data = data;
      throw err;
    }

    return data;
  } catch (err) {
    // Chuyển AbortError thành thông báo dễ hiểu hơn
    if (err.name === "AbortError") {
      const timeoutErr = new Error("Yêu cầu quá thời gian chờ. Vui lòng kiểm tra kết nối hoặc thử lại.");
      timeoutErr.name  = "TimeoutError";
      timeoutErr.isTimeout = true;
      throw timeoutErr;
    }
    throw err;
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
  }
}

function showToast(title, message, duration = 5000) {
  const wrap = $("#toast-container");
  const el = document.createElement("div");
  el.className = "toast";
  el.innerHTML = `<div class="toast-title">${title}</div>${message}`;
  wrap.appendChild(el);
  setTimeout(() => el.remove(), duration);
}

function copyToClipboard(text) {
  navigator.clipboard.writeText(text).then(() => showToast("Đã copy", "Nội dung đã được sao chép vào clipboard."));
}

/* ── Login / Auth ─────────────────────────────────────────── */
function bindAuthButtons() {
  const ms = $("#btn-login-microsoft");
  const gg = $("#btn-login-google");

  if (ms) ms.onclick = () => { window.location.href = "/api/auth/login/microsoft"; };
  if (gg) gg.onclick = () => { window.location.href = "/api/auth/login/google"; };
}

function applyProviderAvailability(providers = []) {
  const setEnabled = (id, providerName) => {
    const btn = $(id);
    if (!btn) return;
    const enabled = providers.includes(providerName);
    btn.disabled = !enabled;
    btn.title = enabled ? "" : "Provider này chưa được cấu hình ở backend";
  };

  setEnabled("#btn-login-microsoft", "microsoft");
  setEnabled("#btn-login-google", "google");

  if (!providers.length) {
    showLoginScreen(
      "Chưa cấu hình đăng nhập OAuth",
      "Admin cần cấu hình MS_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_ID trong Docker .env rồi khởi động lại container."
    );
  }
}

function showLoginScreen(statusText, hintText = "") {
  $("#login-screen").classList.remove("hidden");
  if (statusText) $("#login-status").textContent = statusText;
  if (hintText) $("#login-hint").textContent = hintText;
}

function handleAuthQueryHint() {
  const params = new URLSearchParams(window.location.search);
  const auth = params.get("auth");
  if (!auth) return;

  if (auth === "success") showToast("Đăng nhập thành công", "Bạn đã đăng nhập hệ thống.");
  if (auth === "pending") showToast("Đang chờ duyệt", "Tài khoản của bạn đang chờ admin phê duyệt.");
  if (auth === "failed") showToast("Đăng nhập thất bại", "Không thể xác thực tài khoản.");
  if (auth === "provider_not_configured") showToast("Thiếu cấu hình", "Provider đăng nhập chưa được cấu hình ở backend.");

  history.replaceState({}, document.title, window.location.pathname);
}

async function checkAuth() {
  try {
    const res = await apiFetch("/api/auth/me", { timeout: 15000 });
    applyProviderAvailability(res.providers || []);

    if (!res.logged_in) {
      showLoginScreen("Chưa đăng nhập", "Nếu bạn là user mới, đăng nhập một lần để tạo tài khoản chờ duyệt.");
      return;
    }

    if (!res.can_access) {
      const email = res.user ? res.user.email : "";
      showLoginScreen(
        "Tài khoản đang chờ admin phê duyệt",
        `Vui lòng liên hệ admin để được cấp quyền truy cập cho email: ${email}`
      );
      return;
    }

    state.graphAuthenticated = !!res.graph_authenticated;
    onAuthSuccess(res.user);
  } catch (err) {
    if (err.isTimeout || err.name === "TimeoutError") {
      showLoginScreen("⚠️ Quá thời gian kết nối", "Server không phản hồi. Vui lòng tải lại trang.");
    } else {
      showLoginScreen("Không thể kết nối backend.");
    }
  }
}

function onAuthSuccess(user) {
  state.authenticated = true;
  state.currentUser = user || null;
  state.isAdmin = !!user && user.role === "admin";

  $("#login-screen").classList.add("hidden");
  $("#auth-badge").classList.add("ok");
  $("#auth-badge .label").textContent = state.isAdmin ? "Admin" : "Đã đăng nhập";

  const authUser = $("#auth-user");
  if (authUser && user) {
    authUser.textContent = `${user.name || "User"} (${user.email || ""})`;
    authUser.classList.remove("hidden");
  }

  $("#btn-logout")?.classList.remove("hidden");
  if (state.isAdmin) $("#btn-admin")?.classList.remove("hidden");

  if (!state.appInitialized) {
    state.appInitialized = true;
    initApp();
  }
  // Khởi chạy poller thông báo độc lập khi đăng nhập thành công
  startNotificationPoller();
}

/* ── App init ──────────────────────────────────────────────── */
async function initApp() {
  startClock();
  await loadSites();
  await updateDevicesDatalist();
  renderSiteList(state.currentGroup);
  bindTopbar();
  bindActionStrip();
  startNotificationPoller();
  triggerBackgroundSync();
}

async function updateDevicesDatalist(siteName = "") {
  try {
    const datalist = $("#device-options");
    if (!datalist) return;

    let devices = [];
    if (siteName) {
      try {
        const items = await apiFetch(`/api/sites/${encodeURIComponent(siteName)}/items`);
        devices = items.map(it => it.file_name.replace(/\.txt$/, ""));
      } catch (e) {
        devices = await apiFetch("/api/admin/devices");
      }
    } else {
      devices = await apiFetch("/api/admin/devices");
    }

    if (datalist) {
      datalist.innerHTML = devices.map(d => `<option value="${d}">`).join("");
    }
  } catch (err) {
    console.error("Lỗi cập nhật datalist thiết bị:", err);
  }
}

/* ── Clock ──────────────────────────────────────────────────── */
function startClock() {
  state.clockInterval = setInterval(() => {
    if (state.clockRunning) {
      const now = new Date();
      const pad = n => String(n).padStart(2, "0");
      $("#clock-display").textContent = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
      $("#clock-display").classList.remove("paused");
    } else {
      $("#clock-display").classList.add("paused");
    }
  }, 1000);
}

function bindTopbar() {
  $("#btn-catch").onclick    = () => { state.clockRunning = false; };
  $("#btn-continue").onclick = () => { state.clockRunning = true;  };
  $("#btn-sync").onclick     = triggerBackgroundSync;
  $("#btn-charts").onclick   = showChartsModal;
  $("#btn-logout").onclick   = async () => {
    await apiFetch("/api/auth/logout", { method: "POST" });
    window.location.href = "/";
  };
  $("#btn-admin").onclick    = () => {
    openModal("admin");
    // Load dữ liệu tab đang active (mặc định là Users)
    loadAdminUsers();
    loadAdminSites();
  };
}

/* ── Countdown ─────────────────────────────────────────────── */
function startCountdown() {
  clearCountdown();
  state.countdownSec     = 300;
  state.countdownRunning = true;
  const el = $("#countdown-display");

  state.countdownJob = setInterval(() => {
    state.countdownSec--;
    const m = Math.floor(state.countdownSec / 60);
    const s = state.countdownSec % 60;
    const pad = n => String(n).padStart(2, "0");
    el.textContent = `⏳ ${pad(m)}:${pad(s)}`;

    if (state.countdownSec <= 60) el.className = "alert";
    if (state.countdownSec <= 0) {
      clearCountdown();
      el.textContent = "⏰ Contact Site!";
      el.className = "done";
    }
  }, 1000);
}

function clearCountdown() {
  if (state.countdownJob) clearInterval(state.countdownJob);
  state.countdownJob = null;
  state.countdownRunning = false;
  const el = $("#countdown-display");
  el.textContent = "⏳ Đang chờ...";
  el.className = "";
}

/* ── Sites & Items ──────────────────────────────────────────── */
async function loadSites() {
  try {
    const res = await apiFetch("/api/sites");
    state.sitesData = res.sites || {};
    state.siteKeyMap = res.key_map || {};
    updateSiteDatalist();
    loadPics(); // Also load PICs while we're at it
  } catch {
    showToast("Lỗi", "Không tải được danh sách sites.");
  }
}

async function loadPics() {
  try {
    state.pics = await apiFetch("/api/admin/pics");
    updatePicsDatalist();
  } catch {
    console.warn("Could not load PICs");
  }
}

function updateSiteDatalist() {
  const datalist = $("#dept-options");
  if (!datalist) return;
  
  const allOptions = new Set();
  
  // Use short names (codes) from siteKeyMap if they exist, otherwise use full names
  // User requested: "chỉ sử dụng các tên viết tắt như AVG"
  if (state.siteKeyMap && Object.keys(state.siteKeyMap).length > 0) {
    Object.values(state.siteKeyMap).forEach(code => {
      if (code) allOptions.add(code);
    });
  } else if (state.sitesData) {
    Object.values(state.sitesData).forEach(groupSites => {
      Object.keys(groupSites).forEach(name => allOptions.add(name));
    });
  }

  const sortedOptions = [...allOptions].sort();
  datalist.innerHTML = sortedOptions.map(s => `<option value="${s}">`).join("");
}

function updatePicsDatalist() {
  const datalist = $("#pic-options");
  if (!datalist || !state.pics) return;
  datalist.innerHTML = state.pics.map(p => `<option value="${p}">`).join("");
}

function renderSiteList(group) {
  const list    = $("#site-list");
  list.innerHTML = "";
  state.currentGroup = group;

  // Group tab highlight
  const tabs = $$(".group-tab");
  tabs.forEach(t => t.classList.remove("active-aeon", "active-max"));
  if (group === "AEONMALL") $(".group-tab[data-group='AEONMALL']").classList.add("active-aeon");
  else                       $(".group-tab[data-group='MAXVALUE']").classList.add("active-max");

  const sites = state.sitesData[group] || {};

  Object.keys(sites).forEach(siteKey => {
    const item = document.createElement("div");
    item.className = "site-item";
    const siteSlug = siteKey.replace(/[^a-zA-Z0-9]/g, "-"); // slug an toan cho id

    const btn = document.createElement("button");
    btn.className = "site-btn " + (group === "AEONMALL" ? "aeon-site" : "max-site");
    btn.innerHTML = `<span>${siteKey}</span><span class="chevron">›</span>`;
    btn.onclick = () => toggleSiteItems(siteKey, siteSlug, item, btn);

    const subList = document.createElement("div");
    subList.className = "item-list";
    subList.id = `items-${siteSlug}`;

    item.appendChild(btn);
    item.appendChild(subList);
    list.appendChild(item);
  });
}

async function toggleSiteItems(siteKey, siteSlug, container, btn) {
  const subList = $(`#items-${siteSlug}`);
  const isOpen  = subList.classList.contains("visible");

  // Close all
  $$(".item-list.visible").forEach(l => l.classList.remove("visible"));
  $$(".site-btn.open").forEach(b => b.classList.remove("open"));

  if (isOpen) return;

  btn.classList.add("open");
  subList.classList.add("visible");
  state.currentSiteKey = siteKey;

  // Load items if empty, or refresh after a background sync
  if (!subList.dataset.loaded || state.needsRefresh) {
    subList.dataset.loaded = "false";
    subList.innerHTML = `<div style="padding:4px 8px; color:var(--text-muted); font-size:11px;"><span class="spinner"></span></div>`;
    try {
      const items = await apiFetch(`/api/sites/${encodeURIComponent(siteKey)}/items`, { timeout: 20000 });
      subList.innerHTML = "";
      items.forEach(it => {
        const b = document.createElement("button");
        b.className = "item-btn";
        const short = it.label.includes("_") ? it.label.split("_").slice(1).join("_") : it.label;
        b.textContent = short;
        b.title = it.label;
        b.onclick = () => selectItem(b, it.file_id, it.file_name, it.label);
        subList.appendChild(b);
      });
      subList.dataset.loaded = "true";
      state.needsRefresh = false;
    } catch (err) {
      const isTimeout = err.isTimeout || err.name === "TimeoutError";
      const message = isTimeout
        ? "⚠️ Quá thời gian chờ. Vui lòng đồng bộ lại."
        : (err?.message || "Lỗi tải");
      subList.innerHTML = `<div style="padding:4px 8px; color:var(--red); font-size:11px;">${message}</div>`;
      if (isTimeout) showToast("⚠️ Timeout", "OneDrive không phản hồi. Nhấn nút Sync để thử lại.", 8000);
    }
  }
}

function _resetForms() {
  // Reset toan bo Contact form
  const contactDevice = $("#contact-device");
  if (contactDevice) contactDevice.value = "";
  ["contact-time-start-h","contact-time-start-m",
   "contact-time-end-h","contact-time-end-m"].forEach(id => {
    const el = $(`#${id}`); if (el) el.value = "";
  });
  const contactStatus = $("#contact-status");
  if (contactStatus) contactStatus.value = "Normal";
  const contactProcessing = $("#contact-processing");
  if (contactProcessing) contactProcessing.value = "None";

  // Reset toan bo Status form
  const statusDept   = $("#status-dept");   if (statusDept)   statusDept.value   = "";
  const statusDevice = $("#status-device"); if (statusDevice) statusDevice.value = "";
  const statusDesc   = $("#status-desc");   if (statusDesc)   statusDesc.value   = "";
  ["status-start-h","status-start-m",
   "status-end-h","status-end-m"].forEach(id => {
    const el = $(`#${id}`); if (el) el.value = "";
  });

  // Reset originalReportText
  state.originalReportText = "";
}

async function selectItem(btn, fileId, fileName, label) {
  // Deactivate previous
  if (state.activeItemBtn) state.activeItemBtn.classList.remove("active");
  btn.classList.add("active");
  state.activeItemBtn = btn;

  state.currentFileId  = fileId;
  state.currentFileName = fileName;

  // Reset form khi chon item moi
  _resetForms();

  // First box fill
  handleFirstBoxFill();

  const isNoError = label.toUpperCase().includes("NO_ERROR");
  setOutputText("⏳ Đang tải...");

  try {
    const res = await apiFetch("/api/report/text", {
      method: "POST",
      body: JSON.stringify({ file_id: fileId, file_name: fileName, is_no_error: isNoError }),
      timeout: 20000,
    });
    if (res.error) {
      setOutputText(`[Lỗi] ${res.error}`);
    } else {
      setOutputText(res.text);
      state.originalReportText = res.text; // luu bao cao goc
      if (!isNoError) startCountdown();
    }
  } catch (err) {
    if (err.isTimeout || err.name === "TimeoutError") {
      setOutputText("[Lỗi] Quá thời gian chờ. Vui lòng kiểm tra kết nối OneDrive và thử lại.");
      showToast("⚠️ Timeout", "Server không phản hồi. Hãy đồng bộ lại hoặc kiểm tra OneDrive.", 8000);
    } else {
      setOutputText(`[Lỗi kết nối] ${err.message || "Không thể kết nối backend"}`);
    }
  }
}

/* ── Site search ────────────────────────────────────────────── */
function bindSiteSearch() {
  $("#site-search").addEventListener("input", function () {
    const kw = this.value.toLowerCase();
    $$(".site-item").forEach(el => {
      const name = $(".site-btn span", el).textContent.toLowerCase();
      el.style.display = kw === "" || name.includes(kw) ? "" : "none";
    });
  });
}

/* ── Output area ────────────────────────────────────────────── */
function setOutputText(text) {
  $("#output-text").value = text;
}

function bindOutputActions() {
  $("#btn-copy-text").onclick = () => {
    const t = $("#output-text").value;
    if (!t || t.startsWith("⏳") || t.startsWith("[")) return;
    copyToClipboard(t);
  };
  $("#btn-clear-text").onclick = () => {
    setOutputText("");
    clearCountdown();
    // Don't reset process tracker — user decides
  };
}

/* ── Process tracker ────────────────────────────────────────── */
const HINTS = [
  "Đang chờ sự cố...",
  "Đã ghi nhận. Báo cáo lên group chung, tiếp tục theo dõi. Trong 5 phút không có thông báo → liên hệ Site. Nhấn [Contact] để cập nhật thông tin liên hệ.",
  "Tiếp tục theo dõi. Sau 1–2 tiếng chưa có thông tin → liên hệ lại xác minh tình trạng. Nhấn [Status] để cập nhật.",
  "Sự cố sau 1–2 tiếng chưa giải quyết → liên hệ theo số ưu tiên, báo cáo lên group. Nhấn [Xác nhận] để tiếp tục.",
  "Sự cố đã giải quyết → báo cáo lên group cho các bên liên quan. Nhấn [Xác nhận].",
  "Cập nhật lên bảng Alarm List. Nhấn [Xác nhận].",
  "✅ Toàn bộ quy trình hoàn tất. Làm tốt lắm!",
];

function handleFirstBoxFill() {
  if (!state.boxFilled[0]) {
    state.boxFilled[0] = true;
    updateProcessUI();
  }
}

function fillBox(index) {
  if (index === 0 || state.boxFilled[index - 1]) {
    state.boxFilled[index] = true;
    updateProcessUI();
    return true;
  }
  showToast("Chú ý", `Vui lòng hoàn thành bước ${index} trước.`);
  return false;
}

function updateProcessUI() {
  const count = state.boxFilled.filter(Boolean).length;
  $$(".process-step").forEach((el, i) => {
    el.classList.toggle("filled", state.boxFilled[i]);
  });
  const hint = HINTS[count] || HINTS[0];
  $("#hint-text").textContent = hint;

  if (count === 6) {
    setTimeout(() => {
      state.boxFilled = [false, false, false, false, false, false];
      updateProcessUI();
    }, 5000);
  }
}

/* ── Action strip ────────────────────────────────────────────── */
function bindActionStrip() {
  $("#btn-confirm").onclick = () => {
    for (let i = 3; i < 6; i++) {
      if (!state.boxFilled[i]) {
        if (fillBox(i)) break;
        else break;
      }
    }
  };

  $$(".strip-btn[data-modal]").forEach(btn => {
    btn.onclick = () => {
      if (btn.dataset.modal === "contact") openContactModal();
      else openModal(btn.dataset.modal);
    };
  });
}

/* ── Modals ─────────────────────────────────────────────────── */
function _setTimePicker(prefix, value) {
  // Set HH:MM selects tu string "HH:MM"
  if (!value) return;
  const clean = value.trim().replace(/[^0-9:]/g, "").substring(0, 5);
  const parts = clean.split(":");
  if (parts.length < 2) return;
  const hEl = $(`#${prefix}-h`);
  const mEl = $(`#${prefix}-m`);
  if (hEl) hEl.value = parts[0].padStart(2, "0");
  if (mEl) mEl.value = parts[1].padStart(2, "0");
}

function _getTimePicker(prefix) {
  const h = ($(`#${prefix}-h`) || {}).value || "";
  const m = ($(`#${prefix}-m`) || {}).value || "";
  if (!h || !m) return "";
  return `${h}:${m}`;
}

function _getDatePicker(prefix) {
  const el = $(`#${prefix}-date`);
  return el ? el.value : "";
}

function openModal(name) {
  const overlay = $(`#${name}-modal`);
  if (!overlay) return;
  overlay.classList.add("open");

  if (name === "note") {
    loadNotesList();
    loadUserEmailsList();
  }
  if (name === "daviteq") initDaviteqViewer();
  if (name === "document") initDocumentViewer();

  // Auto-fill Status form tu output text
  if (name === "status") {
    // Bat tat ca fields
    $$(".status-field").forEach(el => {
      el.disabled = false;
      el.style.opacity = "1";
    });
    const dept   = _extractFromReport("bộ phận") || _extractFromReport("khu vực");
    const device = _extractFromReport("thiết bị");
    const time   = _extractTimeFromReport();

    if (dept)   { 
      const el = $("#status-dept");   
      if (el) {
        el.value = dept;
        // Trigger device list update immediately
        updateDevicesDatalist(dept);
      }
    }
    if (device) { const el = $("#status-device"); if (el) el.value = device; }
    if (time)   { _setTimePicker("status-start", time); }

    // Auto-fill ngay hom nay cho ca 2 date picker
    const todayVal = new Date().toLocaleDateString("en-CA"); // YYYY-MM-DD
    const sd = $("#status-start-date"); if (sd) sd.value = todayVal;
    const ed = $("#status-end-date");   if (ed) ed.value = todayVal;
  }
}

function closeModal(name) {
  $(`#${name}-modal`).classList.remove("open");
}

function bindModalCloses() {
  $$(".modal-overlay").forEach(overlay => {
    overlay.addEventListener("click", e => {
      if (e.target === overlay) overlay.classList.remove("open");
    });
  });
  $$(".btn-close-modal").forEach(btn => {
    btn.onclick = () => {
      const modal = btn.closest(".modal-overlay") || btn.closest(".admin-fullscreen-wrapper");
      if (modal) {
        modal.classList.remove("open");
        if (modal.id === "admin-modal") {
          // Sau khi đóng admin: reload sites và refresh nội dung báo cáo hiện tại ngay lập tức
          refreshAfterAdminClose();
        }
      }
    };
  });
}

async function refreshAfterAdminClose() {
  // Reload danh sách sites để phản ánh thay đổi Sites/Devices/PICs
  await loadSites();
  renderSiteList(state.currentGroup);

  // Nếu đang có file được chọn, reload lại nội dung báo cáo ngay
  // để phản ánh thay đổi template từ admin mà không cần click lại
  if (state.currentFileId && state.currentFileName) {
    const isNoError = (state.currentFileName || "").toUpperCase().includes("NO_ERROR");
    try {
      const res = await apiFetch("/api/report/text", {
        method: "POST",
        body: JSON.stringify({
          file_id: state.currentFileId,
          file_name: state.currentFileName,
          is_no_error: isNoError,
        }),
        timeout: 20000,
      });
      if (!res.error) {
        setOutputText(res.text);
        state.originalReportText = res.text;
      }
    } catch {
      // Bỏ qua lỗi reload - nội dung cũ vẫn hiển thị
    }
  }
}

/* ── Admin user management ─────────────────────────────────── */
function _adminActionsHtml(user) {
  if (!user.approved) {
    return `
      <div class="admin-action-group" id="action-group-${user.id}">
        <button class="btn-approve admin-approve" data-id="${user.id}" style="padding: 6px 10px; font-size: 12px; border-radius: 6px; border: none; background: #dcfce7; color: #166534; cursor: pointer;">
          ✓ Duyệt
        </button>
        <button class="btn-reject admin-reject" data-id="${user.id}" style="padding: 6px 10px; font-size: 12px; border-radius: 6px; border: none; background: #fee2e2; color: #991b1b; cursor: pointer;">
          ✕ Xóa
        </button>
      </div>
      <div id="action-status-${user.id}" style="font-size: 13px; font-weight: 600; display: none;"></div>
    `;
  } else {
    const roleBtn = user.role === 'admin' 
      ? `<button class="admin-demote" data-id="${user.id}" style="padding: 4px 8px; font-size: 12px; border-radius: 4px; border: 1px solid #e5e7eb; background: white; color: #374151; cursor: pointer;">Hạ quyền</button>`
      : `<button class="admin-promote" data-id="${user.id}" style="padding: 4px 8px; font-size: 12px; border-radius: 4px; border: 1px solid #e5e7eb; background: white; color: #374151; cursor: pointer;">Lên Admin</button>`;
      
    return `
      <div class="admin-action-group" style="display:flex; gap: 8px; justify-content: flex-end;">
        ${roleBtn}
        <button class="admin-delete" data-id="${user.id}" style="padding: 4px 8px; font-size: 12px; border-radius: 4px; border: 1px solid #fecaca; background: #fee2e2; color: #b91c1c; cursor: pointer;">Xóa</button>
      </div>
    `;
  }
}

function renderAdminUsers(users) {
  const tbody = $("#admin-users-tbody");
  if (!tbody) return;

  if (!Array.isArray(users) || users.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#9ca3af;padding:30px;">Không có user nào</td></tr>';
    const tabBtn = $(".admin-v2-tab[data-tab='users']");
    if (tabBtn) tabBtn.textContent = `Quản lý User (0)`;
    return;
  }

  const tabBtn = $(".admin-v2-tab[data-tab='users']");
  if (tabBtn) tabBtn.textContent = `Quản lý User (${users.length})`;

  const searchKw = ($("#admin-user-search")?.value || "").toLowerCase();
  let displayUsers = users;
  if (searchKw) {
    displayUsers = users.filter(u => 
      (u.name && u.name.toLowerCase().includes(searchKw)) || 
      (u.email && u.email.toLowerCase().includes(searchKw))
    );
  }

  if (displayUsers.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#9ca3af;padding:30px;">Không tìm thấy user nào phù hợp</td></tr>';
    return;
  }

  tbody.innerHTML = displayUsers.map((user, idx) => {
    const mockDate = user.created_at ? new Date(user.created_at).toLocaleString('vi-VN') : "Không rõ";
    const pColor = user.provider === 'microsoft' ? 'color:#1e40af; background:#dbeafe; border-color:#bfdbfe;' : 
                   user.provider === 'google' ? 'color:#b91c1c; background:#fee2e2; border-color:#fecaca;' : 
                   'color:#374151; background:#f3f4f6; border-color:#e5e7eb;';
    
    const roleBadge = user.role === 'admin' 
      ? `<span style="background:#fef08a; color:#854d0e; padding:2px 8px; border-radius:12px; font-size:12px; font-weight:600;">Admin</span>`
      : `<span style="background:#e5e7eb; color:#374151; padding:2px 8px; border-radius:12px; font-size:12px; font-weight:600;">User</span>`;

    return `
      <tr>
        <td class="admin-user-name">${user.name || "User"} ${!user.approved ? '<span style="color:#dc2626; font-size:12px; margin-left:4px;">(Chờ duyệt)</span>' : ''}</td>
        <td class="admin-user-email">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path><polyline points="22,6 12,13 2,6"></polyline></svg>
          ${user.email || ""}
        </td>
        <td>${roleBadge}</td>
        <td><span class="admin-provider-badge" style="${pColor}">${user.provider || "local"}</span></td>
        <td class="admin-date-cell">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>
          ${mockDate}
        </td>
        <td style="text-align:right;">${_adminActionsHtml(user)}</td>
      </tr>
    `;
  }).join("");

  $$(".admin-approve", tbody).forEach(btn => {
    btn.onclick = async () => {
      const id = btn.dataset.id;
      const grp = $(`#action-group-${id}`);
      const st = $(`#action-status-${id}`);
      if(grp) grp.style.display = "none";
      if(st) {
        st.style.display = "block";
        st.style.color = "#16a34a";
        st.textContent = "✓ Đã phê duyệt";
      }

      const res = await apiFetch(`/api/auth/admin/users/${id}/approve`, { method: "POST" });
      if (res.error) {
        showToast("Lỗi", res.error);
        if(grp) grp.style.display = "flex";
        if(st) st.style.display = "none";
      } else {
        const currentText = $(".admin-v2-tab[data-tab='users']").textContent;
        const match = currentText.match(/\d+/);
        if (match) {
          const count = parseInt(match[0]);
          if (!isNaN(count) && count > 0) {
            $(".admin-v2-tab[data-tab='users']").textContent = `Chờ phê duyệt (${count - 1})`;
          }
        }
      }
    };
  });

  $$(".admin-reject", tbody).forEach(btn => {
    btn.onclick = async () => {
      const id = btn.dataset.id;
      const grp = $(`#action-group-${id}`);
      const st = $(`#action-status-${id}`);
      if(grp) grp.style.display = "none";
      if(st) {
        st.style.display = "block";
        st.style.color = "#dc2626";
        st.textContent = "✕ Đã từ chối";
      }

      const res = await apiFetch(`/api/auth/admin/users/${id}`, { method: "DELETE" });
      if (res.error) {
        showToast("Lỗi", res.error);
        if (st) st.style.display = "none";
      } else {
        loadAdminUsers();
      }
    };
  });

  $$(".admin-delete", tbody).forEach(btn => {
    btn.onclick = async () => {
      if (!confirm("Bạn có chắc muốn xóa user này?")) return;
      const res = await apiFetch(`/api/auth/admin/users/${btn.dataset.id}`, { method: "DELETE" });
      if (res.error) showToast("Lỗi", res.error);
      else loadAdminUsers();
    };
  });

  $$(".admin-promote", tbody).forEach(btn => {
    btn.onclick = async () => {
      const res = await apiFetch(`/api/auth/admin/users/${btn.dataset.id}/role`, { method: "POST", body: JSON.stringify({ role: "admin" }) });
      if (res.error) showToast("Lỗi", res.error);
      else loadAdminUsers();
    };
  });

  $$(".admin-demote", tbody).forEach(btn => {
    btn.onclick = async () => {
      const res = await apiFetch(`/api/auth/admin/users/${btn.dataset.id}/role`, { method: "POST", body: JSON.stringify({ role: "user" }) });
      if (res.error) showToast("Lỗi", res.error);
      else loadAdminUsers();
    };
  });
}

let usersDataCache = [];
async function loadAdminUsers() {
  const tbody = $("#admin-users-tbody");
  if (tbody) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#9ca3af;padding:30px;"><span class="spinner"></span> Đang tải...</td></tr>';
  }
  const res = await apiFetch("/api/auth/admin/users");
  if (res.error) {
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--red);padding:30px;">${res.error}</td></tr>`;
    }
    return;
  }
  usersDataCache = res;
  renderAdminUsers(res);
  
  const searchInput = $("#admin-user-search");
  if (searchInput) {
    searchInput.oninput = () => renderAdminUsers(usersDataCache);
  }
}

function bindAdminModal() {
  bindAdminTabs();
  const btn = $("#admin-add-user");
  if (btn) {
    btn.onclick = async () => {
      const email = ($("#admin-new-email")?.value || "").trim();
      const name = ($("#admin-new-name")?.value || "").trim();

      if (!email) {
        showToast("Thiếu thông tin", "Vui lòng nhập email user.");
        return;
      }

      const res = await apiFetch("/api/auth/admin/users", {
        method: "POST",
        body: JSON.stringify({ email, name, approved: true }),
      });

      if (res.error) {
        showToast("Lỗi", res.error);
        return;
      }

      $("#admin-new-email").value = "";
      $("#admin-new-name").value = "";
      showToast("Thành công", `Đã thêm user ${res.email}.`);
      loadAdminUsers();
    };
  }

  // --- Site Mgmt ---
  $("#admin-add-site").onclick = async () => {
    const group = $("#admin-site-group").value;
    const name = $("#admin-site-name").value.trim();
    const shortName = $("#admin-site-short").value.trim();
    const path = $("#admin-site-path").value.trim();
    if (!name || !path) return showToast("Lỗi", "Vui lòng nhập tên Site và Path");

    try {
      const { sites_config, site_key_map } = await apiFetch("/api/admin/sites/config");
      if (!sites_config[group]) sites_config[group] = {};
      sites_config[group][name] = path;
      site_key_map[name.toUpperCase()] = shortName || name.toUpperCase().replace(/\s+/g, "");

      await apiFetch("/api/admin/sites/config", {
        method: "POST",
        body: JSON.stringify({ sites_config, site_key_map })
      });
      showToast("Thành công", "Đã thêm site mới");
      $("#admin-site-name").value = "";
      $("#admin-site-short").value = "";
      $("#admin-site-path").value = "";
      loadAdminSites();
      loadSites(); // Refresh main site list
    } catch (err) { showToast("Lỗi", err.message); }
  };

  // --- PIC Mgmt ---
  const addPicBtn = $("#admin-add-pic");
  if (addPicBtn) {
    addPicBtn.onclick = async () => {
      const nameInput = $("#admin-pic-name");
      const name = nameInput ? nameInput.value.trim() : "";
      if (!name) return;
      try {
        const pics = await apiFetch("/api/admin/pics");
        if (pics.includes(name)) return showToast("Lỗi", "PIC đã tồn tại");
        pics.push(name);
        await apiFetch("/api/admin/pics", { method: "POST", body: JSON.stringify(pics) });
        showToast("Thành công", "Đã thêm PIC");
        if (nameInput) nameInput.value = "";
        loadAdminPics();
        loadPics();
      } catch (err) { showToast("Lỗi", err.message); }
    };
  }

  // --- Device Mgmt ---
  const addDeviceBtn = $("#admin-add-device");
  if (addDeviceBtn) {
    addDeviceBtn.onclick = async () => {
      const nameInput = $("#admin-device-name");
      const name = nameInput ? nameInput.value.trim() : "";
      if (!name) return;
      try {
        const devices = await apiFetch("/api/admin/devices");
        if (devices.includes(name)) return showToast("Lỗi", "Thiết bị đã tồn tại");
        devices.push(name);
        await apiFetch("/api/admin/devices", { method: "POST", body: JSON.stringify(devices) });
        showToast("Thành công", "Đã thêm thiết bị");
        if (nameInput) nameInput.value = "";
        loadAdminDevices();
        updateDevicesDatalist();
      } catch (err) { showToast("Lỗi", err.message); }
    };
  }

  // --- Template Mgmt ---
  const tplCreateBtn = $("#admin-tpl-create");
  if (tplCreateBtn) {
    tplCreateBtn.onclick = async () => {
      const site_key = $("#admin-tpl-site-select").value;
      const filename = $("#admin-tpl-filename").value.trim();
      if (!site_key || !filename) return showToast("Lỗi", "Chọn site và nhập tên file");

      try {
        await apiFetch("/api/admin/site-items", {
          method: "POST",
          body: JSON.stringify({ site_key, filename, content: "Nội dung báo cáo mẫu cho " + filename })
        });
        showToast("Thành công", "Đã tạo file mẫu trên OneDrive");
        $("#admin-tpl-filename").value = "";
        loadAdminTemplates(site_key);
      } catch (err) { showToast("Lỗi", err.message); }
    };
  }

  $("#admin-tpl-site-select").onchange = (e) => loadAdminTemplates(e.target.value);
  if ($("#admin-tpl-search")) {
    $("#admin-tpl-search").oninput = _renderAdminTemplatesTable;
  }

  // --- Cloud Sync ---
  const syncCloudBtn = $("#admin-sync-cloud");
  const pushCloudBtn = $("#admin-push-cloud");

  if (pushCloudBtn) {
    pushCloudBtn.onclick = async () => {
      pushCloudBtn.disabled = true;
      const originalText = pushCloudBtn.textContent;
      pushCloudBtn.innerHTML = `<span class="spinner"></span> Đang tải lên...`;
      try {
        const res = await apiFetch("/api/admin/config/push-to-cloud", { method: "POST" });
        if (res.error) showToast("Lỗi", res.error);
        else showToast("Thành công", "Đã tải cấu hình hiện tại lên OneDrive");
      } catch (err) {
        showToast("Lỗi", err.message || "Không thể tải lên OneDrive");
      } finally {
        pushCloudBtn.disabled = false;
        pushCloudBtn.textContent = originalText;
      }
    };
  }

  if (syncCloudBtn) {
    syncCloudBtn.onclick = async () => {
      syncCloudBtn.disabled = true;
      const originalText = syncCloudBtn.textContent;
      syncCloudBtn.innerHTML = `<span class="spinner"></span> Đang đồng bộ...`;
      
      try {
        const res = await apiFetch("/api/admin/config/sync-from-cloud", { method: "POST" });
        if (res.error) {
          showToast("Lỗi", res.error);
        } else {
          showToast("Thành công", `Đã tải cấu hình: ${res.synced.join(", ")}`);
          // Reload everything to reflect new config
          loadAdminSites();
          loadAdminDevices();
          loadSites(); // Refresh main sidebar
        }
      } catch (err) {
        showToast("Lỗi", err.message || "Không thể đồng bộ từ OneDrive");
      } finally {
        syncCloudBtn.disabled = false;
        syncCloudBtn.textContent = originalText;
      }
    };
  }
}

function bindAdminTabs() {
  const tabs = $$("#admin-tabs .admin-v2-tab");
  tabs.forEach(t => {
    t.onclick = () => {
      console.log("Admin tab clicked:", t.dataset.tab);
      tabs.forEach(x => x.classList.remove("active"));
      t.classList.add("active");
      const panelId = "admin-panel-" + t.dataset.tab;
      
      $$(".admin-panel").forEach(p => {
        p.style.display = "none";
        p.classList.add("hidden");
      });
      const targetPanel = $("#" + panelId);
      if (targetPanel) {
        targetPanel.style.display = "block";
        targetPanel.classList.remove("hidden");
      }

      // Load data on demand
      if (t.dataset.tab === "users") loadAdminUsers();
      if (t.dataset.tab === "system") loadAdminSites();
      if (t.dataset.tab === "devices") loadAdminDevices();
      if (t.dataset.tab === "pics") loadAdminPics();
    };
  });
}

async function loadAdminSites() {
  const tbody = $("#admin-sites-tbody");
  if (tbody) tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;"><span class="spinner"></span></td></tr>';
  
  try {
    const data = await apiFetch("/api/admin/sites/config");
    console.log("Admin Sites Data:", data);
    const { sites_config } = data;
    renderAdminSites(sites_config);
    
    // Fill template site select
    const select = $("#admin-tpl-site-select");
    if (select) {
      let options = '<option value="">-- Chọn Site --</option>';
      for (const group in sites_config) {
        for (const site in sites_config[group]) {
          options += `<option value="${site}">${site}</option>`;
        }
      }
      select.innerHTML = options;
    }
  } catch (err) {
    console.error("Lỗi loadAdminSites:", err);
    if (tbody) tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;color:var(--red);">Lỗi: ${err.message}</td></tr>`;
  }
}

function renderAdminSites(config) {
  const tbody = $("#admin-sites-tbody");
  if (!tbody) return;
  let html = "";
  for (const group in config) {
    for (const site in config[group]) {
      const path = config[group][site];
      
      let groupBadge = `<span style="background: #e5e7eb; color: #374151; padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; text-transform: uppercase;">${group}</span>`;
      if (group === "AEONMALL") {
        groupBadge = `<span style="background: #fce7f3; color: #be185d; padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; text-transform: uppercase;">${group}</span>`;
      } else if (group === "MAXVALUE") {
        groupBadge = `<span style="background: #dbeafe; color: #1d4ed8; padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; text-transform: uppercase;">${group}</span>`;
      }

      html += `
        <tr>
          <td>${groupBadge}</td>
          <td style="font-weight: 500;">${site}</td>
          <td style="font-size:12px; color:var(--text-muted)">${path}</td>
          <td>
            <button class="topbar-btn admin-site-edit" data-group="${group}" data-site="${site}">Sửa</button>
            <button class="topbar-btn admin-site-del" data-group="${group}" data-site="${site}">Xóa</button>
          </td>
        </tr>
      `;
    }
  }
  tbody.innerHTML = html;
  
  $$(".admin-site-edit").forEach(btn => {
    btn.onclick = async () => {
      const { group, site } = btn.dataset;
      const { sites_config, site_key_map } = await apiFetch("/api/admin/sites/config");
      const currentPath = sites_config[group][site];
      
      const newName = window.prompt("Tên Site mới:", site);
      if (newName === null) return;
      const newPath = window.prompt("OneDrive Path mới:", currentPath);
      if (newPath === null) return;
      
      if (newName !== site) {
        sites_config[group][newName] = newPath;
        delete sites_config[group][site];
        site_key_map[newName.toUpperCase()] = site_key_map[site.toUpperCase()] || newName.toUpperCase().replace(/\s+/g, "");
        delete site_key_map[site.toUpperCase()];
      } else {
        sites_config[group][site] = newPath;
      }
      
      await apiFetch("/api/admin/sites/config", { method: "POST", body: JSON.stringify({ sites_config, site_key_map }) });
      loadAdminSites();
      loadSites();
    };
  });

  $$(".admin-site-del").forEach(btn => {
    btn.onclick = async () => {
      const { group, site } = btn.dataset;
      if (!confirm(`Xóa site "${site}"? Thao tác này sẽ xóa cả thư mục trên OneDrive.`)) return;
      
      try {
        await apiFetch("/api/admin/sites", { 
          method: "DELETE", 
          body: JSON.stringify({ group, site }) 
        });
        showToast("Thành công", "Đã xóa Site và thư mục trên OneDrive");
        loadAdminSites();
        loadSites();
      } catch (err) {
        showToast("Lỗi", "Không thể xóa Site: " + err.message);
      }
    };
  });
}

async function loadAdminDevices() {
  const tbody = $("#admin-devices-tbody");
  if (tbody) tbody.innerHTML = '<tr><td colspan="2" style="text-align:center;"><span class="spinner"></span></td></tr>';

  try {
    const devices = await apiFetch("/api/admin/devices");
    console.log("Admin Devices Data:", devices);
    renderAdminDevices(devices);
  } catch (err) {
    console.error("Lỗi loadAdminDevices:", err);
    if (tbody) tbody.innerHTML = `<tr><td colspan="2" style="text-align:center;color:var(--red);">Lỗi: ${err.message}</td></tr>`;
  }
}

function renderAdminDevices(devices) {
  const tbody = $("#admin-devices-tbody");
  if (!tbody) return;
  tbody.innerHTML = devices.map(d => `
    <tr>
      <td>${d}</td>
      <td>
        <button class="topbar-btn admin-device-del" data-name="${d}">Xóa</button>
      </td>
    </tr>
  `).join("");
  $$(".admin-device-del").forEach(btn => {
    btn.onclick = async () => {
      const name = btn.dataset.name;
      const devList = await apiFetch("/api/admin/devices");
      const filtered = devList.filter(x => x !== name);
      await apiFetch("/api/admin/devices", { method: "POST", body: JSON.stringify(filtered) });
      loadAdminDevices();
      updateDevicesDatalist();
    };
  });
}

async function loadAdminPics() {
  const tbody = $("#admin-pics-tbody");
  if (tbody) tbody.innerHTML = '<tr><td colspan="2" style="text-align:center;"><span class="spinner"></span></td></tr>';
  try {
    const pics = await apiFetch("/api/admin/pics");
    renderAdminPics(pics);
  } catch (err) {
    if (tbody) tbody.innerHTML = `<tr><td colspan="2" style="text-align:center;color:var(--red);">Lỗi: ${err.message}</td></tr>`;
  }
}

function renderAdminPics(pics) {
  const tbody = $("#admin-pics-tbody");
  if (!tbody) return;
  tbody.innerHTML = pics.map(p => `
    <tr>
      <td>${p}</td>
      <td>
        <button class="topbar-btn admin-pic-edit" data-name="${p}">Sửa</button>
        <button class="topbar-btn admin-pic-del" data-name="${p}">Xóa</button>
      </td>
    </tr>
  `).join("");
  
  $$(".admin-pic-edit").forEach(btn => {
    btn.onclick = async () => {
      const oldName = btn.dataset.name;
      const newName = window.prompt("Tên PIC mới:", oldName);
      if (!newName || newName === oldName) return;
      const picList = await apiFetch("/api/admin/pics");
      const idx = picList.indexOf(oldName);
      if (idx !== -1) picList[idx] = newName;
      await apiFetch("/api/admin/pics", { method: "POST", body: JSON.stringify(picList) });
      loadAdminPics();
      loadPics();
    };
  });

  $$(".admin-pic-del").forEach(btn => {
    btn.onclick = async () => {
      const name = btn.dataset.name;
      if (!confirm(`Xóa PIC "${name}"?`)) return;
      const picList = await apiFetch("/api/admin/pics");
      const filtered = picList.filter(x => x !== name);
      await apiFetch("/api/admin/pics", { method: "POST", body: JSON.stringify(filtered) });
      loadAdminPics();
      loadPics();
    };
  });
}

async function loadAdminTemplates(siteKey) {
  if (!siteKey) return $("#admin-templates-tbody").innerHTML = "";
  try {
    const items = await apiFetch(`/api/sites/${encodeURIComponent(siteKey)}/items`);
    renderAdminTemplates(siteKey, items);
  } catch (err) { console.error(err); }
}

function renderAdminTemplates(siteKey, items) {
  state.currentAdminTplItems = items || [];
  state.currentAdminTplSiteKey = siteKey;
  _renderAdminTemplatesTable();
}

function _renderAdminTemplatesTable() {
  const tbody = $("#admin-templates-tbody");
  if (!tbody) return;
  const kw = ($("#admin-tpl-search")?.value || "").toLowerCase();
  
  const filtered = state.currentAdminTplItems.filter(it => 
    it.file_name.toLowerCase().includes(kw)
  );

  tbody.innerHTML = filtered.map(it => `
    <tr>
      <td>${it.file_name}</td>
      <td>
        <button class="topbar-btn admin-tpl-edit" data-site="${state.currentAdminTplSiteKey}" data-id="${it.file_id}" data-name="${it.file_name}">Sửa ND</button>
        <button class="topbar-btn admin-tpl-rename" data-site="${state.currentAdminTplSiteKey}" data-id="${it.file_id}" data-name="${it.file_name}">Đổi tên</button>
        <button class="topbar-btn admin-tpl-del" data-site="${state.currentAdminTplSiteKey}" data-name="${it.file_name}">Xóa</button>
      </td>
    </tr>
  `).join("");

  $$(".admin-tpl-edit").forEach(btn => {
    btn.onclick = async () => {
      const { site, id, name } = btn.dataset;
      const res = await apiFetch("/api/report/text", { 
        method: "POST", 
        body: JSON.stringify({ file_id: id, file_name: name, raw: true }) 
      });
      
      // Use the new large modal instead of window.prompt
      $("#tpl-edit-label").textContent = `Đang sửa: ${name} (Site: ${site})`;
      $("#tpl-edit-content").value = res.text;
      openModal("tpl-edit");
      
      $("#tpl-edit-save").onclick = async () => {
        const newContent = $("#tpl-edit-content").value;
        const btnSave = $("#tpl-edit-save");
        btnSave.disabled = true;
        btnSave.textContent = "⏳ Đang lưu...";
        
        try {
          await apiFetch("/api/admin/site-items", { 
            method: "POST", 
            body: JSON.stringify({ site_key: site, filename: name, content: newContent }) 
          });
          showToast("Thành công", "Đã cập nhật nội dung trực tiếp trên OneDrive");
          closeModal("tpl-edit");
        } catch (err) {
          showToast("Lỗi", "Không thể upload lên OneDrive: " + err.message);
        } finally {
          btnSave.disabled = false;
          btnSave.textContent = "Lưu thay đổi trực tiếp lên OneDrive";
        }
      };
    };
  });

  $$(".admin-tpl-rename").forEach(btn => {
    btn.onclick = async () => {
      const { site, id, name } = btn.dataset;
      const newName = window.prompt(`Đổi tên file ${name} thành:`, name);
      if (!newName || newName === name) return;
      
      try {
        await apiFetch("/api/admin/site-items", {
          method: "PATCH",
          body: JSON.stringify({ file_id: id, new_name: newName })
        });
        showToast("Thành công", "Đã đổi tên file trên OneDrive");
        loadAdminTemplates(site);
      } catch (err) {
        showToast("Lỗi", "Không thể đổi tên: " + err.message);
      }
    };
  });

  $$(".admin-tpl-del").forEach(btn => {
    btn.onclick = async () => {
      if (!confirm("Xóa file này trên OneDrive?")) return;
      const { site, name } = btn.dataset;
      await apiFetch("/api/admin/site-items", { method: "DELETE", body: JSON.stringify({ site_key: site, filename: name }) });
      showToast("Thành công", "Đã xóa file");
      loadAdminTemplates(site);
    };
  });
}

/* ── Contact modal ────────────────────────────────────────────── */
function _extractFromReport(keyword) {
  // Trich xuat gia tri tu bao cao goc (khong bi ghi de boi Contact/Status)
  const text = state.originalReportText || $("#output-text").value || "";
  const lines = text.split("\n");
  for (const line of lines) {
    const lower = line.toLowerCase();
    if (lower.includes(keyword.toLowerCase())) {
      const idx = line.indexOf(":");
      if (idx !== -1) return line.slice(idx + 1).trim();
    }
  }
  return "";
}

function _extractTimeFromReport() {
  // Tim dong "Thoi gian" va lay gia tri HH:MM tu bao cao goc
  const text = state.originalReportText || $("#output-text").value || "";
  const lines = text.split("\n");
  for (const line of lines) {
    if (line.toLowerCase().includes("thời gian") || line.toLowerCase().includes("time")) {
      const match = line.match(/\b(\d{1,2}:\d{2})\b/);
      if (match) return match[1];
    }
  }
  return "";
}

function _formatContactRecoveryTime(startTime, startDate, endTime, endDate) {
  if (!startTime && !endTime) return "...";
  if (!startTime || !endTime) return startTime || endTime;

  const [sh, sm] = startTime.split(":").map(Number);
  const [eh, em] = endTime.split(":").map(Number);
  if ([sh, sm, eh, em].some(n => Number.isNaN(n))) {
    return `${startTime} - ${endTime}`;
  }

  // Helper to format duration to the largest units (ngày, giờ, phút)
  function formatDuration(minutes) {
    if (minutes <= 0) return "0 phút";
    const days = Math.floor(minutes / (24 * 60));
    const remainingMinutes = minutes % (24 * 60);
    const hours = Math.floor(remainingMinutes / 60);
    const mins = remainingMinutes % 60;
    
    let parts = [];
    if (days > 0) {
      parts.push(`${days} ngày`);
    }
    if (hours > 0) {
      parts.push(`${hours} giờ`);
    }
    if (mins > 0 || parts.length === 0) {
      parts.push(`${mins} phút`);
    }
    return parts.join(" ");
  }

  // Helper to format date YYYY-MM-DD to DD/MM/YYYY
  function formatVnDate(dateStr) {
    if (!dateStr) return "";
    const parts = dateStr.split("-");
    if (parts.length === 3) {
      return `${parts[2]}/${parts[1]}/${parts[0]}`;
    }
    return dateStr;
  }

  // Check if dates are provided
  if (startDate && endDate) {
    const startDt = new Date(`${startDate}T${startTime}:00`);
    const endDt = new Date(`${endDate}T${endTime}:00`);
    if (!isNaN(startDt.getTime()) && !isNaN(endDt.getTime())) {
      const diffMs = endDt.getTime() - startDt.getTime();
      const totalMinutes = Math.floor(diffMs / (1000 * 60));
      const durStr = formatDuration(totalMinutes);
      return `(${durStr}) ${startTime}, ngày ${formatVnDate(startDate)} - ${endTime}, ngày ${formatVnDate(endDate)}`;
    }
  }

  // If one or both dates are missing, default to within 24h rollover logic
  let totalMinutes = (eh * 60 + em) - (sh * 60 + sm);
  if (totalMinutes < 0) totalMinutes += 24 * 60;
  const durStr = formatDuration(totalMinutes);
  return `(${durStr}) ${startTime} - ${endTime}`;
}

function _buildContactText() {
  const device = $("#contact-device").value.trim();
  const status = $("#contact-status").value;
  const processing = $("#contact-processing").value;
  const timeStart = _getTimePicker("contact-time-start");
  const timeEnd = _getTimePicker("contact-time-end");
  const dateStart = _getDatePicker("contact-start");
  const dateEnd = _getDatePicker("contact-end");

  if (!device) {
    showToast("Thiếu thông tin", "Vui lòng nhập tên thiết bị.");
    return null;
  }

  const timeStr = _formatContactRecoveryTime(timeStart, dateStart, timeEnd, dateEnd);
  return (
    `Dear anh/ chị tại site, em xin phép cập nhập tình trạng thiết bị:\n` +
    `+ Tên thiết bị liên quan: ${device}\n` +
    `+ Tình trạng thiết bị: ${status}\n` +
    `+ Processing Results: ${processing}\n` +
    `+ Thời gian khắc phục: ${timeStr}`
  );
}

function openContactModal() {
  // Mo modal truoc
  openModal("contact");

  // Sau do dien thong tin (dam bao DOM da san sang)
  const device    = _extractFromReport("thiết bị");
  const timeStart = _extractTimeFromReport();

  const deviceInput = $("#contact-device");
  if (deviceInput && device) deviceInput.value = device;
  if (timeStart) _setTimePicker("contact-time-start", timeStart);

  // Clear date pickers when opening modal
  const startDateInput = $("#contact-start-date");
  const endDateInput = $("#contact-end-date");
  if (startDateInput) startDateInput.value = "";
  if (endDateInput) endDateInput.value = "";

  // Bind submit moi lan mo de tranh mat onclick
  const btn = $("#contact-submit");
  if (btn) {
    btn.onclick = null;
    btn.onclick = () => {
      const text = _buildContactText();
      if (!text) return;

      setOutputText(text);
      fillBox(1);
      startCountdown();

      // Reset fields
      if (startDateInput) startDateInput.value = "";
      if (endDateInput) endDateInput.value = "";
      ["contact-time-start-h","contact-time-start-m",
       "contact-time-end-h","contact-time-end-m"].forEach(id => {
        const el = $(`#${id}`);
        if (el) el.value = "";
      });

      closeModal("contact");
    };
  }
}

function bindContactModal() {
  $("#contact-submit").onclick = () => {
    const text = _buildContactText();
    if (!text) return;

    setOutputText(text);
    fillBox(1);
    startCountdown();

    // Reset fields
    const startDateInput = $("#contact-start-date");
    const endDateInput = $("#contact-end-date");
    if (startDateInput) startDateInput.value = "";
    if (endDateInput) endDateInput.value = "";

    // Reset time pickers
    ["contact-time-start-h","contact-time-start-m",
     "contact-time-end-h","contact-time-end-m"].forEach(id => {
      const el = $(`#${id}`);
      if (el) el.value = "";
    });
    closeModal("contact");
  };
}

/* ── Status modal ─────────────────────────────────────────────── */
function bindStatusModal() {
  // Khong con confirmed/not_confirmed - tat ca fields luon enabled
  $$(".status-field").forEach(el => {
    el.disabled = false;
    el.style.opacity = "1";
  });

  // Filter devices when site changes
  const deptInput = $("#status-dept");
  if (deptInput) {
    deptInput.oninput = (e) => {
      const siteName = e.target.value.trim();
      updateDevicesDatalist(siteName);
    };
    
    // Show datalist immediately on focus/click to help arrow key selection
    deptInput.onfocus = () => {
      // In some browsers, clearing and restoring the value or double clicking shows the list
      // But for now, we just ensure it's up to date
    };
    
    // When an option is selected from the datalist, the input event fires.
    // If the value matches an option, we can immediately update the devices.
    deptInput.onchange = (e) => {
      const siteName = e.target.value.trim();
      updateDevicesDatalist(siteName);
    };
    
    // Trigger once on open to sync if already filled
    if (deptInput.value) updateDevicesDatalist(deptInput.value);
  }

  const deviceInput = $("#status-device");
  if (deviceInput) {
    deviceInput.onfocus = () => {
      // Ensure devices are loaded for the current site if not already
      if (deptInput.value) updateDevicesDatalist(deptInput.value);
    };
  }

  $("#status-submit").onclick = async () => {
    const btn = $("#status-submit");
    const originalText = btn.textContent;
    
    const body = {
      confirmed:   false,
      dept:        $("#status-dept").value.trim(),
      device:      $("#status-device").value.trim(),
      pic:         $("#status-pic").value,
      alarm_type:  $("#status-alarm-type").value,
      alarm_level: $("#status-alarm-level").value,
      status:      $("#status-done").value,
      week:        $("#status-week").value,
      start_time:  _getTimePicker("status-start"),
      start_date:  $("#status-start-date").value,
      end_time:    _getTimePicker("status-end"),
      end_date:    $("#status-end-date").value,
      desc:        $("#status-desc").value.trim(),
    };

    // Validate (Các trường có thể dùng hàm Excel được phép để trống)
    const missing = [];
    if (!body.dept)       missing.push("Site");
    if (!body.device)     missing.push("Thiết bị");
    if (!body.start_date) missing.push("Ngày bắt đầu");
    if (!body.start_time) missing.push("Giờ bắt đầu");
    if (!body.end_date)   missing.push("Ngày kết thúc");
    if (!body.end_time)   missing.push("Giờ kết thúc");
    if (!body.desc)       missing.push("Mô tả");

    if (missing.length > 0) {
      showToast("Thiếu thông tin", "Vui lòng điền: " + missing.join(", "));
      return;
    }

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Đang lưu...';

    try {
      const notice = $("#status-excel-notice");
      if (notice) notice.style.display = "block";
      const res = await apiFetch("/api/status", { method: "POST", body: JSON.stringify(body), timeout: 60000 });
      
      if (res.error) {
        showToast("Lỗi", res.error);
      } else {
        showToast("Thành công", "Đã gửi yêu cầu lưu Excel.");
        if (res.text) setOutputText(res.text);
        fillBox(2);
        closeModal("status");
      }
    } catch (err) {
      showToast("Lỗi kết nối", err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = originalText;
      const notice = $("#status-excel-notice");
      if (notice) notice.style.display = "none";
    }
  };
}

/* ── Notification modal ─────────────────────────────────────── */
function bindNotificationForm() {
  const btn = $("#notif-submit");
  if (!btn) return;
  btn.onclick = async () => {
    const now = new Date();
    const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    const body = {
      site:        $("#notif-site").value.trim(),
      description: $("#notif-description").value.trim(),
      start_time:  $("#notif-start-time").value.trim(),
      start_date:  $("#notif-start-date").value || today,
      end_time:    $("#notif-end-time").value.trim(),
      end_date:    $("#notif-end-date").value || today,
      devices:     $("#notif-devices").value.trim(),
      note:        $("#notif-note").value.trim(),
    };
    try {
      const res = await apiFetch("/api/notification", { method: "POST", body: JSON.stringify(body) });
      if (res.error) { showToast("Lỗi", res.error); return; }
      setOutputText(res.text);
      closeModal("note");
    } catch { showToast("Lỗi", "Không thể kết nối API"); }
  };
}

/* ── Note modal ──────────────────────────────────────────────── */
function bindNoteTabs() {
  $$("#note-modal .note-tab").forEach(tab => {
    tab.onclick = () => {
      $$("#note-modal .note-tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      $$(".note-panel").forEach(p => p.classList.add("hidden"));
      $(`#note-panel-${tab.dataset.tab}`).classList.remove("hidden");
      if (tab.dataset.tab === "view") loadNotesList();
    };
  });
}

function initNoteFormGrids() {
  // Render Days checkbox grid (1 to 31)
  const daysGrid = $("#note-days-grid");
  if (daysGrid) {
    daysGrid.innerHTML = "";
    for (let d = 1; d <= 31; d++) {
      const val = String(d);
      const label = document.createElement("label");
      label.innerHTML = `<input type="checkbox" name="note-day-cb" value="${val}"> ${val}`;
      daysGrid.appendChild(label);
    }
  }

  // Render Months checkbox grid (1 to 12)
  const monthsGrid = $("#note-months-grid");
  if (monthsGrid) {
    monthsGrid.innerHTML = "";
    for (let m = 1; m <= 12; m++) {
      const val = String(m);
      const label = document.createElement("label");
      label.innerHTML = `<input type="checkbox" name="note-month-cb" value="${val}"> T${val}`;
      monthsGrid.appendChild(label);
    }
  }

  // Bind Days select all
  const daysAll = $("#note-days-all");
  if (daysAll) {
    daysAll.onchange = function() {
      const cbs = $$("#note-days-grid input[type='checkbox']");
      cbs.forEach(cb => {
        cb.checked = this.checked;
        cb.parentElement.classList.toggle("checked", this.checked);
      });
    };
  }

  // Bind Months select all
  const monthsAll = $("#note-months-all");
  if (monthsAll) {
    monthsAll.onchange = function() {
      const cbs = $$("#note-months-grid input[type='checkbox']");
      cbs.forEach(cb => {
        cb.checked = this.checked;
        cb.parentElement.classList.toggle("checked", this.checked);
      });
    };
  }
  
  // Tag-along updates for "Select All" on individual checkbox changes
  document.addEventListener("change", e => {
    if (e.target && e.target.name === "note-day-cb") {
      const cbs = $$("#note-days-grid input[type='checkbox']");
      if (daysAll) daysAll.checked = cbs.every(cb => cb.checked);
      e.target.parentElement.classList.toggle("checked", e.target.checked);
    }
    if (e.target && e.target.name === "note-month-cb") {
      const cbs = $$("#note-months-grid input[type='checkbox']");
      if (monthsAll) monthsAll.checked = cbs.every(cb => cb.checked);
      e.target.parentElement.classList.toggle("checked", e.target.checked);
    }
  });
}

function updateNoteTimeTagsUI() {
  const container = $("#note-time-tags");
  if (!container) return;
  container.innerHTML = "";
  
  // Sort times ascending for better display
  state.noteTimeTags.sort();
  
  state.noteTimeTags.forEach(t => {
    const tag = document.createElement("span");
    tag.className = "time-tag";
    tag.innerHTML = `
      <span>${t}</span>
      <span class="remove-time-btn" data-time="${t}">&times;</span>
    `;
    container.appendChild(tag);
  });

  // Bind remove buttons
  $$(".remove-time-btn", container).forEach(btn => {
    btn.onclick = () => {
      const timeToRemove = btn.dataset.time;
      state.noteTimeTags = state.noteTimeTags.filter(t => t !== timeToRemove);
      updateNoteTimeTagsUI();
    };
  });
}

function resetNoteForm() {
  state.editingNoteStt = null;
  state.noteTimeTags = [];
  updateNoteTimeTagsUI();
  
  $("#note-keyword").value = "";
  $("#note-content").value = "";
  $("#note-emails").value = "";
  $("#note-time-input").value = "";
  $("#note-repeat-count").value = "1";
  $("#note-repeat-interval").value = "5";
  $("#note-mode").value = "Cố định";
  $("#note-delete-mode").value = "delete";
  
  // Uncheck grids
  $$("#note-days-grid input[type='checkbox']").forEach(cb => {
    cb.checked = false;
    cb.parentElement.classList.remove("checked");
  });
  $$("#note-months-grid input[type='checkbox']").forEach(cb => {
    cb.checked = false;
    cb.parentElement.classList.remove("checked");
  });
  if ($("#note-days-all")) $("#note-days-all").checked = false;
  if ($("#note-months-all")) $("#note-months-all").checked = false;

  // Reset text/buttons
  $("#note-form-title").textContent = "Tạo Nhắc Nhở Mới";
  $("#note-create-submit").textContent = "Thêm Nhắc";
  $("#note-edit-cancel").classList.add("hidden");

  // Sync user email chips
  syncUserEmailChips();
}

async function loadUserEmailsList() {
  try {
    const users = await apiFetch("/api/auth/users");
    state.userEmails = users || [];
    renderUserEmailChips();
  } catch (err) {
    console.error("Failed to load user emails list", err);
  }
}

function renderUserEmailChips() {
  const container = $("#note-user-select-container");
  if (!container) return;
  container.innerHTML = "";
  
  if (state.userEmails.length === 0) {
    container.innerHTML = `<span style="font-size:12px; color:var(--text-muted); padding:4px;">Không có email người dùng để chọn.</span>`;
    return;
  }
  
  state.userEmails.forEach(u => {
    const chip = document.createElement("span");
    chip.className = "user-email-chip";
    chip.dataset.email = u.email;
    chip.innerHTML = `<i class="far fa-user"></i> ${u.name} (${u.email})`;
    chip.onclick = () => toggleUserEmailSelection(u.email);
    container.appendChild(chip);
  });
  
  syncUserEmailChips();
}

function toggleUserEmailSelection(email) {
  const input = $("#note-emails");
  if (!input) return;
  let emails = input.value.split(",").map(e => e.trim()).filter(Boolean);
  
  if (emails.includes(email)) {
    emails = emails.filter(e => e !== email);
  } else {
    emails.push(email);
  }
  
  input.value = emails.join(", ");
  syncUserEmailChips();
}

function syncUserEmailChips() {
  const input = $("#note-emails");
  if (!input) return;
  const emails = input.value.split(",").map(e => e.trim()).filter(Boolean);
  
  $$(".user-email-chip").forEach(chip => {
    const email = chip.dataset.email;
    if (emails.includes(email)) {
      chip.classList.add("selected");
    } else {
      chip.classList.remove("selected");
    }
  });
}

function bindNoteCreate() {
  // Initialize grids first
  initNoteFormGrids();

  // Bind input on note-emails
  const inputEmails = $("#note-emails");
  if (inputEmails) {
    inputEmails.addEventListener("input", syncUserEmailChips);
  }

  // Add Time button
  const btnAddTime = $("#btn-add-time");
  if (btnAddTime) {
    btnAddTime.onclick = () => {
      const timeVal = $("#note-time-input").value;
      if (!timeVal) return;
      if (state.noteTimeTags.includes(timeVal)) {
        showToast("Lỗi", "Giờ này đã được thêm.");
        return;
      }
      state.noteTimeTags.push(timeVal);
      updateNoteTimeTagsUI();
      $("#note-time-input").value = "";
    };
  }

  // Cancel Edit button
  const btnCancelEdit = $("#note-edit-cancel");
  if (btnCancelEdit) {
    btnCancelEdit.onclick = () => {
      resetNoteForm();
      showToast("Thông tin", "Đã hủy chế độ chỉnh sửa.");
    };
  }

  // Form Submit
  $("#note-create-submit").onclick = async () => {
    const keyword = $("#note-keyword").value.trim();
    const content = $("#note-content").value.trim();
    const emailsRaw = $("#note-emails").value.trim();
    
    // Parse emails
    const emails = emailsRaw ? emailsRaw.split(",").map(e => e.trim()).filter(Boolean) : [];
    
    // Collect days
    const days = $$("#note-days-grid input[type='checkbox']:checked").map(cb => cb.value);
    
    // Collect months
    const months = $$("#note-months-grid input[type='checkbox']:checked").map(cb => cb.value);
    
    const repeat_count = parseInt($("#note-repeat-count").value) || 1;
    const repeat_interval = parseInt($("#note-repeat-interval").value) || 5;
    const mode = $("#note-mode").value;
    const delete_mode = $("#note-delete-mode").value;

    // Validations
    if (!keyword || !content) {
      showToast("Thiếu thông tin", "Vui lòng nhập Từ khóa và Nội dung nhắc nhở.");
      return;
    }
    if (state.noteTimeTags.length === 0) {
      showToast("Thiếu thông tin", "Vui lòng thêm ít nhất một giờ nhắc.");
      return;
    }
    if (days.length === 0) {
      showToast("Thiếu thông tin", "Vui lòng chọn ít nhất một ngày báo.");
      return;
    }
    if (months.length === 0) {
      showToast("Thiếu thông tin", "Vui lòng chọn ít nhất một tháng báo.");
      return;
    }

    // Email format validation
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    for (const email of emails) {
      if (!emailRegex.test(email)) {
        showToast("Sai định dạng", `Email "${email}" không đúng định dạng.`);
        return;
      }
    }

    const body = {
      keyword,
      content,
      times: state.noteTimeTags,
      days,
      months,
      mode,
      delete_mode,
      repeat_count,
      repeat_interval,
      emails,
      paused: false
    };

    const isEdit = state.editingNoteStt !== null;
    const path = isEdit ? `/api/notes/${state.editingNoteStt}` : "/api/notes";
    const method = isEdit ? "PUT" : "POST";

    try {
      const res = await apiFetch(path, { method, body: JSON.stringify(body) });
      if (res.error) {
        showToast("Lỗi", res.error);
        return;
      }
      
      showToast("Thành công", isEdit ? `Đã cập nhật note #${res.stt}` : `Đã tạo nhắc nhở thành công!`);
      
      resetNoteForm();
      
      // Chuyển sang tab Xem Note
      const tabView = $("#tab-note-view");
      if (tabView) tabView.click();
    } catch (err) {
      showToast("Lỗi", "Không thể kết nối đến máy chủ.");
    }
  };
}

function getNextTriggerTimeStr(note) {
  if (note.done) return "Đã xong";
  if (note.paused) return "Tạm dừng";
  
  const now = new Date();
  let closestTrigger = null;
  const currentYear = now.getFullYear();

  // Kiểm tra thời gian kích hoạt dự kiến cho năm nay và năm sau
  for (let year = currentYear; year <= currentYear + 1; year++) {
    for (const monthStr of note.months) {
      const month = parseInt(monthStr) - 1; // 0-11
      for (const dayStr of note.days) {
        const day = parseInt(dayStr);
        for (const timeStr of note.times) {
          const [h, m] = timeStr.split(":").map(Number);
          const triggerDate = new Date(year, month, day, h, m, 0, 0);
          
          // Kiểm tra ngày có hợp lệ hay không (tránh tràn ngày như 30/2)
          if (triggerDate.getFullYear() === year && triggerDate.getMonth() === month && triggerDate.getDate() === day) {
            if (triggerDate > now) {
              if (!closestTrigger || triggerDate < closestTrigger) {
                closestTrigger = triggerDate;
              }
            }
          }
        }
      }
    }
  }
  
  if (!closestTrigger) return "Hết hạn";
  
  const diffMs = closestTrigger - now;
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 60) {
    return `Còn ${diffMins} phút`;
  }
  const diffHours = Math.floor(diffMins / 60);
  const remMins = diffMins % 60;
  if (diffHours < 24) {
    return `Còn ${diffHours}g ${remMins}p`;
  }
  const diffDays = Math.floor(diffHours / 24);
  const remHours = diffHours % 24;
  return `Còn ${diffDays}n ${remHours}g`;
}

async function loadNotesList() {
  const loading = $("#note-table-loading");
  const table = $("#note-list-table");
  const empty = $("#note-empty-state");
  
  if (loading) loading.style.display = "block";
  if (table) table.style.display = "none";
  if (empty) empty.style.display = "none";

  try {
    const notes = await apiFetch("/api/notes");
    state.notesList = notes;
    
    // Cập nhật số lượng Badge trên thanh menu (các note đang hoạt động)
    const activeNotesCount = notes.filter(n => !n.done && !n.paused).length;
    const badge = $("#note-badge");
    if (badge) {
      if (activeNotesCount > 0) {
        badge.textContent = activeNotesCount;
        badge.classList.remove("hidden");
      } else {
        badge.classList.add("hidden");
      }
    }

    renderNotesTable(notes);
  } catch (err) {
    showToast("Lỗi", "Không tải được danh sách notes");
  } finally {
    if (loading) loading.style.display = "none";
  }
}

function renderNotesTable(notes) {
  const tbody = $("#notes-tbody");
  if (!tbody) return;
  tbody.innerHTML = "";
  
  const table = $("#note-list-table");
  const empty = $("#note-empty-state");

  if (notes.length === 0) {
    if (table) table.style.display = "none";
    if (empty) empty.style.display = "block";
    return;
  }

  if (table) table.style.display = "table";
  if (empty) empty.style.display = "none";

  notes.forEach(n => {
    const tr = document.createElement("tr");

    // Row styles
    let rowClass = "";
    if (n.done) {
      rowClass = "tag-done";
    } else if (n.paused) {
      rowClass = ""; // Normal look for paused
    } else if (n.mode === "1 lần") {
      rowClass = "tag-valid";
    } else {
      rowClass = "tag-recurring";
    }
    tr.className = rowClass;

    // Status Badge
    let statusBadgeHtml = "";
    if (n.done) {
      statusBadgeHtml = `<span class="status-badge done-status">Xong</span>`;
    } else if (n.paused) {
      statusBadgeHtml = `<span class="status-badge paused-status">Tắt</span>`;
    } else {
      statusBadgeHtml = `<span class="status-badge active-status">Bật</span>`;
    }

    // Nhắc tiếp
    const nextTrigger = getNextTriggerTimeStr(n);

    // Emails recipient list
    const emailsStr = n.emails && n.emails.length > 0 ? n.emails.join(", ") : "-";

    tr.innerHTML = `
      <td>${n.stt}</td>
      <td style="font-weight: 600; color: var(--text-primary);">${n.keyword}</td>
      <td style="max-width:180px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${n.content}">${n.content}</td>
      <td style="font-size:11px; font-weight: 500;">${n.times.join(", ")}</td>
      <td>${n.days.length === 31 ? "Tất cả" : n.days.join(", ")}</td>
      <td>${n.months.length === 12 ? "Tất cả" : n.months.join(", ")}</td>
      <td style="max-width:120px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${emailsStr}">${emailsStr}</td>
      <td>${statusBadgeHtml}</td>
      <td style="font-size:12px; font-weight:500;">${nextTrigger}</td>
      <td style="text-align:center;">
        <button class="action-icon-btn edit-btn" data-stt="${n.stt}" title="Sửa"><i class="fas fa-edit"></i></button>
        ${n.paused 
          ? `<button class="action-icon-btn resume-btn" data-stt="${n.stt}" title="Kích hoạt"><i class="fas fa-play"></i></button>`
          : `<button class="action-icon-btn pause-btn" data-stt="${n.stt}" title="Tạm dừng"><i class="fas fa-pause"></i></button>`
        }
        <button class="delete-row-btn" data-stt="${n.stt}" title="Xóa"><i class="fas fa-trash-alt"></i></button>
      </td>
    `;
    tbody.appendChild(tr);
  });

  // Bind Actions inside Table
  $$(".edit-btn", tbody).forEach(btn => {
    btn.onclick = () => {
      const stt = parseInt(btn.dataset.stt);
      const note = state.notesList.find(n => n.stt === stt);
      if (note) editNote(note);
    };
  });

  $$(".pause-btn", tbody).forEach(btn => {
    btn.onclick = async () => {
      const stt = parseInt(btn.dataset.stt);
      await togglePauseResume(stt, "pause");
    };
  });

  $$(".resume-btn", tbody).forEach(btn => {
    btn.onclick = async () => {
      const stt = parseInt(btn.dataset.stt);
      await togglePauseResume(stt, "resume");
    };
  });

  $$(".delete-row-btn", tbody).forEach(btn => {
    btn.onclick = async () => {
      const stt = btn.dataset.stt;
      if (!confirm(`Bạn có chắc chắn muốn xóa nhắc nhở #${stt}?`)) return;
      try {
        const res = await apiFetch(`/api/notes/${stt}`, { method: "DELETE" });
        if (res.error) {
          showToast("Lỗi", res.error);
          return;
        }
        showToast("Thành công", `Đã xóa nhắc nhở #${stt}`);
        loadNotesList();
      } catch (err) {
        showToast("Lỗi", "Không xóa được");
      }
    };
  });
}

function editNote(note) {
  state.editingNoteStt = note.stt;
  
  // Điền dữ liệu vào form
  $("#note-keyword").value = note.keyword;
  $("#note-content").value = note.content;
  $("#note-emails").value = note.emails ? note.emails.join(", ") : "";
  $("#note-repeat-count").value = note.repeat_count || 1;
  $("#note-repeat-interval").value = note.repeat_interval || 5;
  $("#note-mode").value = note.mode || "Cố định";
  $("#note-delete-mode").value = note.delete_mode || "delete";
  
  // Load times
  state.noteTimeTags = [...note.times];
  updateNoteTimeTagsUI();
  
  // Check checkboxes trong grid ngày
  $$("#note-days-grid input[type='checkbox']").forEach(cb => {
    cb.checked = note.days.includes(cb.value);
    cb.parentElement.classList.toggle("checked", cb.checked);
  });
  const allDays = $$("#note-days-grid input[type='checkbox']");
  if ($("#note-days-all")) $("#note-days-all").checked = allDays.every(cb => cb.checked);
  
  // Check checkboxes trong grid tháng
  $$("#note-months-grid input[type='checkbox']").forEach(cb => {
    cb.checked = note.months.includes(cb.value);
    cb.parentElement.classList.toggle("checked", cb.checked);
  });
  const allMonths = $$("#note-months-grid input[type='checkbox']");
  if ($("#note-months-all")) $("#note-months-all").checked = allMonths.every(cb => cb.checked);
  
  // Đổi title và text button submit
  $("#note-form-title").textContent = `Chỉnh sửa Nhắc Nhở #${note.stt}`;
  $("#note-create-submit").textContent = "Cập nhật";
  $("#note-edit-cancel").classList.remove("hidden");

  // Sync user email chips
  syncUserEmailChips();
  
  // Click tab Tạo Note để hiển thị form
  const tabCreate = $("#tab-note-create");
  if (tabCreate) tabCreate.click();
}

async function togglePauseResume(stt, action) {
  try {
    const res = await apiFetch(`/api/notes/${stt}/${action}`, { method: "PATCH" });
    if (res.error) {
      showToast("Lỗi", res.error);
      return;
    }
    showToast("Thành công", action === "pause" ? `Đã tạm dừng note #${stt}` : `Đã kích hoạt lại note #${stt}`);
    loadNotesList();
  } catch (err) {
    showToast("Lỗi", "Không thể kết nối API");
  }
}

function bindNoteSearch() {
  const searchInput = $("#note-search");
  if (!searchInput) return;
  searchInput.addEventListener("input", function () {
    const kw = this.value.toLowerCase();
    const filtered = state.notesList.filter(n =>
      n.keyword.toLowerCase().includes(kw) || n.content.toLowerCase().includes(kw)
    );
    renderNotesTable(filtered);
  });
}

/* ── Notification form inside Note modal ────────────────────── */
function bindNotifFormInNote() {
  const now = new Date();
  const todayVal = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  const sd = $("#notif-start-date");
  const ed = $("#notif-end-date");
  if (sd) sd.value = todayVal;
  if (ed) ed.value = todayVal;
}

/* ── DAVITEQ image viewer ────────────────────────────────────── */
let daviteqInited = false;
let daviteqCats   = {};

async function initDaviteqViewer() {
  if (daviteqInited) return;
  daviteqInited = true;

  const catList = $("#img-cat-list");
  catList.innerHTML = `<span class="spinner"></span>`;

  try {
    daviteqCats = await apiFetch("/api/images/categories");
    catList.innerHTML = "";

    Object.keys(daviteqCats).forEach((cat, i) => {
      const btn = document.createElement("button");
      btn.className = "img-cat-btn";
      btn.textContent = cat;
      btn.onclick = () => {
        $$(".img-cat-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        renderImgSubList(cat);
      };
      catList.appendChild(btn);
      if (i === 0) { btn.classList.add("active"); renderImgSubList(cat); }
    });
  } catch {
    catList.innerHTML = `<span style="color:var(--red);font-size:11px;">Lỗi tải</span>`;
  }
}

function renderImgSubList(cat) {
  const subList = $("#img-sub-list");
  subList.innerHTML = "";
  const sites = daviteqCats[cat] || [];

  sites.forEach((site, i) => {
    const btn = document.createElement("button");
    btn.className = "img-sub-btn";
    btn.textContent = site;
    btn.onclick = () => {
      $$(".img-sub-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      loadImgGrid(cat, site);
    };
    subList.appendChild(btn);
    if (i === 0) { btn.classList.add("active"); loadImgGrid(cat, site); }
  });
}

async function loadImgGrid(cat, site) {
  const grid = $("#img-grid");
  grid.innerHTML = `<span class="spinner"></span>`;

  try {
    const images = await apiFetch(`/api/images/${cat}/${site}`);
    grid.innerHTML = "";
    if (!images.length) {
      grid.innerHTML = `<span style="color:var(--text-muted);font-size:12px;">Không có ảnh</span>`;
      return;
    }
    images.forEach(img => {
      const el = document.createElement("div");
      el.className = "img-thumb";
      el.innerHTML = `<img src="${API}${img.url}" alt="${img.name}" loading="lazy"><span>${img.name}</span>`;
      el.onclick = () => window.open(`${API}${img.url}`, "_blank");
      grid.appendChild(el);
    });
  } catch {
    grid.innerHTML = `<span style="color:var(--red);font-size:12px;">Lỗi tải ảnh</span>`;
  }
}

/* ── Documentary viewer ──────────────────────────────────────── */
let docFiles = [];

async function initDocumentViewer() {
  await loadDocList();
  bindDocSearch();
}

async function loadDocList(q = "", mode = "name") {
  const tbody = $("#docs-tbody");
  tbody.innerHTML = `<tr><td colspan="5"><span class="spinner"></span></td></tr>`;
  try {
    const params = new URLSearchParams({ q, mode });
    docFiles = await apiFetch(`/api/docs?${params}`);
    renderDocTable(docFiles);
  } catch {
    tbody.innerHTML = `<tr><td colspan="5" style="color:var(--red)">Lỗi tải tài liệu</td></tr>`;
  }
}

function renderDocTable(files) {
  const tbody = $("#docs-tbody");
  tbody.innerHTML = "";
  files.forEach(f => {
    const tr = document.createElement("tr");
    const pill = f.is_downloaded
      ? `<span class="tag-pill pill-green">✓ Đã tải</span>`
      : `<span class="tag-pill pill-red">Chưa tải</span>`;
    tr.innerHTML = `
      <td>${f.stt}</td>
      <td>${f.tags}</td>
      <td>${f.name}</td>
      <td><button class="action-btn doc-dl-btn" data-id="${f.id}" data-name="${f.name}">⇩</button></td>
      <td>${pill}</td>
    `;
    tbody.appendChild(tr);
  });

  $$(".doc-dl-btn", tbody).forEach(btn => {
    btn.onclick = async () => {
      btn.disabled = true;
      btn.innerHTML = `<span class="spinner"></span>`;
      try {
        const res = await apiFetch(`/api/docs/download/${btn.dataset.id}`, { method: "POST" });
        if (res.error) { showToast("Lỗi", res.error); }
        else {
          showToast("Đã tải", `${btn.dataset.name}`);
          await loadDocList($("#doc-search").value, $(".doc-mode-btn.active")?.dataset.mode || "name");
        }
      } catch { showToast("Lỗi", "Tải thất bại"); }
      btn.disabled = false;
      btn.innerHTML = "⇩";
    };
  });
}

function bindDocSearch() {
  const searchInput  = $("#doc-search");
  const modeBtns     = $$(".doc-mode-btn");

  searchInput.addEventListener("input", function () {
    const mode = $(".doc-mode-btn.active")?.dataset.mode || "name";
    loadDocList(this.value.trim(), mode);
  });

  modeBtns.forEach(btn => {
    btn.onclick = () => {
      modeBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      loadDocList(searchInput.value.trim(), btn.dataset.mode);
    };
  });

  $("#doc-refresh").onclick = async () => {
    await apiFetch("/api/docs/refresh", { method: "POST" });
    loadDocList();
  };
}

/* ── Background sync ─────────────────────────────────────────── */
async function triggerBackgroundSync() {
  if (!state.graphAuthenticated) {
    showToast("Lỗi Sync", "Chưa xác thực OneDrive, vui lòng làm theo hướng dẫn.");
    await startDeviceFlowAuth();
    return;
  }

  try {
    state.needsRefresh = true;
    await apiFetch("/api/sync", { method: "POST" });
    showToast("Đồng bộ", "Đang đồng bộ dữ liệu từ OneDrive...");
    await loadSites(); // Reload sites config in case it changed on OneDrive
  } catch (err) {
    showToast("Lỗi Sync", err.message || "Không thể đồng bộ");
  }
}

let authPollInterval = null;

async function startDeviceFlowAuth() {
  const modal = $("#device-auth-modal");
  if (!modal) return;
  modal.classList.add("open");

  $("#auth-link-input").value = "";
  $("#auth-code-input").value = "Đang tải mã...";
  const statusEl = $("#auth-polling-status");
  statusEl.textContent = "Đang khởi tạo...";

  try {
    const res = await apiFetch("/api/auth/graph/device-flow", { method: "POST" });
    if (res.status === "error") {
      statusEl.textContent = "Lỗi: " + res.message;
      return;
    }

    $("#auth-link-input").value = res.verification_uri || "https://microsoft.com/devicelogin";
    $("#auth-code-input").value = res.user_code;
    statusEl.textContent = "⏳ Đang chờ người dùng thao tác...";

    if (authPollInterval) clearInterval(authPollInterval);
    
    // Poll the backend to check if the user completed flow
    authPollInterval = setInterval(async () => {
      try {
        const pollRes = await apiFetch("/api/auth/graph/device-flow/poll");
        if (pollRes.status === "success") {
          clearInterval(authPollInterval);
          authPollInterval = null;
          state.graphAuthenticated = true;
          statusEl.textContent = "✅ Đăng nhập OneDrive thành công!";
          statusEl.style.color = "var(--success-color)";
          
          showToast("Xác thực thành công", "Đã xác thực, đang tự động đồng bộ...");
          setTimeout(() => {
            modal.classList.remove("open");
            triggerBackgroundSync();
          }, 1500);
        } else if (pollRes.status === "error") {
          clearInterval(authPollInterval);
          authPollInterval = null;
          statusEl.textContent = "Lỗi: " + (pollRes.message || "Không xác định");
        }
      } catch (err) {
        console.error("Poll device flow error", err);
      }
    }, 4000);

  } catch (err) {
    statusEl.textContent = "Lỗi khởi tạo: " + err.message;
  }
}

// Ensure polling interval is cleared when modal is closed manually
document.addEventListener("DOMContentLoaded", () => {
  $$(".btn-close-modal").forEach(btn => {
    btn.addEventListener("click", () => {
      if (authPollInterval && !$("#device-auth-modal").classList.contains("open")) {
        clearInterval(authPollInterval);
        authPollInterval = null;
      }
    });
  });
});

/* ── Notification poller ─────────────────────────────────────── */
function startNotificationPoller() {
  let _pollTimer   = null;
  let _controller  = null;
  let _running     = false;

  async function poll() {
    if (!state.authenticated || document.hidden) return;

    // Hủy request cũ nếu còn treo
    if (_controller) _controller.abort();
    _controller = new AbortController();

    try {
      const notifs = await apiFetch("/api/notes/pending", {
        signal: _controller.signal,
      });
      if (!Array.isArray(notifs)) return;
      notifs.forEach(n => {
        showReminder(n.keyword, n.content, n.time || "");
        if (Notification.permission === "granted") {
          new Notification(n.keyword, { body: n.content });
        }
      });
    } catch (err) {
      if (err.name !== "AbortError") {
        console.warn("[NotePoller] Lỗi kết nối:", err.message);
      }
    } finally {
      _controller = null;
    }
  }

  function start() {
    if (_running) return;
    _running  = true;
    // Poll ngay khi tab được mở lại (không chờ 15s)
    poll();
    _pollTimer = setInterval(poll, 15000);
  }

  function stop() {
    _running = false;
    if (_controller) { _controller.abort(); _controller = null; }
    if (_pollTimer)  { clearInterval(_pollTimer); _pollTimer = null; }
  }

  // Điểm mấu chốt: dừng khi tab ẩn, resume khi quay lại
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      stop();
    } else {
      // Chờ 1s để tránh burst nhiều request cùng lúc khi nhiều tab mở
      setTimeout(start, 1000);
    }
  });

  // Bắt đầu lần đầu
  start();

  // Yêu cầu quyền thông báo
  if (Notification.permission === "default") {
    Notification.requestPermission();
  }
}

/* ── Group tabs ─────────────────────────────────────────────── */
function bindGroupTabs() {
  $$(".group-tab").forEach(tab => {
    tab.onclick = () => {
      renderSiteList(tab.dataset.group);
      // Reset active item
      if (state.activeItemBtn) state.activeItemBtn.classList.remove("active");
      state.activeItemBtn  = null;
      state.currentSiteKey = null;
    };
  });
}



/* ── Reminder overlay ───────────────────────────────────────── */
const _reminderQueue = [];
let _reminderShowing = false;
let _currentReminder = null;

function showReminder(keyword, content, time) {
  _reminderQueue.push({ keyword, content, time });
  if (!_reminderShowing) _showNextReminder();
}

function _showNextReminder() {
  if (_reminderQueue.length === 0) {
    _reminderShowing = false;
    _currentReminder = null;
    return;
  }
  _reminderShowing = true;
  const reminder = _reminderQueue.shift();
  _currentReminder = reminder;
  const { keyword, content, time } = reminder;
  $("#reminder-keyword").textContent = keyword;
  $("#reminder-content").textContent = content;
  $("#reminder-time").textContent    = `⏰ ${time}`;
  $("#reminder-overlay").classList.add("open");
}

function closeReminder() {
  $("#reminder-overlay").classList.remove("open");
  // Hien cai tiep theo neu con trong queue
  setTimeout(_showNextReminder, 300);
}

function snoozeReminder() {
  if (!_currentReminder) return;
  const reminderToSnooze = { ..._currentReminder };
  closeReminder();
  
  // Nhắc lại sau 5 phút
  setTimeout(() => {
    showReminder(reminderToSnooze.keyword, reminderToSnooze.content, reminderToSnooze.time);
  }, 5 * 60 * 1000);
}

/* ── Charts ────────────────────────────────────────────────── */
function showChartsModal() {
  window.open("/charts.html", "_blank");
}

/* ── Boot ────────────────────────────────────────────────────── */
document.addEventListener("DOMContentLoaded", () => {
  handleAuthQueryHint();
  initTheme();
  
  const boots = [
    bindThemeToggle, initSidebarResize, bindItemSearch,
    bindAuthButtons, bindGroupTabs, bindSiteSearch, bindOutputActions,
    bindModalCloses, bindAdminModal, bindContactModal, bindStatusModal,
    bindNoteCreate, bindNoteTabs, bindNoteSearch, bindNotifFormInNote,
    bindNotificationForm
  ];

  boots.forEach(fn => {
    try {
      fn();
    } catch (err) {
      console.warn(`Boot component failed: ${fn.name}`, err);
    }
  });

  checkAuth();
});

/* ── Theme toggle ────────────────────────────────────────────── */
function initTheme() {
  const saved = localStorage.getItem("rmc-theme") || "dark";
  applyTheme(saved);
}

function applyTheme(theme) {
  const btn = $("#btn-theme");
  if (theme === "light") {
    document.documentElement.setAttribute("data-theme", "light");
    if (btn) btn.textContent = "☀️";
  } else {
    document.documentElement.removeAttribute("data-theme");
    if (btn) btn.textContent = "🌙";
  }
  localStorage.setItem("rmc-theme", theme);
}

function bindThemeToggle() {
  const btn = $("#btn-theme");
  if (!btn) return;
  btn.onclick = () => {
    const current = document.documentElement.getAttribute("data-theme");
    applyTheme(current === "light" ? "dark" : "light");
  };
}

/* ── Sidebar resize ──────────────────────────────────────────── */
function initSidebarResize() {
  const sidebar  = $("#sidebar");
  const resizer  = $("#sidebar-resizer");
  const app      = $("#app");
  if (!resizer) return;

  let startX = 0;
  let startW = 0;

  resizer.addEventListener("mousedown", e => {
    startX = e.clientX;
    startW = sidebar.getBoundingClientRect().width;
    resizer.classList.add("dragging");
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    function onMove(e) {
      const newW = Math.min(480, Math.max(150, startW + (e.clientX - startX)));
      sidebar.style.width = newW + "px";
      app.style.gridTemplateColumns = `${newW}px 1fr`;
    }
    function onUp() {
      resizer.classList.remove("dragging");
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      // Lưu width vào localStorage
      localStorage.setItem("sidebar-width", sidebar.style.width);
    }
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  });

  // Khôi phục width đã lưu
  const saved = localStorage.getItem("sidebar-width");
  if (saved) {
    sidebar.style.width = saved;
    app.style.gridTemplateColumns = `${saved} 1fr`;
  }
}

/* ── Item search (tìm thiết bị) ──────────────────────────────── */
function bindItemSearch() {
  const input = $("#item-search");
  if (!input) return;

  input.addEventListener("input", function () {
    const kw = this.value.toLowerCase().trim();
    $$(".item-btn").forEach(btn => {
      const match = kw === "" || btn.textContent.toLowerCase().includes(kw);
      btn.style.display = match ? "" : "none";
    });
  });
}