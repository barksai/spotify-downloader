// ==========================================================================
// Spotify & Album MP3 Downloader - Frontend SPA Client (JavaScript)
// ==========================================================================

let currentSearchMode = "album"; // "album" ou "url"
let currentModalAlbum = null;
let eventSource = null;

// État du lecteur audio streaming
let currentPlaylist = [];
let currentTrackIndex = 0;

document.addEventListener("DOMContentLoaded", () => {
    initTabs();
    initSSE();
    loadSystemInfo();
    loadServerLibrary();
    loadSettings();

    // Touche Entrée pour la recherche
    document.getElementById("main-search-input").addEventListener("keydown", (e) => {
        if (e.key === "Enter") handleMainSearch();
    });

    // Enchaînement automatique de la piste suivante dans le lecteur audio
    const audioEl = document.getElementById("audio-element");
    audioEl.addEventListener("ended", () => {
        playNextTrack();
    });
});

// ==========================================================================
// Navigation par Onglets (Desktop & Mobile)
// ==========================================================================

function initTabs() {
    const desktopBtns = document.querySelectorAll(".nav-btn");
    const mobileBtns = document.querySelectorAll(".nav-mobile-btn");

    function switchTab(tabId) {
        document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));
        const target = document.getElementById(tabId);
        if (target) target.classList.add("active");

        desktopBtns.forEach(b => b.classList.toggle("active", b.dataset.tab === tabId));
        mobileBtns.forEach(b => b.classList.toggle("active", b.dataset.tab === tabId));

        if (tabId === "tab-library") loadServerLibrary();
        if (tabId === "tab-settings") loadSettings();
    }

    desktopBtns.forEach(b => b.addEventListener("click", () => switchTab(b.dataset.tab)));
    mobileBtns.forEach(b => b.addEventListener("click", () => switchTab(b.dataset.tab)));

    window.switchTab = switchTab;
}

// ==========================================================================
// Mode de Recherche (Album ou Lien Spotify)
// ==========================================================================

function setSearchMode(mode) {
    currentSearchMode = mode;
    const albumBtn = document.getElementById("mode-album-btn");
    const urlBtn = document.getElementById("mode-url-btn");
    const input = document.getElementById("main-search-input");
    const btnText = document.getElementById("search-btn-text");

    if (mode === "album") {
        albumBtn.classList.add("active");
        urlBtn.classList.remove("active");
        input.placeholder = "Tapez le nom d'un album ou d'un artiste (ex: Daft Punk Discovery, Nirvana Nevermind)...";
        btnText.textContent = "Rechercher l'album";
    } else {
        urlBtn.classList.add("active");
        albumBtn.classList.remove("active");
        input.placeholder = "Collez un lien Spotify : https://open.spotify.com/playlist/... ou album/... ou track/...";
        btnText.textContent = "Charger le lien";
    }
}

// ==========================================================================
// Exécution de la Recherche
// ==========================================================================

async function handleMainSearch() {
    const input = document.getElementById("main-search-input");
    const query = input.value.trim();
    if (!query) return;

    const grid = document.getElementById("results-grid");
    const title = document.getElementById("results-title");
    const btn = document.getElementById("main-search-btn");

    btn.disabled = true;
    grid.innerHTML = '<div style="grid-column: 1 / -1; text-align: center; padding: 40px; color: var(--accent);">⏳ Recherche en cours...</div>';

    try {
        const isUrl = query.startsWith("http://") || query.startsWith("https://") || query.startsWith("spotify:");

        if (isUrl || currentSearchMode === "url") {
            const resp = await fetch("/api/spotify/resolve", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ url: query })
            });
            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || "Erreur lors de l'analyse du lien.");
            }
            const playlist = await resp.json();
            title.textContent = `Résultat du lien : ${playlist.name}`;
            const countEl = document.getElementById("results-count");
            if (countEl) countEl.textContent = `${playlist.tracks ? playlist.tracks.length : playlist.total_tracks} titre(s)`;
            renderCards([playlist]);
        } else {
            const resp = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
            if (!resp.ok) throw new Error("Erreur lors de la recherche d'albums.");
            const albums = await resp.json();
            title.textContent = `Résultats pour "${query}"`;
            const countEl = document.getElementById("results-count");
            if (countEl) countEl.textContent = `${albums.length} album(s) trouvé(s)`;
            renderCards(albums);
        }
    } catch (err) {
        grid.innerHTML = `<div style="grid-column: 1 / -1; text-align: center; padding: 40px; color: #ef5350;">❌ ${err.message}</div>`;
    } finally {
        btn.disabled = false;
    }
}

