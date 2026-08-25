/* lan-nav 前端逻辑 */
(function () {
  "use strict";

  const TOKEN_KEY = "lan-nav-admin-token";
  const THEME_KEY = "lan-nav-theme";
  const COLLAPSE_KEY = "lan-nav-collapsed";
  const SIZE_KEY = "lan-nav-card-size";
  const SIZE_OPTIONS = ["sm", "md", "lg"];

  const state = {
    site: { title: "", subtitle: "", theme: "system" },
    categories: [],
    links: [],
    meta: { admin_protected: false, uncategorized_id: "" },
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

  function getToken() {
    return sessionStorage.getItem(TOKEN_KEY) || "";
  }

  function setToken(token) {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
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
    return `<span class="fav" style="background:${color || initialColor(title)}" aria-hidden="true">${escapeHtml(ch)}</span>`;
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderFav(link) {
    const color = link.color || initialColor(link.title);
    if (link.icon && window.LucideIcons.has(link.icon)) {
      return `<span class="fav lucide" style="background:${color}">${window.LucideIcons.svg(link.icon)}</span>`;
    }
    if (link.icon_url) {
      return `<span class="fav" style="background:${color}"><img src="${escapeHtml(link.icon_url)}" alt="" loading="lazy" referrerpolicy="no-referrer" data-fallback-title="${escapeHtml(link.title)}" data-fallback-color="${escapeHtml(color)}" /></span>`;
    }
    const ico = faviconCandidate(link.url);
    if (ico) {
      return `<span class="fav" style="background:${color}"><img src="${escapeHtml(ico)}" alt="" loading="lazy" referrerpolicy="no-referrer" data-fallback-title="${escapeHtml(link.title)}" data-fallback-color="${escapeHtml(color)}" /></span>`;
    }
    return letterAvatar(link.title, color);
  }

  async function api(path, options) {
    const opts = options || {};
    const headers = Object.assign({ Accept: "application/json" }, opts.headers || {});
    if (opts.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
    if (opts.auth) {
      const token = getToken();
      if (token) headers["X-Admin-Token"] = token;
    }
    const res = await fetch(path, {
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

  function applyTheme() {
    const theme = resolveTheme();
    document.documentElement.setAttribute("data-theme", theme);
    const btn = $("#themeToggle");
    if (btn) {
      btn.innerHTML = window.LucideIcons.svg(theme === "dark" ? "sun" : "moon");
      btn.setAttribute("aria-label", theme === "dark" ? "切换到浅色" : "切换到深色");
    }
  }

  function cycleTheme() {
    const cur = resolveTheme();
    localStorage.setItem(THEME_KEY, cur === "dark" ? "light" : "dark");
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
    $$("#sizeSwitch .size-btn").forEach((btn) => {
      const on = btn.getAttribute("data-size") === s;
      btn.setAttribute("aria-pressed", on ? "true" : "false");
      btn.classList.toggle("is-active", on);
    });
  }

  function updateSecurityBanner() {
    const banner = $("#securityBanner");
    const protected_ = state.meta.admin_protected;
    if (!protected_) {
      banner.classList.remove("hidden");
      banner.innerHTML =
        '<span data-icon="alert"></span><span>编辑保护未启用，仅建议在可信局域网使用。若暴露公网，请配置 ADMIN_TOKEN，并配合 VPN / Nginx Basic Auth 等访问控制。</span>';
      hydrateIcons(banner);
    } else {
      banner.classList.add("hidden");
      banner.innerHTML = "";
    }
    $("#footerHint").textContent = protected_
      ? "写入接口已启用 Token 保护"
      : "写入接口未启用 Token";
  }

  async function verifyToken() {
    await api("/api/auth/verify", { auth: true });
  }

  async function ensureAuth() {
    if (!state.meta.admin_protected) return true;
    if (getToken()) {
      try {
        await verifyToken();
        return true;
      } catch (e) {
        if (e.status === 401 || e.code === "UNAUTHORIZED") setToken("");
        else {
          toast(e.message, true);
          return false;
        }
      }
    }
    return promptToken();
  }

  async function withAuth(fn) {
    const ok = await ensureAuth();
    if (!ok) return;
    return fn();
  }

  function promptToken() {
    return new Promise((resolve) => {
      openModal({
        title: "输入管理 Token",
        body: `
          <div class="field">
            <label for="tokenInput">ADMIN_TOKEN</label>
            <input id="tokenInput" type="password" autocomplete="current-password" placeholder="关闭浏览器后失效" />
            <p class="hint">Token 仅保存在本机 sessionStorage，不会写入服务端日志。</p>
          </div>`,
        confirmText: "确认",
        onConfirm: async () => {
          const val = ($("#tokenInput").value || "").trim();
          if (!val) {
            toast("请输入 Token", true);
            return false;
          }
          setToken(val);
          try {
            await verifyToken();
            resolve(true);
            return true;
          } catch (e) {
            setToken("");
            toast(e.status === 401 ? "Token 无效" : e.message, true);
            return false;
          }
        },
        onCancel: () => resolve(false),
      });
      setTimeout(() => $("#tokenInput")?.focus(), 50);
    });
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
          const ok = await b.onClick();
          if (ok !== false) closeModal(true);
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
        if (!opts.onConfirm) {
          closeModal(true);
          return;
        }
        const result = await opts.onConfirm();
        if (result !== false) closeModal(true);
      });
      foot.appendChild(ok);
    }
    backdrop.hidden = false;
    backdrop.classList.remove("hidden");
    hydrateIcons(backdrop);
  }

  function closeModal(confirmed) {
    const backdrop = $("#modalBackdrop");
    backdrop.classList.add("hidden");
    backdrop.hidden = true;
    if (!confirmed && modalOpts && modalOpts.onCancel) modalOpts.onCancel();
    modalOpts = null;
  }

  function categoryForm(cat) {
    const c = cat || { name: "", description: "", icon: "folder", color: "#8b5cf6" };
    return `
      <div class="field">
        <label for="fName">名称</label>
        <input id="fName" value="${escapeHtml(c.name)}" required maxlength="60" />
      </div>
      <div class="field">
        <label for="fDesc">描述</label>
        <input id="fDesc" value="${escapeHtml(c.description || "")}" maxlength="200" />
      </div>
      <div class="field-row">
        <div class="field">
          <label for="fIcon">Lucide 图标名</label>
          <input id="fIcon" value="${escapeHtml(c.icon || "folder")}" placeholder="folder" list="iconList" />
        </div>
        <div class="field">
          <label for="fColor">颜色</label>
          <input id="fColor" type="color" value="${escapeHtml((c.color || "#8b5cf6").slice(0, 7))}" />
        </div>
      </div>
      <datalist id="iconList">${window.LucideIcons.names.map((n) => `<option value="${n}"></option>`).join("")}</datalist>
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
      <div class="field-row">
        <div class="field">
          <label for="lIconUrl">图标 URL（可选）</label>
          <input id="lIconUrl" value="${escapeHtml(l.icon_url || "")}" />
        </div>
        <div class="field">
          <label for="lIcon">Lucide 图标名</label>
          <input id="lIcon" value="${escapeHtml(l.icon || "")}" list="iconList" />
        </div>
      </div>
      <div class="field">
        <label for="lColor">主题色</label>
        <input id="lColor" type="color" value="${escapeHtml((l.color || "#6366f1").slice(0, 7))}" />
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
      icon: $("#fIcon").value.trim() || "folder",
      color: $("#fColor").value,
    };
  }

  function readLinkForm() {
    return {
      title: $("#lTitle").value.trim(),
      url: $("#lUrl").value.trim(),
      description: $("#lDesc").value.trim(),
      category_id: $("#lCat").value,
      tags: $("#lTags").value,
      icon_url: $("#lIconUrl").value.trim(),
      icon: $("#lIcon").value.trim(),
      color: $("#lColor").value,
      status: $("#lStatus").value,
      pinned: $("#lPinned").checked,
    };
  }

  function renderLinkCard(link) {
    return `<a class="link-card" href="${escapeHtml(link.url)}" target="_blank" rel="noopener noreferrer" data-link-id="${escapeHtml(link.id)}" style="--card-accent:${escapeHtml(link.color || "#6366f1")}">
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
    $("#siteSubtitle").textContent = state.site.subtitle || "";

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
      pinnedGrid.innerHTML = pinned.map(renderLinkCard).join("");
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
          .sort((a, b) => Number(!a.pinned) - Number(!b.pinned) || a.order - b.order);
        const isCollapsed = !!collapsed[c.id];
        return `<section class="category ${isCollapsed ? "collapsed" : ""}" id="cat-${escapeHtml(c.id)}" data-cat-id="${escapeHtml(c.id)}">
          <div class="category-panel" data-cat-panel="${escapeHtml(c.id)}">
            <div class="category-head">
              <span class="cat-icon" style="background:${escapeHtml(c.color || "#64748b")}">${window.LucideIcons.svg(c.icon || "folder")}</span>
              <div class="cat-meta">
                <h2>${escapeHtml(c.name)}</h2>
                <p>${escapeHtml(c.description || "")} · ${links.length} 个链接</p>
              </div>
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
    if (addWrap) addWrap.classList.toggle("hidden", !!state.query);

    hydrateIcons(document);
    bindFavfallbacks();
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
    updateSecurityBanner();
    applyTheme();
    render();
  }

  function findLink(id) {
    return state.links.find((l) => l.id === id);
  }

  function findCat(id) {
    return state.categories.find((c) => c.id === id);
  }

  function openAddCategory() {
    return withAuth(() => {
      openModal({
        title: "新增分类",
        body: categoryForm(),
        confirmText: "创建",
        onConfirm: async () => {
          try {
            await api("/api/categories", { method: "POST", body: readCategoryForm(), auth: true });
            await reload();
            toast("分类已创建");
            return true;
          } catch (e) {
            toast(e.message, true);
            return false;
          }
        },
      });
    });
  }

  function openAddLink(categoryId) {
    return withAuth(() => {
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
            await api("/api/links", { method: "POST", body: readLinkForm(), auth: true });
            await reload();
            toast("链接已创建");
            return true;
          } catch (e) {
            toast(e.message, true);
            return false;
          }
        },
      });
    });
  }

  function openEditLink(id) {
    const link = findLink(id);
    if (!link) return;
    return withAuth(() => {
      openModal({
        title: "编辑链接",
        body: linkForm(link),
        confirmText: "保存",
        onConfirm: async () => {
          try {
            await api(`/api/links/${id}`, { method: "PUT", body: readLinkForm(), auth: true });
            await reload();
            toast("已保存");
            return true;
          } catch (e) {
            toast(e.message, true);
            return false;
          }
        },
      });
    });
  }

  function openDeleteLink(id) {
    const link = findLink(id);
    return withAuth(() => {
      openModal({
        title: "删除链接",
        body: `<p>确定删除「${escapeHtml(link ? link.title : id)}」？此操作不可撤销。</p>`,
        confirmText: "删除",
        onConfirm: async () => {
          try {
            await api(`/api/links/${id}`, { method: "DELETE", auth: true });
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
    });
  }

  function openEditCategory(id) {
    const cat = findCat(id);
    if (!cat) return;
    return withAuth(() => {
      openModal({
        title: "编辑分类",
        body: categoryForm(cat),
        confirmText: "保存",
        onConfirm: async () => {
          try {
            await api(`/api/categories/${id}`, {
              method: "PUT",
              body: readCategoryForm(),
              auth: true,
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
    });
  }

  function openDeleteCategory(id) {
    if (id === state.meta.uncategorized_id) {
      toast("不能删除「未分类」", true);
      return;
    }
    const cat = findCat(id);
    return withAuth(() => {
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
                  auth: true,
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
                  auth: true,
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
    return [
      { id: "open", label: "打开链接", run: () => openLink(id) },
      { id: "copy", label: "复制链接", run: () => copyLink(id) },
      { sep: true },
      { id: "edit", label: "编辑链接", run: () => openEditLink(id) },
      { id: "del", label: "删除链接", danger: true, run: () => openDeleteLink(id) },
    ];
  }

  function catMenuItems(catId) {
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
      return {
        kind: "cat",
        el: panel,
        items: catMenuItems(panel.getAttribute("data-cat-panel")),
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

  function bindGlobal() {
    $("#themeToggle").addEventListener("click", cycleTheme);
    $("#sizeSwitch").addEventListener("click", (e) => {
      const btn = e.target.closest(".size-btn");
      if (!btn) return;
      applyCardSize(btn.getAttribute("data-size"));
    });
    $("#btnAddCategory").addEventListener("click", () => openAddCategory());
    $("#searchInput").addEventListener("input", (e) => {
      state.query = e.target.value;
      render();
    });
    $("#modalClose").addEventListener("click", () => closeModal(false));
    $("#modalBackdrop").addEventListener("click", (e) => {
      if (e.target === $("#modalBackdrop")) closeModal(false);
    });

    document.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-act]");
      if (btn) {
        handleAction(btn.getAttribute("data-act"), btn.getAttribute("data-id"), e);
        return;
      }
      if (!e.target.closest("#ctxMenu")) hideCtxMenu();
    });

    document.addEventListener("contextmenu", (e) => {
      if (openCtxAt(e.target, e.clientX, e.clientY)) {
        e.preventDefault();
        e.stopPropagation();
      }
    });

    bindLongPress();

    window.addEventListener("scroll", hideCtxMenu, true);
    window.addEventListener("resize", hideCtxMenu);

    document.addEventListener("keydown", (e) => {
      const tag = (e.target && e.target.tagName) || "";
      const typing = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || e.target.isContentEditable;
      if (e.key === "/" && !typing) {
        e.preventDefault();
        $("#searchInput").focus();
        $("#searchInput").select();
      }
      if (e.key === "Escape") {
        hideCtxMenu();
        if (!$("#modalBackdrop").classList.contains("hidden")) {
          closeModal(false);
          return;
        }
        if (state.query) {
          state.query = "";
          $("#searchInput").value = "";
          render();
        }
        $("#searchInput").blur();
      }
    });
  }

  async function boot() {
    hydrateIcons(document);
    state.meta.admin_protected = !!(window.__LAN_NAV__ && window.__LAN_NAV__.adminProtected);
    updateClock();
    setInterval(updateClock, 1000);
    applyTheme();
    applyCardSize(resolveCardSize());
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
