/* lan-nav 前端逻辑 */
(function () {
  "use strict";

  const THEME_KEY = "lan-nav-theme";
  const COLLAPSE_KEY = "lan-nav-collapsed";
  const SIZE_KEY = "lan-nav-card-size";
  const SIZE_OPTIONS = ["sm", "md", "lg"];
  const SHAPE_KEY = "lan-nav-icon-shape";
  const SHAPE_OPTIONS = ["rounded", "circle"];

  const KEY_STORAGE = "lan-nav-key";
  const KEY_HEADER = "X-Nav-Key";

  // 访客 / 登录状态：服务端未配置 KEY 时视为完全开放（兼容旧行为）
  const auth = {
    required: false, // 服务端是否配置了 KEY
    authenticated: false, // 当前是否已通过密钥校验
    mobile: false, // 手机端强制访客模式
  };

  function detectMobile() {
    const ua = navigator.userAgent || "";
    if (
      /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini|Mobile|Windows Phone/i.test(
        ua
      )
    ) {
      return true;
    }
    // iPadOS 等以桌面 UA 呈现的设备：触控 + 粗指针 + 小屏
    const coarse =
      typeof window.matchMedia === "function" && window.matchMedia("(pointer: coarse)").matches;
    const touchPoints = navigator.maxTouchPoints || 0;
    const smallScreen =
      Math.min(window.screen.width || 0, window.screen.height || 0) <= 1100;
    return coarse && touchPoints > 1 && smallScreen;
  }

  function readStoredKey() {
    try {
      return sessionStorage.getItem(KEY_STORAGE) || "";
    } catch (_) {
      return "";
    }
  }

  function storeKey(value) {
    try {
      if (value) sessionStorage.setItem(KEY_STORAGE, value);
      else sessionStorage.removeItem(KEY_STORAGE);
    } catch (_) {
      /* 隐私模式下 storage 可能不可用，退化为仅当前会话内存态 */
    }
  }

  // 当前请求应携带的密钥：手机端永不携带，退化为只读访客
  function activeKey() {
    if (auth.mobile) return "";
    return auth.authenticated ? readStoredKey() : "";
  }

  // 是否可以执行任何写操作（新增 / 编辑 / 删除 / 排序 / 导入）
  function canEdit() {
    if (auth.mobile) return false;
    if (!auth.required) return true;
    return auth.authenticated;
  }

  const state = {
    site: { title: "", subtitle: "", theme: "system" },
    categories: [],
    links: [],
    meta: { uncategorized_id: "" },
    query: "",
  };

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  function toast(message, isError) {
    const wrap = $("#toastWrap");
    const el = document.createElement("div");
    el.className = "toast" + (isError ? " error" : "");
    el.textContent = message;
    wrap.appendChild(el);
    setTimeout(() => el.remove(), 3200);
  }

  function collapsedMap() {
    try {
      return JSON.parse(localStorage.getItem(COLLAPSE_KEY) || "{}") || {};
    } catch {
      return {};
    }
  }

  function setCollapsed(id, value) {
    const map = collapsedMap();
    if (value) map[id] = true;
    else delete map[id];
    localStorage.setItem(COLLAPSE_KEY, JSON.stringify(map));
  }

  function hydrateIcons(root) {
    $$( "[data-icon]", root || document).forEach((el) => {
      const name = el.getAttribute("data-icon");
      if (!name || el.dataset.hydrated === "1") return;
      el.innerHTML = window.LucideIcons.svg(name);
      el.dataset.hydrated = "1";
    });
  }

  function hostnameOf(url) {
    try {
      return new URL(url).host;
    } catch {
      return url;
    }
  }

  function faviconCandidate(url) {
    try {
      const u = new URL(url);
      return u.origin + "/favicon.ico";
    } catch {
      return "";
    }
  }

  function initialColor(seed) {
    let h = 0;
    const s = String(seed || "?");
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
    const hue = h % 360;
    return `hsl(${hue} 48% 42%)`;
  }

  function letterAvatar(title, color) {
    const ch = (title || "?").trim().charAt(0).toUpperCase() || "?";
    return `<span class="fav" style="background:${escapeHtml(color || initialColor(title))}" aria-hidden="true">${escapeHtml(ch)}</span>`;
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function iconSrc(ref) {
    const v = String(ref || "").trim();
    if (!v) return "";
    if (v.startsWith("data:") || v.startsWith("http://") || v.startsWith("https://") || v.startsWith("/")) return v;
    if (v.startsWith("icon/")) return "/" + v;
    return v;
  }

  function renderFav(link) {
    const color = link.color || initialColor(link.title);
    const custom = iconSrc(link.icon_url);
    if (custom) {
      return `<span class="fav fav-url"><img src="${escapeHtml(custom)}" alt="" loading="lazy" referrerpolicy="no-referrer" data-fallback-title="${escapeHtml(link.title)}" data-fallback-color="${escapeHtml(color)}" /></span>`;
    }
    if (link.icon && window.LucideIcons.has(link.icon)) {
      return `<span class="fav lucide" style="background:${escapeHtml(color)}">${window.LucideIcons.svg(link.icon)}</span>`;
    }
    const ico = faviconCandidate(link.url);
    if (ico) {
      return `<span class="fav" style="background:${escapeHtml(color)}"><img src="${escapeHtml(ico)}" alt="" loading="lazy" referrerpolicy="no-referrer" data-fallback-title="${escapeHtml(link.title)}" data-fallback-color="${escapeHtml(color)}" /></span>`;
    }
    return letterAvatar(link.title, color);
  }

  async function api(path, options) {
    const opts = options || {};
    const headers = Object.assign({ Accept: "application/json" }, opts.headers || {});
    if (opts.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
    const key = activeKey();
    if (key) headers[KEY_HEADER] = key;
    const res = await fetch(String(path || "").replace(/^\//, ""), {
      method: opts.method || "GET",
      headers,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    let json = null;
    try {
      json = await res.json();
    } catch {
      json = null;
    }
    if (!res.ok || !json || json.success === false) {
      const msg = (json && json.error && json.error.message) || `请求失败 (${res.status})`;
      const code = (json && json.error && json.error.code) || "ERROR";
      const err = new Error(msg);
      err.code = code;
      err.status = res.status;
      throw err;
    }
    return json.data;
  }

  function matchQuery(link, catName) {
    const q = state.query.trim().toLowerCase();
    if (!q) return true;
    const hay = [
      link.title,
      link.description,
      link.url,
      catName,
      ...(link.tags || []),
    ]
      .join(" ")
      .toLowerCase();
    return hay.includes(q);
  }

  function updateClock() {
    const el = $("#clock");
    if (!el) return;
    const now = new Date();
    const fmt = new Intl.DateTimeFormat("zh-CN", {
      weekday: "short",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
    el.textContent = fmt.format(now);
    el.dateTime = now.toISOString();
  }

  function resolveTheme() {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved === "light" || saved === "dark") return saved;
    const prefer = state.site.theme;
    if (prefer === "light" || prefer === "dark") return prefer;
    return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  }

  function syncSegButtons(rootSel, dataAttr, value) {
    $$(rootSel + " .size-btn").forEach((btn) => {
      const on = btn.getAttribute(dataAttr) === value;
      btn.setAttribute("aria-pressed", on ? "true" : "false");
      btn.classList.toggle("is-active", on);
    });
  }

  function applyTheme() {
    const theme = resolveTheme();
    document.documentElement.setAttribute("data-theme", theme);
    syncSegButtons("#themeSwitch", "data-theme-choice", theme);
  }

  function setTheme(theme) {
    if (theme !== "light" && theme !== "dark") return;
    localStorage.setItem(THEME_KEY, theme);
    applyTheme();
  }

  function resolveCardSize() {
    const saved = localStorage.getItem(SIZE_KEY);
    return SIZE_OPTIONS.includes(saved) ? saved : "md";
  }

  function applyCardSize(size) {
    const s = SIZE_OPTIONS.includes(size) ? size : "md";
    document.documentElement.setAttribute("data-card-size", s);
    localStorage.setItem(SIZE_KEY, s);
    syncSegButtons("#sizeSwitch", "data-size", s);
  }

  function resolveIconShape() {
    const saved = localStorage.getItem(SHAPE_KEY);
    return SHAPE_OPTIONS.includes(saved) ? saved : "rounded";
  }

  function applyIconShape(shape) {
    const s = SHAPE_OPTIONS.includes(shape) ? shape : "rounded";
    document.documentElement.setAttribute("data-icon-shape", s);
    localStorage.setItem(SHAPE_KEY, s);
    syncSegButtons("#iconShapeSwitch", "data-shape", s);
  }

  let modalOpts = null;

  function openModal(opts) {
    modalOpts = opts;
    const backdrop = $("#modalBackdrop");
    $("#modalTitle").textContent = opts.title || "对话框";
    $("#modalBody").innerHTML = opts.body || "";
    const foot = $("#modalFoot");
    foot.innerHTML = "";
    if (opts.cancelText !== false) {
      const cancel = document.createElement("button");
      cancel.type = "button";
      cancel.className = "btn btn-ghost";
      cancel.textContent = opts.cancelText || "取消";
      cancel.addEventListener("click", () => closeModal(false));
      foot.appendChild(cancel);
    }
    if (opts.extraButtons) {
      opts.extraButtons.forEach((b) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "btn " + (b.className || "");
        btn.textContent = b.text;
        btn.addEventListener("click", async () => {
          if (btn.disabled) return;
          btn.disabled = true;
          try {
            const ok = await b.onClick();
            if (ok !== false) closeModal(true);
          } catch (e) {
            toast((e && e.message) || "操作失败", true);
          } finally {
            btn.disabled = false;
          }
        });
        foot.appendChild(btn);
      });
    }
    if (opts.confirmText !== false) {
      const ok = document.createElement("button");
      ok.type = "button";
      ok.className = "btn btn-primary";
      ok.textContent = opts.confirmText || "确定";
      ok.addEventListener("click", async () => {
        if (ok.disabled) return;
        if (!opts.onConfirm) {
          closeModal(true);
          return;
        }
        ok.disabled = true;
        try {
          const result = await opts.onConfirm();
          if (result !== false) closeModal(true);
        } catch (e) {
          toast((e && e.message) || "操作失败", true);
        } finally {
          ok.disabled = false;
        }
      });
      foot.appendChild(ok);
    }
    backdrop.hidden = false;
    backdrop.classList.remove("hidden");
    hydrateIcons(backdrop);
    if ($("#lIconData")) bindIconPicker();
  }

  let iconCropCleanup = null;

  function closeModal(confirmed) {
    if (iconCropCleanup) {
      iconCropCleanup();
      iconCropCleanup = null;
    }
    const backdrop = $("#modalBackdrop");
    backdrop.classList.add("hidden");
    backdrop.hidden = true;
    if (!confirmed && modalOpts && modalOpts.onCancel) modalOpts.onCancel();
    modalOpts = null;
  }

  function bindIconPicker() {
    const preview = $("#lIconPreview");
    const dataInput = $("#lIconData");
    const fileInput = $("#lIconFile");
    const pickBtn = $("#lIconPick");
    const clearBtn = $("#lIconClear");
    const cropWrap = $("#lIconCropWrap");
    const cropBox = $("#lIconCrop");
    const cropImg = $("#lIconCropImg");
    const zoomInput = $("#lIconZoom");
    const cropOk = $("#lIconCropOk");
    const cropCancel = $("#lIconCropCancel");
    if (!preview || !dataInput || !fileInput || !cropBox || !cropImg) return;

    const CROP_OUT = 128;
    let objectUrl = "";
    let zoom = 1;
    let ox = 0;
    let oy = 0;
    let dragging = false;
    let lastX = 0;
    let lastY = 0;
    let cropOpen = false;

    function revoke() {
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
        objectUrl = "";
      }
    }

    iconCropCleanup = () => {
      cropOpen = false;
      dragging = false;
      revoke();
    };

    function setPreview(src) {
      if (src) {
        preview.innerHTML = `<img alt="" src="${escapeHtml(src)}" />`;
        if (clearBtn) clearBtn.hidden = false;
      } else {
        preview.innerHTML = `<span class="icon-picker-empty">无</span>`;
        if (clearBtn) clearBtn.hidden = true;
      }
    }

    function hideCrop() {
      cropOpen = false;
      dragging = false;
      cropWrap.classList.add("hidden");
      cropWrap.hidden = true;
      revoke();
      cropImg.removeAttribute("src");
    }

    function layoutCrop() {
      if (!cropOpen || !cropImg.naturalWidth) return;
      const bw = cropBox.clientWidth;
      const bh = cropBox.clientHeight;
      const nw = cropImg.naturalWidth;
      const nh = cropImg.naturalHeight;
      const base = Math.max(bw / nw, bh / nh);
      const s = base * zoom;
      const dw = nw * s;
      const dh = nh * s;
      ox = Math.min(0, Math.max(bw - dw, ox));
      oy = Math.min(0, Math.max(bh - dh, oy));
      cropImg.style.width = dw + "px";
      cropImg.style.height = dh + "px";
      cropImg.style.left = ox + "px";
      cropImg.style.top = oy + "px";
    }

    function openCrop(file) {
      if (!file || !file.type.startsWith("image/")) {
        toast("请选择图片文件", true);
        return;
      }
      if (file.size > 8 * 1024 * 1024) {
        toast("图片过大（上限 8MB）", true);
        return;
      }
      revoke();
      objectUrl = URL.createObjectURL(file);
      zoom = 1;
      if (zoomInput) zoomInput.value = "1";
      cropImg.onload = () => {
        const bw = cropBox.clientWidth;
        const bh = cropBox.clientHeight;
        const nw = cropImg.naturalWidth;
        const nh = cropImg.naturalHeight;
        const base = Math.max(bw / nw, bh / nh);
        const dw = nw * base;
        const dh = nh * base;
        ox = (bw - dw) / 2;
        oy = (bh - dh) / 2;
        cropOpen = true;
        layoutCrop();
      };
      cropImg.onerror = () => {
        toast("无法读取该图片", true);
        hideCrop();
      };
      cropWrap.classList.remove("hidden");
      cropWrap.hidden = false;
      cropImg.src = objectUrl;
    }

    pickBtn.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", () => {
      const file = fileInput.files && fileInput.files[0];
      fileInput.value = "";
      if (file) openCrop(file);
    });
    clearBtn.addEventListener("click", () => {
      dataInput.value = "";
      setPreview("");
      hideCrop();
    });
    if (zoomInput) {
      zoomInput.addEventListener("input", () => {
        zoom = Number(zoomInput.value) || 1;
        layoutCrop();
      });
    }
    cropCancel.addEventListener("click", hideCrop);
    cropOk.addEventListener("click", () => {
      if (!cropImg.naturalWidth) return;
      const bw = cropBox.clientWidth;
      const bh = cropBox.clientHeight;
      const nw = cropImg.naturalWidth;
      const nh = cropImg.naturalHeight;
      const base = Math.max(bw / nw, bh / nh);
      const s = base * zoom;
      const sx = -ox / s;
      const sy = -oy / s;
      const sw = bw / s;
      const sh = bh / s;
      const canvas = document.createElement("canvas");
      canvas.width = CROP_OUT;
      canvas.height = CROP_OUT;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = "high";
      ctx.drawImage(cropImg, sx, sy, sw, sh, 0, 0, CROP_OUT, CROP_OUT);
      const dataUrl = canvas.toDataURL("image/png");
      dataInput.value = dataUrl;
      setPreview(dataUrl);
      hideCrop();
    });

    cropBox.addEventListener("pointerdown", (e) => {
      if (!cropOpen) return;
      dragging = true;
      lastX = e.clientX;
      lastY = e.clientY;
      cropBox.setPointerCapture(e.pointerId);
    });
    cropBox.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      ox += e.clientX - lastX;
      oy += e.clientY - lastY;
      lastX = e.clientX;
      lastY = e.clientY;
      layoutCrop();
    });
    const stopDrag = () => {
      dragging = false;
    };
    cropBox.addEventListener("pointerup", stopDrag);
    cropBox.addEventListener("pointercancel", stopDrag);
  }

  function categoryForm(cat) {
    const c = cat || { name: "", description: "" };
    return `
      <div class="field">
        <label for="fName">名称</label>
        <input id="fName" value="${escapeHtml(c.name)}" required maxlength="60" />
      </div>
      <div class="field">
        <label for="fDesc">描述</label>
        <input id="fDesc" value="${escapeHtml(c.description || "")}" maxlength="200" />
      </div>
    `;
  }

  function linkForm(link) {
    const l = link || {
      title: "",
      url: "",
      description: "",
      category_id: state.meta.uncategorized_id,
      tags: [],
      icon_url: "",
      icon: "",
      color: "#6366f1",
      pinned: false,
      status: "normal",
    };
    const options = state.categories
      .map(
        (c) =>
          `<option value="${escapeHtml(c.id)}" ${c.id === l.category_id ? "selected" : ""}>${escapeHtml(c.name)}</option>`
      )
      .join("");
    return `
      <div class="field">
        <label for="lTitle">标题</label>
        <input id="lTitle" value="${escapeHtml(l.title)}" required maxlength="80" />
      </div>
      <div class="field">
        <label for="lUrl">URL</label>
        <input id="lUrl" value="${escapeHtml(l.url)}" required placeholder="https:// 或内网地址" />
      </div>
      <div class="field">
        <label for="lDesc">描述</label>
        <textarea id="lDesc" maxlength="300">${escapeHtml(l.description || "")}</textarea>
      </div>
      <div class="field">
        <label for="lCat">分类</label>
        <select id="lCat">${options}</select>
      </div>
      <div class="field field-hidden" aria-hidden="true">
        <label for="lTags">标签（逗号分隔）</label>
        <input id="lTags" value="${escapeHtml((l.tags || []).join(", "))}" />
      </div>
      <div class="field">
        <label>图标（可选）</label>
        <div class="icon-picker">
          <div class="icon-picker-preview" id="lIconPreview">${
            l.icon_url
              ? `<img alt="" src="${escapeHtml(iconSrc(l.icon_url))}" />`
              : `<span class="icon-picker-empty">无</span>`
          }</div>
          <div class="icon-picker-actions">
            <button type="button" class="btn btn-ghost btn-sm" id="lIconPick">选择图片</button>
            <button type="button" class="btn btn-ghost btn-sm" id="lIconClear"${l.icon_url ? "" : " hidden"}>清除</button>
          </div>
          <input type="file" id="lIconFile" accept="image/*" hidden />
          <input type="hidden" id="lIconData" value="${escapeHtml(l.icon_url || "")}" />
        </div>
        <p class="hint">从本地选择图片后裁剪为正方形图标</p>
      </div>
      <div class="icon-crop-wrap hidden" id="lIconCropWrap" hidden>
        <div class="icon-crop" id="lIconCrop" aria-label="拖动调整裁剪位置">
          <img id="lIconCropImg" alt="" />
        </div>
        <label class="icon-crop-zoom">
          <span>缩放</span>
          <input type="range" id="lIconZoom" min="1" max="3" step="0.02" value="1" />
        </label>
        <div class="icon-picker-actions">
          <button type="button" class="btn btn-primary btn-sm" id="lIconCropOk">完成裁剪</button>
          <button type="button" class="btn btn-ghost btn-sm" id="lIconCropCancel">取消</button>
        </div>
      </div>
      <div class="field-row">
        <div class="field">
          <label for="lIcon">Lucide 图标名</label>
          <input id="lIcon" value="${escapeHtml(l.icon || "")}" list="iconList" />
        </div>
        <div class="field">
          <label for="lColor">主题色</label>
          <input id="lColor" type="color" value="${escapeHtml((l.color || "#6366f1").slice(0, 7))}" />
        </div>
      </div>
      <div class="field field-hidden" aria-hidden="true">
        <label for="lStatus">状态</label>
        <select id="lStatus">
          <option value="normal" ${l.status === "normal" ? "selected" : ""}>normal</option>
          <option value="warning" ${l.status === "warning" ? "selected" : ""}>warning</option>
          <option value="offline" ${l.status === "offline" ? "selected" : ""}>offline</option>
        </select>
      </div>
      <label class="check-row"><input id="lPinned" type="checkbox" ${l.pinned ? "checked" : ""} /> 置顶</label>
      <datalist id="iconList">${window.LucideIcons.names.map((n) => `<option value="${n}"></option>`).join("")}</datalist>
    `;
  }

  function readCategoryForm() {
    return {
      name: $("#fName").value.trim(),
      description: $("#fDesc").value.trim(),
    };
  }

  function readLinkForm() {
    return {
      title: $("#lTitle").value.trim(),
      url: $("#lUrl").value.trim(),
      description: $("#lDesc").value.trim(),
      category_id: $("#lCat").value,
      tags: $("#lTags").value,
      icon_url: $("#lIconData") ? $("#lIconData").value.trim() : "",
      icon: $("#lIcon").value.trim(),
      color: $("#lColor").value,
      status: $("#lStatus").value,
      pinned: $("#lPinned").checked,
    };
  }

  /* ---------------- 排序模式（拖动分组 / 卡片） ---------------- */

  const SORT_LABEL_IDLE = "编辑排序";
  const SORT_LABEL_ACTIVE = "保存排序";
  const DRAG_THRESHOLD = 6;

  let sortMode = false;
  let dragCtx = null;
  let dragScrollTimer = 0;
  let dragScrollDelta = 0;

  function syncSortButton() {
    const btn = $("#btnSortToggle");
    if (!btn) return;
    btn.setAttribute("aria-pressed", sortMode ? "true" : "false");
    btn.classList.toggle("is-active", sortMode);
    const icon = $(".sort-toggle-icon", btn);
    if (icon) icon.innerHTML = window.LucideIcons.svg(sortMode ? "check" : "grip");
    const label = $(".sort-toggle-label", btn);
    if (label) label.textContent = sortMode ? SORT_LABEL_ACTIVE : SORT_LABEL_IDLE;
    btn.setAttribute(
      "title",
      sortMode ? "保存当前顺序" : "进入排序模式：拖动分组与卡片调整顺序"
    );
  }

  function setSortMode(active, opts) {
    const options = opts || {};
    if (active && !canEdit()) return;
    sortMode = !!active;
    document.documentElement.classList.toggle("sort-mode", sortMode);
    if (!sortMode && dragCtx) endDrag();
    if (sortMode) {
      state.query = "";
      hideCtxMenu();
      render();
    }
    syncSortButton();
    if (!options.silent) {
      toast(
        sortMode
          ? "拖动分组标题或卡片右侧的手柄调整顺序，完成后点「保存排序」"
          : "已退出排序模式"
      );
    }
  }

  function collectOrder() {
    const sections = $$("#main > .category");
    const catIds = sections.map((sec) => sec.getAttribute("data-cat-id")).filter(Boolean);
    // 分类内顺序（全局 order）：同一链接只在所属分类出现一次
    const linkIds = [];
    const seen = new Set();
    sections.forEach((sec) => {
      $$(".link-card", sec).forEach((card) => {
        const id = card.getAttribute("data-link-id");
        if (!id || seen.has(id)) return;
        seen.add(id);
        linkIds.push(id);
      });
    });
    // 置顶区顺序（独立 pin_order），与分类顺序互不影响
    const pinnedIds = $$("#pinnedGrid .link-card")
      .map((card) => card.getAttribute("data-link-id"))
      .filter(Boolean);
    return { catIds, linkIds, pinnedIds };
  }

  async function saveSortOrder() {
    const btn = $("#btnSortToggle");
    const { catIds, linkIds, pinnedIds } = collectOrder();
    if (btn) btn.disabled = true;
    try {
      if (catIds.length > 1) {
        await api("/api/categories/reorder", { method: "POST", body: { ids: catIds } });
      }
      if (linkIds.length > 1) {
        await api("/api/links/reorder", { method: "POST", body: { ids: linkIds } });
      }
      if (pinnedIds.length > 1) {
        await api("/api/links/pin-reorder", { method: "POST", body: { ids: pinnedIds } });
      }
      await reload();
      setSortMode(false, { silent: true });
      if (btn) btn.classList.remove("is-dirty");
      toast("排序已保存");
    } catch (e) {
      toast("保存失败：" + e.message, true);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function beginDrag(e) {
    if (!sortMode || dragCtx || !canEdit()) return;
    if (e.pointerType === "mouse" && e.button !== 0) return;

    const target = e.target;
    const handle = target && target.closest ? target.closest(".drag-handle") : null;
    const card = target && target.closest ? target.closest(".link-card") : null;
    // 鼠标可直接拖动卡片；触摸必须从手柄开始，避免和页面滚动冲突
    if (!handle && !(card && e.pointerType === "mouse")) return;

    let el = null;
    let container = null;
    let itemSelector = "";
    let kind = "";
    if (handle && handle.getAttribute("data-drag") === "cat") {
      el = handle.closest(".category");
      container = $("#main");
      itemSelector = ".category";
      kind = "cat";
    } else if (card) {
      el = card;
      container = card.parentElement;
      itemSelector = ".link-card";
      kind = "link";
    }
    if (!el || !container || !container.children.length) return;

    // 阻止 <a> 的原生 HTML5 拖拽，否则浏览器会在移动时转入 native drag，
    // 从而中断 pointermove，卡片无法排序（分组按钮不受影响）。
    if (e.cancelable) e.preventDefault();

    dragCtx = {
      el,
      container,
      itemSelector,
      kind,
      pointerId: e.pointerId,
      startX: e.clientX,
      startY: e.clientY,
      moved: false,
    };
    window.addEventListener("pointermove", onDragMove, { passive: false });
    window.addEventListener("pointerup", endDrag);
    window.addEventListener("pointercancel", endDrag);
  }

  function onDragMove(e) {
    const c = dragCtx;
    if (!c || e.pointerId !== c.pointerId) return;
    if (!c.moved) {
      const dx = e.clientX - c.startX;
      const dy = e.clientY - c.startY;
      if (dx * dx + dy * dy < DRAG_THRESHOLD * DRAG_THRESHOLD) return;
      c.moved = true;
      c.el.classList.add("is-dragging");
      document.documentElement.classList.add("is-drag-active");
      if (c.el.setPointerCapture) {
        try {
          c.el.setPointerCapture(e.pointerId);
        } catch (_) {}
      }
    }
    e.preventDefault();
    placeDragged(e.clientX, e.clientY);
    autoScroll(e.clientY);
  }

  function placeDragged(x, y) {
    const c = dragCtx;
    if (!c) return;
    const siblings = Array.from(c.container.children).filter(
      (n) => n !== c.el && n.matches(c.itemSelector)
    );
    if (!siblings.length) return;

    if (c.kind === "cat") {
      let ref = null;
      for (const s of siblings) {
        const r = s.getBoundingClientRect();
        if (y < r.top + r.height / 2) {
          ref = s;
          break;
        }
      }
      if (ref) {
        if (c.el.nextElementSibling !== ref) c.container.insertBefore(c.el, ref);
      } else if (c.container.lastElementChild !== c.el) {
        c.container.appendChild(c.el);
      }
      return;
    }

    let best = null;
    let bestDist = Infinity;
    for (const s of siblings) {
      const r = s.getBoundingClientRect();
      const dx = x - (r.left + r.width / 2);
      const dy = y - (r.top + r.height / 2);
      const d = dx * dx + dy * dy;
      if (d < bestDist) {
        bestDist = d;
        best = s;
      }
    }
    if (!best) return;
    const rect = best.getBoundingClientRect();
    if (x > rect.left + rect.width / 2) {
      if (best.nextElementSibling !== c.el) best.after(c.el);
    } else if (best.previousElementSibling !== c.el) {
      best.before(c.el);
    }
  }

  function autoScroll(y) {
    const margin = 96;
    let delta = 0;
    if (y < margin) delta = -Math.min(28, Math.ceil((margin - y) / 5));
    else if (y > window.innerHeight - margin) {
      delta = Math.min(28, Math.ceil((y - (window.innerHeight - margin)) / 5));
    }
    dragScrollDelta = delta;
    if (!delta) {
      stopAutoScroll();
      return;
    }
    if (dragScrollTimer) return;
    dragScrollTimer = setInterval(() => {
      if (dragScrollDelta) window.scrollBy(0, dragScrollDelta);
    }, 40);
  }

  function stopAutoScroll() {
    if (dragScrollTimer) {
      clearInterval(dragScrollTimer);
      dragScrollTimer = 0;
    }
    dragScrollDelta = 0;
  }

  function endDrag(e) {
    const c = dragCtx;
    if (!c) return;
    if (e && e.pointerId !== undefined && e.pointerId !== c.pointerId) return;
    if (c.moved) {
      c.el.classList.remove("is-dragging");
      document.documentElement.classList.remove("is-drag-active");
      if (c.el.releasePointerCapture) {
        try {
          c.el.releasePointerCapture(c.pointerId);
        } catch (_) {}
      }
      const btn = $("#btnSortToggle");
      if (btn) btn.classList.add("is-dirty");
    }
    dragCtx = null;
    stopAutoScroll();
    window.removeEventListener("pointermove", onDragMove);
    window.removeEventListener("pointerup", endDrag);
    window.removeEventListener("pointercancel", endDrag);
  }

  function renderLinkCard(link) {
    const classes = ["link-card"];
    if (link.pinned) classes.push("is-pinned-card");
    const handle = `<span class="drag-handle" data-drag="link" aria-hidden="true">${window.LucideIcons.svg("grip")}</span>`;
    return `<a class="${classes.join(" ")}" href="${escapeHtml(link.url)}" target="_blank" rel="noopener noreferrer" data-link-id="${escapeHtml(link.id)}" style="--card-accent:${escapeHtml(link.color || "#6366f1")}">
      ${handle}
      <div class="link-top">${renderFav(link)}
        <div>
          <h3 class="link-title">${escapeHtml(link.title)}</h3>
          ${link.description ? `<p class="link-desc">${escapeHtml(link.description)}</p>` : ""}
        </div>
      </div>
      <div class="link-domain">${escapeHtml(hostnameOf(link.url))}</div>
    </a>`;
  }

  function render() {
    const title = state.site.title || "局域网导航";
    document.title = title;
    $("#siteTitle").textContent = title;

    const catById = Object.fromEntries(state.categories.map((c) => [c.id, c]));
    const collapsed = collapsedMap();
    const filteredLinks = state.links.filter((lk) =>
      matchQuery(lk, (catById[lk.category_id] || {}).name || "")
    );
    const pinned = filteredLinks.filter((lk) => lk.pinned);

    const pinnedSection = $("#pinnedSection");
    const pinnedGrid = $("#pinnedGrid");
    if (pinned.length) {
      pinnedSection.classList.remove("hidden");
      pinnedGrid.innerHTML = pinned.map((lk) => renderLinkCard(lk)).join("");
    } else {
      pinnedSection.classList.add("hidden");
      pinnedGrid.innerHTML = "";
    }

    const nav = $("#anchorNav");
    const visibleCats = state.categories.filter((c) => {
      const links = filteredLinks.filter((lk) => lk.category_id === c.id);
      if (state.query) return links.length > 0;
      if (c.id === state.meta.uncategorized_id) return links.length > 0;
      return true;
    });

    nav.innerHTML = visibleCats
      .map((c) => `<a href="#cat-${escapeHtml(c.id)}">${escapeHtml(c.name)}</a>`)
      .join("");

    const main = $("#main");
    main.innerHTML = visibleCats
      .map((c) => {
        const links = filteredLinks
          .filter((lk) => lk.category_id === c.id)
          .sort((a, b) => a.order - b.order || String(a.title).localeCompare(String(b.title)));
        const isCollapsed = !!collapsed[c.id];
        return `<section class="category ${isCollapsed ? "collapsed" : ""}" id="cat-${escapeHtml(c.id)}" data-cat-id="${escapeHtml(c.id)}">
          <div class="category-panel" data-cat-panel="${escapeHtml(c.id)}">
            <div class="category-head">
              <div class="cat-meta">
                <h2>${escapeHtml(c.name)}</h2>
                <p>${escapeHtml(c.description || "")} · ${links.length} 个链接</p>
              </div>
              <button type="button" class="drag-handle drag-handle-cat" data-drag="cat" aria-label="拖动分组排序">
                ${window.LucideIcons.svg("grip")}
              </button>
              <button type="button" class="cat-toggle" data-act="toggle-cat" data-id="${escapeHtml(c.id)}" aria-expanded="${!isCollapsed}" aria-label="折叠分类">
                ${window.LucideIcons.svg(isCollapsed ? "chevron-down" : "chevron-up")}
              </button>
            </div>
            <div class="category-body">
              <div class="link-grid">
                ${
                  links.length
                    ? links.map(renderLinkCard).join("")
                    : `<div class="empty-card" style="grid-column:1/-1;padding:1.2rem"><p>此分类暂无链接 · 右键分组可新增</p></div>`
                }
              </div>
            </div>
          </div>
        </section>`;
      })
      .join("");

    const empty = $("#emptyState");
    const addWrap = $("#addCategoryWrap");
    if (!visibleCats.length && state.query) {
      empty.classList.remove("hidden");
      $("#emptyTitle").textContent = "无匹配结果";
      $("#emptyDesc").textContent = "试试其他关键词，或按 Esc 清空搜索。";
      main.innerHTML = "";
      pinnedSection.classList.add("hidden");
    } else if (!visibleCats.length && !state.categories.filter((c) => c.id !== state.meta.uncategorized_id).length) {
      empty.classList.remove("hidden");
      $("#emptyTitle").textContent = "暂无内容";
      $("#emptyDesc").textContent = "点击下方「新增分类」开始添加，或在分组上右键管理。";
      main.innerHTML = "";
    } else {
      empty.classList.add("hidden");
    }
    if (addWrap) addWrap.classList.toggle("hidden", !!state.query || !canEdit());

    hydrateIcons(document);
    bindFavfallbacks();
    syncAuthUI();
  }

  function bindFavfallbacks() {
    $$(".fav img").forEach((img) => {
      img.addEventListener(
        "error",
        () => {
          const title = img.getAttribute("data-fallback-title") || "?";
          const color = img.getAttribute("data-fallback-color") || initialColor(title);
          const wrap = img.parentElement;
          if (wrap) wrap.outerHTML = letterAvatar(title, color);
        },
        { once: true }
      );
    });
  }

  async function reload() {
    const data = await api("/api/navigation");
    state.site = data.site;
    state.categories = data.categories;
    state.links = data.links;
    state.meta = data.meta || state.meta;
    const meta = data.meta || {};
    if (typeof meta.requires_key === "boolean") auth.required = meta.requires_key;
    if (auth.mobile) {
      // 手机端强制访客，忽略任何已存的密钥
      auth.authenticated = false;
    } else {
      auth.authenticated = !!meta.authenticated;
      if (!auth.authenticated) storeKey("");
    }
    applyTheme();
    render();
  }

  function findLink(id) {
    return state.links.find((l) => l.id === id);
  }

  function findCat(id) {
    return state.categories.find((c) => c.id === id);
  }

  function syncAuthUI() {
    const btn = $("#btnLogin");
    if (btn) {
      // 手机端仅访客模式，不提供登录入口；未启用 KEY 时也无需登录
      const show = auth.required && !auth.mobile;
      btn.classList.toggle("hidden", !show);
      const label = $("#btnLoginLabel");
      const icon = $("[data-icon]", btn);
      if (auth.authenticated) {
        if (label) label.textContent = "退出";
        btn.setAttribute("title", "已登录，点击退出");
        if (icon) {
          icon.dataset.hydrated = "1";
          icon.innerHTML = window.LucideIcons.svg("unlock");
        }
      } else {
        if (label) label.textContent = "登录";
        btn.setAttribute("title", "输入访问密钥以解锁编辑");
        if (icon) {
          icon.dataset.hydrated = "1";
          icon.innerHTML = window.LucideIcons.svg("lock");
        }
      }
    }
    // 访客模式隐藏导入 / 导出入口（均为数据级操作）
    const importBtn = $("#btnImport");
    if (importBtn) importBtn.classList.toggle("hidden", !canEdit());
    const exportBtn = $("#btnExport");
    if (exportBtn) exportBtn.classList.toggle("hidden", !canEdit());
    document.documentElement.classList.toggle("guest-mode", !canEdit());
  }

  function openLogin() {
    openModal({
      title: "登录",
      body: `
        <div class="field">
          <label for="authKey">访问密钥</label>
          <input id="authKey" type="password" autocomplete="current-password" placeholder="请输入 KEY" />
        </div>
        <p class="hint">输入正确的密钥后解锁添加 / 编辑 / 删除等功能。</p>
      `,
      confirmText: "登录",
      onConfirm: async () => {
        const input = $("#authKey");
        const value = input ? input.value.trim() : "";
        if (!value) {
          toast("请输入访问密钥", true);
          return false;
        }
        storeKey(value);
        auth.authenticated = true;
        try {
          await api("/api/login", { method: "POST" });
        } catch (e) {
          auth.authenticated = false;
          storeKey("");
          toast(e.message || "密钥错误", true);
          return false;
        }
        await reload();
        toast("已登录，可编辑");
        return true;
      },
    });
    setTimeout(() => {
      const input = $("#authKey");
      if (input) input.focus();
    }, 30);
  }

  function logout() {
    auth.authenticated = false;
    storeKey("");
    if (sortMode) setSortMode(false, { silent: true });
    reload().catch(() => {});
    toast("已退出登录");
  }

  function openAddCategory() {
    openModal({
      title: "新增分类",
      body: categoryForm(),
      confirmText: "创建",
      onConfirm: async () => {
        try {
          await api("/api/categories", { method: "POST", body: readCategoryForm() });
          await reload();
          toast("分类已创建");
          return true;
        } catch (e) {
          toast(e.message, true);
          return false;
        }
      },
    });
  }

  function openAddLink(categoryId) {
    const base = {
      title: "",
      url: "",
      description: "",
      category_id: categoryId || state.meta.uncategorized_id,
      tags: [],
      icon_url: "",
      icon: "",
      color: "#6366f1",
      pinned: false,
      status: "normal",
    };
    openModal({
      title: "新增链接",
      body: linkForm(base),
      confirmText: "创建",
      onConfirm: async () => {
        try {
          await api("/api/links", { method: "POST", body: readLinkForm() });
          await reload();
          toast("链接已创建");
          return true;
        } catch (e) {
          toast(e.message, true);
          return false;
        }
      },
    });
  }

  function openEditLink(id) {
    const link = findLink(id);
    if (!link) return;
    openModal({
      title: "编辑链接",
      body: linkForm(link),
      confirmText: "保存",
      onConfirm: async () => {
        try {
          await api(`/api/links/${id}`, { method: "PUT", body: readLinkForm() });
          await reload();
          toast("已保存");
          return true;
        } catch (e) {
          toast(e.message, true);
          return false;
        }
      },
    });
  }

  function openDeleteLink(id) {
    const link = findLink(id);
    openModal({
      title: "删除链接",
      body: `<p>确定删除「${escapeHtml(link ? link.title : id)}」？此操作不可撤销。</p>`,
      confirmText: "删除",
      onConfirm: async () => {
        try {
          await api(`/api/links/${id}`, { method: "DELETE" });
          await reload();
          toast("已删除");
          return true;
        } catch (e) {
          toast(e.message, true);
          return false;
        }
      },
    });
    setTimeout(() => {
      const btns = $$("#modalFoot .btn-primary");
      if (btns[0]) btns[0].classList.add("btn-danger");
    }, 0);
  }

  function openEditCategory(id) {
    const cat = findCat(id);
    if (!cat) return;
    openModal({
      title: "编辑分类",
      body: categoryForm(cat),
      confirmText: "保存",
      onConfirm: async () => {
        try {
          await api(`/api/categories/${id}`, {
            method: "PUT",
            body: readCategoryForm(),
          });
          await reload();
          toast("分类已更新");
          return true;
        } catch (e) {
          toast(e.message, true);
          return false;
        }
      },
    });
  }

  function openDeleteCategory(id) {
    if (id === state.meta.uncategorized_id) {
      toast("不能删除「未分类」", true);
      return;
    }
    const cat = findCat(id);
    openModal({
      title: "删除分类",
      body: `<p>确定删除分类「${escapeHtml(cat ? cat.name : id)}」？</p>
        <p class="hint">请选择链接处理方式：</p>`,
      confirmText: false,
      extraButtons: [
        {
          text: "删除分类及全部链接",
          className: "btn-danger",
          onClick: async () => {
            try {
              await api(`/api/categories/${id}?action=delete_links`, {
                method: "DELETE",
              });
              await reload();
              toast("分类已删除");
              return true;
            } catch (e) {
              toast(e.message, true);
              return false;
            }
          },
        },
        {
          text: "链接移至未分类",
          className: "btn-primary",
          onClick: async () => {
            try {
              await api(`/api/categories/${id}?action=move_uncategorized`, {
                method: "DELETE",
              });
              await reload();
              toast("分类已删除，链接已迁移");
              return true;
            } catch (e) {
              toast(e.message, true);
              return false;
            }
          },
        },
      ],
    });
  }

  function copyTextSync(text) {
    const value = String(text || "");
    if (!value) return false;

    // iOS Safari：须在用户手势内同步执行；HTTP / 非安全上下文下 clipboard API 常不可用
    const ta = document.createElement("textarea");
    ta.value = value;
    ta.setAttribute("readonly", "");
    ta.setAttribute("aria-hidden", "true");
    ta.style.cssText =
      "position:fixed;top:0;left:0;width:1px;height:1px;padding:0;margin:0;border:0;opacity:0;font-size:16px;";
    document.body.appendChild(ta);

    const selected =
      document.getSelection && document.getSelection().rangeCount > 0
        ? document.getSelection().getRangeAt(0)
        : null;

    let ok = false;
    try {
      ta.focus();
      ta.select();
      ta.setSelectionRange(0, value.length);
      ok = document.execCommand("copy");
    } catch (_) {
      ok = false;
    }

    document.body.removeChild(ta);
    if (selected && document.getSelection) {
      const sel = document.getSelection();
      sel.removeAllRanges();
      sel.addRange(selected);
    }
    return ok;
  }

  async function copyText(text) {
    if (copyTextSync(text)) return true;
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      try {
        await navigator.clipboard.writeText(String(text || ""));
        return true;
      } catch (_) {
        return false;
      }
    }
    return false;
  }

  function copyLink(id) {
    const link = findLink(id);
    if (!link) return false;
    // 优先同步复制，保证 iOS 仍处于点击手势上下文中
    if (copyTextSync(link.url)) {
      toast("已复制地址");
      return true;
    }
    return copyText(link.url).then((ok) => {
      if (ok) toast("已复制地址");
      else toast("复制失败，请长按链接手动复制", true);
      return ok;
    });
  }

  function openLink(id) {
    const link = findLink(id);
    if (link) window.open(link.url, "_blank", "noopener,noreferrer");
  }

  function hideCtxMenu() {
    const menu = $("#ctxMenu");
    if (!menu) return;
    menu.classList.add("hidden");
    menu.hidden = true;
    menu.innerHTML = "";
  }

  function linkMenuItems(id) {
    const items = [
      { id: "open", label: "打开链接", run: () => openLink(id) },
      { id: "copy", label: "复制链接", run: () => copyLink(id) },
    ];
    if (canEdit()) {
      items.push({ sep: true });
      items.push({ id: "edit", label: "编辑链接", run: () => openEditLink(id) });
      items.push({ id: "del", label: "删除链接", danger: true, run: () => openDeleteLink(id) });
    }
    return items;
  }

  function catMenuItems(catId) {
    if (!canEdit()) return [];
    const isUncat = catId === state.meta.uncategorized_id;
    const items = [
      { id: "add-link", label: "新增链接", run: () => openAddLink(catId) },
      { id: "edit-cat", label: "编辑分类", run: () => openEditCategory(catId) },
    ];
    if (!isUncat) {
      items.push({ sep: true });
      items.push({
        id: "del-cat",
        label: "删除分类",
        danger: true,
        run: () => openDeleteCategory(catId),
      });
    }
    return items;
  }

  function resolveCtxTarget(el) {
    const linkEl = el && el.closest ? el.closest(".link-card") : null;
    if (linkEl) {
      return {
        kind: "link",
        el: linkEl,
        items: linkMenuItems(linkEl.getAttribute("data-link-id")),
      };
    }
    const panel = el && el.closest ? el.closest("[data-cat-panel]") : null;
    if (panel) {
      const items = catMenuItems(panel.getAttribute("data-cat-panel"));
      if (!items.length) return null;
      return {
        kind: "cat",
        el: panel,
        items,
      };
    }
    return null;
  }

  function showCtxMenu(x, y, items) {
    const menu = $("#ctxMenu");
    if (!menu) return;
    menu.innerHTML = items
      .map((it) => {
        if (it.sep) return `<div class="ctx-sep" role="separator"></div>`;
        const danger = it.danger ? " ctx-item-danger" : "";
        const disabled = it.disabled ? " disabled" : "";
        return `<button type="button" class="ctx-item${danger}" role="menuitem" data-ctx="${escapeHtml(it.id)}"${disabled ? " disabled" : ""}>${escapeHtml(it.label)}</button>`;
      })
      .join("");
    menu.classList.remove("hidden");
    menu.hidden = false;

    const pad = 8;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    menu.style.left = "0px";
    menu.style.top = "0px";
    const rect = menu.getBoundingClientRect();
    let left = x;
    let top = y;
    if (left + rect.width > vw - pad) left = Math.max(pad, vw - rect.width - pad);
    if (top + rect.height > vh - pad) top = Math.max(pad, vh - rect.height - pad);
    menu.style.left = left + "px";
    menu.style.top = top + "px";

    menu.onclick = async (e) => {
      const btn = e.target.closest("[data-ctx]");
      if (!btn || btn.disabled) return;
      e.preventDefault();
      e.stopPropagation();
      const action = btn.getAttribute("data-ctx");
      const item = items.find((i) => i.id === action);
      // 复制必须在 hide 之前同步执行，否则 iOS 会丢失用户手势导致失败
      let result;
      if (item && item.run) result = item.run();
      hideCtxMenu();
      if (result && typeof result.then === "function") await result;
    };
  }

  function openCtxAt(el, x, y) {
    const hit = resolveCtxTarget(el);
    if (!hit) return false;
    showCtxMenu(x, y, hit.items);
    return true;
  }

  function bindLongPress() {
    const LONG_MS = 480;
    const MOVE_PX = 12;
    let timer = null;
    let startX = 0;
    let startY = 0;
    let targetEl = null;
    let fired = false;
    let suppressClickUntil = 0;

    function clearTimer() {
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
    }

    function onStart(e) {
      if (sortMode) return;
      if (e.touches && e.touches.length !== 1) return;
      const t = e.touches ? e.touches[0] : e;
      const hit = resolveCtxTarget(e.target);
      if (!hit) return;
      clearTimer();
      fired = false;
      targetEl = hit.el;
      startX = t.clientX;
      startY = t.clientY;
      timer = setTimeout(() => {
        fired = true;
        suppressClickUntil = Date.now() + 700;
        if (navigator.vibrate) {
          try {
            navigator.vibrate(18);
          } catch (_) {}
        }
        openCtxAt(targetEl, startX, startY);
      }, LONG_MS);
    }

    function onMove(e) {
      if (!timer) return;
      const t = e.touches ? e.touches[0] : e;
      if (!t) return;
      const dx = t.clientX - startX;
      const dy = t.clientY - startY;
      if (dx * dx + dy * dy > MOVE_PX * MOVE_PX) clearTimer();
    }

    function onEnd() {
      clearTimer();
      targetEl = null;
    }

    document.addEventListener("touchstart", onStart, { passive: true });
    document.addEventListener("touchmove", onMove, { passive: true });
    document.addEventListener("touchend", onEnd, { passive: true });
    document.addEventListener("touchcancel", onEnd, { passive: true });

    // 长按弹出菜单后，吞掉随后的 click，避免误打开链接
    document.addEventListener(
      "click",
      (e) => {
        if (Date.now() < suppressClickUntil && e.target.closest(".link-card")) {
          e.preventDefault();
          e.stopPropagation();
        }
      },
      true
    );

    // 部分 Android 会在长按后仍触发 contextmenu，与桌面共用即可
    return { wasLongPress: () => fired };
  }

  async function handleAction(act, id, event) {
    if (event) {
      event.preventDefault();
      event.stopPropagation();
    }
    if (act === "toggle-cat") {
      const next = !collapsedMap()[id];
      setCollapsed(id, next);
      render();
    }
  }

  async function exportConfig() {
    try {
      const exportHeaders = {};
      const exportKey = activeKey();
      if (exportKey) exportHeaders[KEY_HEADER] = exportKey;
      const res = await fetch("api/export", { headers: exportHeaders });
      if (!res.ok) {
        let msg = `导出失败 (${res.status})`;
        try {
          const json = await res.json();
          if (json && json.error && json.error.message) msg = json.error.message;
        } catch {
          /* ignore */
        }
        throw new Error(msg);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "navigation.zip";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast("配置已导出");
    } catch (e) {
      toast("导出失败：" + e.message, true);
    }
  }

  function openImportConfirm(file) {
    if (!file) return;
    if (!canEdit()) {
      toast("访客模式不能导入配置", true);
      return;
    }
    const name = file.name || "所选文件";
    openModal({
      title: "导入配置",
      body: `<p>将用 <strong>${escapeHtml(name)}</strong> 覆盖当前全部导航数据。</p><p class="modal-hint">此操作不可撤销，建议先导出备份。</p>`,
      confirmText: "确认导入",
      onConfirm: async () => {
        try {
          if (file.size > 16 * 1024 * 1024) {
            toast("配置文件过大（上限 16MB）", true);
            return false;
          }
          const fd = new FormData();
          fd.append("file", file);
          const importHeaders = { Accept: "application/json" };
          const importKey = activeKey();
          if (importKey) importHeaders[KEY_HEADER] = importKey;
          const res = await fetch("api/import", {
            method: "POST",
            headers: importHeaders,
            body: fd,
          });
          let json = null;
          try {
            json = await res.json();
          } catch {
            json = null;
          }
          if (!res.ok || !json || json.success === false) {
            const msg = (json && json.error && json.error.message) || `导入失败 (${res.status})`;
            throw new Error(msg);
          }
          const result = json.data;
          await reload();
          toast(`已导入 ${result.categories} 个分类、${result.links} 条链接`);
          return true;
        } catch (e) {
          toast("导入失败：" + e.message, true);
          return false;
        }
      },
    });
  }

  function bindGlobal() {
    $("#themeSwitch").addEventListener("click", (e) => {
      const btn = e.target.closest("[data-theme-choice]");
      if (!btn) return;
      setTheme(btn.getAttribute("data-theme-choice"));
    });
    $("#sizeSwitch").addEventListener("click", (e) => {
      const btn = e.target.closest(".size-btn");
      if (!btn) return;
      applyCardSize(btn.getAttribute("data-size"));
    });
    $("#iconShapeSwitch").addEventListener("click", (e) => {
      const btn = e.target.closest("[data-shape]");
      if (!btn) return;
      applyIconShape(btn.getAttribute("data-shape"));
    });
    $("#btnAddCategory").addEventListener("click", () => openAddCategory());
    const sortBtn = $("#btnSortToggle");
    if (sortBtn) {
      sortBtn.addEventListener("click", () => {
        if (sortMode) saveSortOrder();
        else setSortMode(true);
      });
    }
    const loginBtn = $("#btnLogin");
    if (loginBtn) {
      loginBtn.addEventListener("click", () => {
        if (auth.authenticated) logout();
        else openLogin();
      });
    }
    document.addEventListener("pointerdown", beginDrag);
    $("#btnExport").addEventListener("click", () => exportConfig());
    $("#btnImport").addEventListener("click", () => $("#importFile").click());
    $("#importFile").addEventListener("change", (e) => {
      const file = e.target.files && e.target.files[0];
      e.target.value = "";
      openImportConfirm(file);
    });
    $("#modalClose").addEventListener("click", () => closeModal(false));
    $("#modalBackdrop").addEventListener("click", (e) => {
      if (e.target === $("#modalBackdrop")) closeModal(false);
    });

    document.addEventListener("click", (e) => {
      if (sortMode && e.target.closest(".link-card")) {
        // 排序模式下卡片只用于拖动，不跳转
        e.preventDefault();
        e.stopPropagation();
        return;
      }
      const btn = e.target.closest("[data-act]");
      if (btn) {
        handleAction(btn.getAttribute("data-act"), btn.getAttribute("data-id"), e);
        return;
      }
      if (!e.target.closest("#ctxMenu")) hideCtxMenu();
    });

    document.addEventListener("dragstart", (e) => {
      if (sortMode) e.preventDefault();
    });

    document.addEventListener("contextmenu", (e) => {
      if (sortMode) {
        e.preventDefault();
        return;
      }
      if (openCtxAt(e.target, e.clientX, e.clientY)) {
        e.preventDefault();
        e.stopPropagation();
      }
    });

    bindLongPress();

    window.addEventListener("scroll", hideCtxMenu, true);
    window.addEventListener("resize", hideCtxMenu);

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        hideCtxMenu();
        if (sortMode) {
          setSortMode(false);
          return;
        }
        if (!$("#modalBackdrop").classList.contains("hidden")) {
          closeModal(false);
        }
      }
    });
  }

  async function boot() {
    auth.mobile = detectMobile();
    auth.authenticated = !auth.mobile && !!readStoredKey();
    hydrateIcons(document);
    syncSortButton();
    syncAuthUI();
    updateClock();
    setInterval(updateClock, 1000);
    applyTheme();
    applyCardSize(resolveCardSize());
    applyIconShape(resolveIconShape());
    bindGlobal();
    try {
      await reload();
    } catch (e) {
      toast("加载导航数据失败：" + e.message, true);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