function renderCards(items) {
    const grid = document.getElementById("results-grid");
    grid.innerHTML = "";

    if (!items || items.length === 0) {
        grid.innerHTML = '<div style="grid-column: 1 / -1; text-align: center; padding: 40px; color: var(--text-muted);">Aucun résultat trouvé.</div>';
        return;
    }

    items.forEach(item => {
        const card = document.createElement("div");
        card.className = "album-card";

        const coverSrc = item.cover_url || "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='76' height='76'%3E%3Crect width='76' height='76' fill='%23333'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' font-size='24' fill='%23666'%3E🎵%3C/text%3E%3C/svg%3E";

        card.innerHTML = `
            <img src="${coverSrc}" class="album-cover" alt="Cover" loading="lazy">
            <div class="album-info">
                <div class="album-title" title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</div>
                <div class="album-artist">${escapeHtml(item.owner)} • ${item.total_tracks} titres</div>
                <div class="album-actions">
                    <button class="btn-secondary btn-explore">🔍 Explorer</button>
                    <button class="btn-primary btn-download" style="padding: 6px 14px; font-size: 0.85rem;">⬇ Télécharger sur le serveur</button>
                </div>
            </div>
        `;

        const btnExplore = card.querySelector(".btn-explore");
        const btnDownload = card.querySelector(".btn-download");

        btnExplore.addEventListener("click", () => exploreItem(item, btnExplore));
        btnDownload.addEventListener("click", () => downloadFullItem(item, btnDownload));

        grid.appendChild(card);
    });
}

// ==========================================================================
// Exploration & Téléchargement complet d'un album
// ==========================================================================

async function exploreItem(item, triggerBtn) {
    if (triggerBtn) {
        triggerBtn.disabled = true;
        triggerBtn.textContent = "⏳ Chargement...";
    }

    let albumData = item;

    if (!albumData.tracks || albumData.tracks.length === 0) {
        try {
            const resp = await fetch(`/api/album/${encodeURIComponent(item.id)}?name=${encodeURIComponent(item.name)}&artist=${encodeURIComponent(item.owner)}&cover_url=${encodeURIComponent(item.cover_url || '')}`);
            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || "Erreur HTTP " + resp.status);
            }
            albumData = await resp.json();
        } catch (e) {
            alert("Impossible de charger les pistes de l'album : " + e.message);
            if (triggerBtn) {
                triggerBtn.disabled = false;
                triggerBtn.textContent = "🔍 Explorer";
            }
            return;
        }
    }

    if (triggerBtn) {
        triggerBtn.disabled = false;
        triggerBtn.textContent = "🔍 Explorer";
    }

    currentModalAlbum = albumData;
    openModal(albumData);
}

async function downloadFullItem(item, triggerBtn) {
    if (triggerBtn) {
        triggerBtn.disabled = true;
        triggerBtn.textContent = "⏳ Ajout en cours...";
    }

    let tracks = item.tracks;

    if (!tracks || tracks.length === 0) {
        try {
            const resp = await fetch(`/api/album/${encodeURIComponent(item.id)}?name=${encodeURIComponent(item.name)}&artist=${encodeURIComponent(item.owner)}&cover_url=${encodeURIComponent(item.cover_url || '')}`);
            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || "Erreur HTTP " + resp.status);
            }
            const data = await resp.json();
            tracks = data.tracks;
        } catch (e) {
            alert("Erreur lors de la récupération des pistes : " + e.message);
            if (triggerBtn) {
                triggerBtn.disabled = false;
                triggerBtn.textContent = "⬇ Télécharger sur le serveur";
            }
            return;
        }
    }

    if (!tracks || tracks.length === 0) {
        alert("Aucun morceau trouvé pour cet album.");
        if (triggerBtn) {
            triggerBtn.disabled = false;
            triggerBtn.textContent = "⬇ Télécharger sur le serveur";
        }
        return;
    }

    try {
        const resp = await fetch("/api/queue/add", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                playlist_name: item.name,
                playlist_owner: item.owner,
                tracks: tracks
            })
        });
        if (resp.ok) {
            window.switchTab("tab-queue");
        } else {
            const err = await resp.json();
            alert("Erreur : " + (err.detail || "Impossible d'ajouter à la file."));
        }
    } catch (e) {
        alert("Erreur d'ajout à la file : " + e.message);
    } finally {
        if (triggerBtn) {
            triggerBtn.disabled = false;
            triggerBtn.textContent = "⬇ Télécharger sur le serveur";
        }
    }
}

// ==========================================================================
// Modale de Sélection de Pistes
// ==========================================================================

function openModal(album) {
    document.getElementById("modal-album-title").textContent = album.name;
    document.getElementById("modal-album-sub").textContent = `${album.owner} • ${album.tracks.length} titres`;

    const tracklist = document.getElementById("modal-tracklist");
    tracklist.innerHTML = "";

    album.tracks.forEach(t => {
        const row = document.createElement("div");
        row.className = "track-select-row";
        row.innerHTML = `
            <input type="checkbox" id="chk-${t.id}" data-id="${t.id}" checked onchange="updateModalCount()">
            <label for="chk-${t.id}" style="flex: 1; font-size: 0.9rem; cursor: pointer;">
                <span style="color: var(--text-muted); font-size: 0.8rem; margin-right: 6px;">${t.track_number_padded}.</span>
                ${escapeHtml(t.artist)} - ${escapeHtml(t.title)}
            </label>
            <span style="color: var(--text-muted); font-size: 0.8rem;">${t.duration_str}</span>
        `;
        tracklist.appendChild(row);
    });

    updateModalCount();
    document.getElementById("album-modal").classList.add("open");
}

function closeModal() {
    document.getElementById("album-modal").classList.remove("open");
}

function toggleAllTracks(checked) {
    document.querySelectorAll(".track-select-row input[type='checkbox']").forEach(cb => cb.checked = checked);
    updateModalCount();
}

function updateModalCount() {
    const total = currentModalAlbum ? currentModalAlbum.tracks.length : 0;
    const selected = document.querySelectorAll(".track-select-row input[type='checkbox']:checked").length;
    document.getElementById("modal-selected-count").textContent = `${selected} / ${total} sélectionnés`;
}

async function confirmAddSelectedTracks() {
    if (!currentModalAlbum) return;

    const checkedIds = new Set(
        Array.from(document.querySelectorAll(".track-select-row input[type='checkbox']:checked")).map(cb => cb.dataset.id)
    );

    const selectedTracks = currentModalAlbum.tracks.filter(t => checkedIds.has(String(t.id)));
    if (selectedTracks.length === 0) {
        alert("Veuillez sélectionner au moins une piste.");
        return;
    }

    try {
        await fetch("/api/queue/add", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                playlist_name: currentModalAlbum.name,
                playlist_owner: currentModalAlbum.owner,
                tracks: selectedTracks
            })
        });
        closeModal();
        window.switchTab("tab-queue");
    } catch (e) {
        alert("Erreur lors de l'ajout : " + e.message);
    }
}

// ==========================================================================
// File de Téléchargement & Temps Réel (SSE)
// ==========================================================================

function initSSE() {
    if (eventSource) eventSource.close();

    eventSource = new EventSource("/api/queue/events");

    eventSource.onmessage = (e) => {
        try {
            const data = JSON.parse(e.data);
            if (data.type === "stats") {
                updateQueueStats(data.stats);
            } else if (data.type === "task_update") {
                updateSingleTask(data.task);
            }
        } catch (err) {
            console.error("SSE parse error:", err);
        }
    };

    fetch("/api/queue")
        .then(r => r.json())
        .then(data => {
            updateQueueStats(data.stats);
            renderQueueTasks(data.tasks);
        })
        .catch(console.error);
}

function updateQueueStats(stats) {
    const total = stats.total || 0;
    const done = (stats.completed || 0) + (stats.skipped || 0);
    const inProg = stats.in_progress || 0;
    const failed = stats.failed || 0;
    const pct = (stats.overall_percent || 0).toFixed(0);

    document.getElementById("queue-overall-pct").textContent = `${pct}%`;
    document.getElementById("global-progress-bar").style.width = `${pct}%`;

    const titleEl = document.getElementById("queue-status-title");
    const subEl = document.getElementById("queue-status-sub");

    if (total === 0) {
        titleEl.textContent = "File d'attente vide";
        subEl.textContent = "Aucun morceau en attente.";
    } else {
        titleEl.textContent = `Progression : ${done} / ${total} morceaux (${pct}%)`;
        subEl.textContent = `${done} terminé(s) • ${inProg} en cours • ${failed} échec(s)`;
    }

    const badgeD = document.getElementById("queue-badge");
    const badgeM = document.getElementById("queue-badge-mobile");
    const activeCount = inProg + (stats.queued || 0);

    if (activeCount > 0) {
        badgeD.textContent = activeCount;
        badgeD.style.display = "inline";
        badgeM.textContent = activeCount;
        badgeM.style.display = "inline";
    } else {
        badgeD.style.display = "none";
        badgeM.style.display = "none";
    }

    const pauseBtn = document.getElementById("queue-pause-btn");
    if (stats.is_paused) {
        pauseBtn.textContent = "▶ Reprendre";
        pauseBtn.style.color = "var(--accent)";
    } else {
        pauseBtn.textContent = "⏸ Pause";
        pauseBtn.style.color = "var(--text-main)";
    }
}

function renderQueueTasks(tasks) {
    const list = document.getElementById("queue-tasks-list");
    list.innerHTML = "";

    if (!tasks || tasks.length === 0) {
        list.innerHTML = '<div style="text-align: center; padding: 30px; color: var(--text-muted);">Aucun morceau dans la file.</div>';
        return;
    }

    tasks.forEach(t => {
        const item = document.createElement("div");
        item.id = `task-row-${t.id}`;
        item.className = "queue-item";
        item.innerHTML = getTaskRowHtml(t);
        list.appendChild(item);
    });
}

function updateSingleTask(t) {
    let row = document.getElementById(`task-row-${t.id}`);
    const list = document.getElementById("queue-tasks-list");

    if (!row) {
        if (list.children.length === 1 && list.children[0].textContent.includes("Aucun morceau")) {
            list.innerHTML = "";
        }
        row = document.createElement("div");
        row.id = `task-row-${t.id}`;
        row.className = "queue-item";
        list.appendChild(row);
    }
    row.innerHTML = getTaskRowHtml(t);
}

function getTaskRowHtml(t) {
    let statusColor = "var(--accent)";
    if (t.status === "Échec") statusColor = "var(--danger)";
    else if (t.status === "En attente") statusColor = "var(--text-muted)";
    else if (t.status === "Téléchargement...") statusColor = "var(--info)";

    return `
        <div class="queue-item-top">
            <span class="queue-item-title">${escapeHtml(t.artist)} - ${escapeHtml(t.title)}</span>
            <span style="font-size: 0.8rem; font-weight: 700; color: ${statusColor};">${t.progress.toFixed(0)}%</span>
        </div>
        <div class="queue-item-status" style="color: ${statusColor};">
            ${escapeHtml(t.status_message || t.status)}
        </div>
        <div class="progress-bar-wrapper" style="height: 6px; margin: 4px 0 0 0;">
            <div class="progress-bar-fill" style="width: ${t.progress}%; background-color: ${statusColor};"></div>
        </div>
    `;
}

async function controlQueue(action) {
    await fetch("/api/queue/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: action })
    });
    fetch("/api/queue").then(r => r.json()).then(d => {
        updateQueueStats(d.stats);
        renderQueueTasks(d.tasks);
    });
}

// ==========================================================================
// Lecteur Audio Streaming & Bibliothèque Serveur
// ==========================================================================

async function loadServerLibrary() {
    const container = document.getElementById("library-container");
    container.innerHTML = '<div style="text-align: center; padding: 40px; color: var(--text-muted);">Chargement de la bibliothèque...</div>';

    try {
        const resp = await fetch("/api/library");
        const data = await resp.json();

        const dirEl = document.getElementById("library-current-dir");
        if (dirEl && data.download_dir) {
            dirEl.textContent = `Emplacement sur le serveur : ${data.download_dir}`;
        }

        if (!data.albums || data.albums.length === 0) {
            container.innerHTML = '<div style="text-align: center; padding: 40px; color: var(--text-muted);">Aucun fichier MP3 trouvé dans le dossier du serveur.</div>';
            return;
        }

        container.innerHTML = "";
        data.albums.forEach(alb => {
            const card = document.createElement("div");
            card.className = "library-album-card";

            let tracksHtml = "";
            alb.tracks.forEach((tr, trIdx) => {
                tracksHtml += `
                    <div class="library-track-row">
                        <span style="font-size: 0.9rem; flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding-right: 10px;">
                            🎵 ${escapeHtml(tr.title || tr.filename)} <span style="font-size: 0.75rem; color: var(--text-muted);">(${tr.size_mb} Mo)</span>
                        </span>
                        <div>
                            <button class="btn-primary btn-play-single" data-index="${trIdx}" style="padding: 5px 12px; font-size: 0.8rem;">▶ Écouter</button>
                        </div>
                    </div>
                `;
            });

            card.innerHTML = `
                <div class="library-album-header">
                    <div>
                        <div style="font-weight: 700; font-size: 1.05rem;">📁 ${escapeHtml(alb.folder_name)}</div>
                        <div style="font-size: 0.8rem; color: var(--text-muted);">${alb.track_count} morceau(x) sur le serveur</div>
                    </div>
                    <div>
                        <button class="btn-secondary btn-play-all" style="padding: 6px 14px; font-size: 0.85rem;">
                            ▶ Écouter tout l'album
                        </button>
                    </div>
                </div>
                <div>${tracksHtml}</div>
            `;

            const playAllBtn = card.querySelector(".btn-play-all");
            if (playAllBtn) {
                playAllBtn.addEventListener("click", () => playTrackFromAlbum(alb.tracks, 0, alb.folder_name));
            }

            card.querySelectorAll(".btn-play-single").forEach(btn => {
                const idx = parseInt(btn.dataset.index) || 0;
                btn.addEventListener("click", () => playTrackFromAlbum(alb.tracks, idx, alb.folder_name));
            });

            container.appendChild(card);
        });
    } catch (e) {
        container.innerHTML = `<div style="text-align: center; padding: 40px; color: #ef5350;">Erreur de chargement: ${e.message}</div>`;
    }
}

function playTrackFromAlbum(tracks, index, albumName) {
    currentPlaylist = tracks;
    currentTrackIndex = index;
    loadAndPlayCurrentTrack(albumName);
}

function loadAndPlayCurrentTrack(albumName) {
    if (!currentPlaylist || currentPlaylist.length === 0) return;
    if (currentTrackIndex < 0) currentTrackIndex = 0;
    if (currentTrackIndex >= currentPlaylist.length) currentTrackIndex = currentPlaylist.length - 1;

    const track = currentPlaylist[currentTrackIndex];
    const playerBar = document.getElementById("player-bar");
    const audioEl = document.getElementById("audio-element");
    const titleEl = document.getElementById("player-title");
    const subEl = document.getElementById("player-sub");

    titleEl.textContent = track.title || track.filename;
    subEl.textContent = `${albumName || "Album"} (${currentTrackIndex + 1} / ${currentPlaylist.length})`;

    audioEl.src = `/api/stream?path=${encodeURIComponent(track.rel_path)}`;
    playerBar.style.display = "flex";
    audioEl.play().catch(console.error);
}

function playNextTrack() {
    if (currentPlaylist && currentTrackIndex < currentPlaylist.length - 1) {
        currentTrackIndex++;
        loadAndPlayCurrentTrack();
    }
}

function playPrevTrack() {
    if (currentPlaylist && currentTrackIndex > 0) {
        currentTrackIndex--;
        loadAndPlayCurrentTrack();
    }
}

function closePlayer() {
    const playerBar = document.getElementById("player-bar");
    const audioEl = document.getElementById("audio-element");
    audioEl.pause();
    playerBar.style.display = "none";
}

// ==========================================================================
// Paramètres & Emplacement Serveur
// ==========================================================================

async function loadSystemInfo() {
    try {
        const resp = await fetch("/api/system/info");
        const data = await resp.json();
        const container = document.getElementById("server-ips-container");
        container.innerHTML = "";

        data.access_urls.forEach(url => {
            const link = document.createElement("div");
            link.style.cssText = "background: #1e1e1e; padding: 10px 14px; border-radius: 8px; border: 1px solid #333; font-family: monospace; font-size: 0.95rem; color: var(--accent); display: flex; justify-content: space-between; align-items: center;";
            link.innerHTML = `
                <span>${url}</span>
                <button class="btn-secondary" style="padding: 4px 8px; font-size: 0.75rem;" onclick="navigator.clipboard.writeText('${url}'); alert('Adresse copiée !')">Copier</button>
            `;
            container.appendChild(link);
        });
    } catch (e) {
        console.error("System info error:", e);
    }
}

async function loadSettings() {
    try {
        const resp = await fetch("/api/settings");
        const s = await resp.json();

        document.getElementById("setting-download-dir").value = s.download_dir || "";
        document.getElementById("setting-template").value = s.filename_template || "";
        document.getElementById("setting-audio-quality").value = s.audio_quality || "320k";
        document.getElementById("setting-threads").value = s.max_threads || 3;

        // Préselection du menu déroulant si correspond
        const presetSelect = document.getElementById("setting-template-preset");
        let matched = false;
        for (let opt of presetSelect.options) {
            if (opt.value === s.filename_template) {
                presetSelect.value = opt.value;
                matched = true;
                break;
            }
        }
        if (!matched) presetSelect.value = "custom";

        updateTemplatePreview(s.full_preview);
    } catch (e) {
        console.error("Settings load error:", e);
    }
}

function onPresetSelected(value) {
    if (value !== "custom") {
        document.getElementById("setting-template").value = value;
    }
    updateTemplatePreview();
}

function updateTemplatePreview(staticPreview) {
    if (staticPreview) {
        document.getElementById("setting-template-preview").textContent = staticPreview;
        return;
    }

    const dir = document.getElementById("setting-download-dir").value.trim() || "C:\\Musique";
    let tmpl = document.getElementById("setting-template").value.trim() || "{Artist}/{Album}/{TrackNumber} - {Title}.mp3";

    // Remplacement d'exemple dynamique
    let rendered = tmpl
        .replace(/{Artist}/g, "Daft Punk")
        .replace(/{Album}/g, "Discovery")
        .replace(/{TrackNumber}/g, "01")
        .replace(/{Title}/g, "One More Time")
        .replace(/{Year}/g, "2001")
        .replace(/{Playlist}/g, "Best of Daft Punk");

    const sep = dir.includes("/") ? "/" : "\\";
    const full = dir.endsWith(sep) ? dir + rendered : dir + sep + rendered;
    document.getElementById("setting-template-preview").textContent = full;
}

// Mise à jour de l'aperçu si le dossier de téléchargement change
document.getElementById("setting-download-dir")?.addEventListener("input", () => updateTemplatePreview());

async function saveSettings() {
    const downloadDir = document.getElementById("setting-download-dir").value.trim();
    const template = document.getElementById("setting-template").value.trim();

    if (!downloadDir) {
        alert("Veuillez renseigner un dossier local pour le serveur.");
        return;
    }

    const payload = {
        download_dir: downloadDir,
        filename_template: template || "{Artist}/{Album}/{TrackNumber} - {Title}.mp3",
        audio_quality: document.getElementById("setting-audio-quality").value,
        max_threads: parseInt(document.getElementById("setting-threads").value) || 3
    };

    try {
        const resp = await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const res = await resp.json();
        if (resp.ok) {
            alert("Paramètres enregistrés avec succès sur le serveur !");
            updateTemplatePreview(res.full_preview);
            loadServerLibrary();
        } else {
            alert("Erreur : " + (res.detail || "Impossible d'enregistrer les paramètres."));
        }
    } catch (e) {
        alert("Erreur lors de l'enregistrement: " + e.message);
    }
}

function escapeHtml(text) {
    if (!text) return "";
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}
