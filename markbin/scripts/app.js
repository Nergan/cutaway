document.addEventListener('DOMContentLoaded', () => {
    const { baseUrl, uuid } = window.MARKBIN_CONFIG;
    const isViewMode = Boolean(uuid);
    
    const btnAction = document.getElementById('btn-action');
    const btnToc = document.getElementById('btn-toc');
    const btnDownload = document.getElementById('btn-download');
    const btnUpload = document.getElementById('btn-upload');
    const ttlInput = document.getElementById('ttl-input');
    const docTimer = document.getElementById('doc-timer');
    
    const sidebar = document.getElementById('toc-sidebar');
    const editorWrapper = document.getElementById('editor-wrapper');
    const viewer = document.getElementById('viewer');
    const toast = document.getElementById('toast');
    const fileInput = document.getElementById('file-input');
    const tocContent = document.getElementById('toc-content');
    
    let vditorInstance = null;
    let rawMarkdown = "";
    
    const DRAFT_KEY = 'markbin_draft';
    
    function showToast(message) {
        toast.textContent = message;
        toast.classList.add('show');
        setTimeout(() => toast.classList.remove('show'), 3000);
    }

    // --- PANEL TOGGLES ---
    btnToc.addEventListener('click', () => sidebar.classList.toggle('hidden'));

    const bottomContainer = document.getElementById('bottom-container');
    const btnToggleBar = document.getElementById('toggle-bar-btn');
    const editorContainer = document.getElementById('editor-container');
    
    const isDesktopInit = window.matchMedia('(min-width: 769px)').matches;
    const iconInit = btnToggleBar.querySelector('i');
    if (isDesktopInit) {
        iconInit.classList.remove('bi-chevron-down');
        iconInit.classList.add('bi-chevron-up');
    } else {
        iconInit.classList.remove('bi-chevron-up');
        iconInit.classList.add('bi-chevron-down');
    }
    
    btnToggleBar.addEventListener('click', () => {
        bottomContainer.classList.toggle('collapsed');
        editorContainer.classList.toggle('expanded-view');
        const icon = btnToggleBar.querySelector('i');
        const isDesktop = window.matchMedia('(min-width: 769px)').matches;
        
        if (isDesktop) {
            icon.classList.replace(bottomContainer.classList.contains('collapsed') ? 'bi-chevron-up' : 'bi-chevron-down', 
                                   bottomContainer.classList.contains('collapsed') ? 'bi-chevron-down' : 'bi-chevron-up');
        } else {
            icon.classList.replace(bottomContainer.classList.contains('collapsed') ? 'bi-chevron-down' : 'bi-chevron-up', 
                                   bottomContainer.classList.contains('collapsed') ? 'bi-chevron-up' : 'bi-chevron-down');
        }
    });

    // --- DOWNLOAD MECHANISM (Ctrl+S / Cmd+S Rebind) ---
    function downloadMarkdown() {
        if (!rawMarkdown) return showToast("Nothing to download!");
        const blob = new Blob([rawMarkdown], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = isViewMode ? `markbin-${uuid}.md` : 'draft.md';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    btnDownload.addEventListener('click', downloadMarkdown);

    window.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'S' || e.code === 'KeyS')) {
            e.preventDefault();
            e.stopPropagation();
            btnDownload.click();
        }
    }, { capture: true });

    // --- TEXT & ID CLEANERS ---
    function getCleanText(rawText) {
        if (!rawText) return '';
        let text = rawText.replace(/[*_~`]/g, '');
        text = text.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
        let tmp = document.createElement('div');
        tmp.innerHTML = text;
        return (tmp.textContent || tmp.innerText || '').trim();
    }

    function generateId(text) {
        let id = text.toLowerCase().trim()
            .replace(/[\s]+/g, '-')
            .replace(/[^\p{L}\p{N}\-_]/gu, '') 
            .replace(/^-+|-+$/g, '');
        return id || 'heading'; 
    }

    // --- NESTED TOC RENDER ENGINE ---
    function buildTree(headings) {
        const root = { depth: 0, children: [] };
        const stack = [root];
        
        headings.forEach(h => {
            const node = { ...h, children: [] };
            while (stack.length > 1 && stack[stack.length - 1].depth >= node.depth) {
                stack.pop();
            }
            stack[stack.length - 1].children.push(node);
            stack.push(node);
        });
        return root.children;
    }

    function renderTOCNode(node, container) {
        const li = document.createElement('li');
        const wrapper = document.createElement('div');
        wrapper.className = 'toc-item-wrapper';
        
        let childUl;
        if (node.children.length > 0) {
            const toggle = document.createElement('i');
            toggle.className = 'bi bi-chevron-right toc-toggle';
            toggle.addEventListener('click', (e) => {
                e.stopPropagation();
                toggle.classList.toggle('expanded');
                childUl.classList.toggle('hidden');
            });
            wrapper.appendChild(toggle);
        } else {
            const spacer = document.createElement('span');
            spacer.className = 'toc-spacer';
            wrapper.appendChild(spacer);
        }
        
        const link = document.createElement('a');
        link.href = '#';
        link.className = 'toc-item';
        link.textContent = node.text;
        link.addEventListener('click', (e) => {
            e.preventDefault();
            if (node.element) node.element.scrollIntoView({ behavior: 'smooth', block: 'start' });
            else if (node.scrollTarget) node.scrollTarget();
        });
        wrapper.appendChild(link);
        li.appendChild(wrapper);
        
        if (node.children.length > 0) {
            childUl = document.createElement('ul');
            childUl.className = 'toc-children hidden'; 
            node.children.forEach(child => renderTOCNode(child, childUl));
            li.appendChild(childUl);
        }
        container.appendChild(li);
    }

    function generateTOC(headingsRaw) {
        tocContent.innerHTML = "";
        if (headingsRaw.length === 0) {
            tocContent.innerHTML = "<span style='color: #666; font-size: 0.9rem'>No headings found.</span>";
            return;
        }
        const tree = buildTree(headingsRaw);
        const rootUl = document.createElement('ul');
        rootUl.className = 'toc-root';
        tree.forEach(node => renderTOCNode(node, rootUl));
        tocContent.appendChild(rootUl);
    }

    function buildTOCFromDOM(container) {
        const headingsNodes = container.querySelectorAll('h1, h2, h3, h4, h5, h6');
        const headings = Array.from(headingsNodes).map(h => {
            const text = getCleanText(h.textContent);
            if (!h.id) h.id = generateId(text);
            return { depth: parseInt(h.tagName.substring(1)), text: text, element: h };
        });
        generateTOC(headings);
    }

    function updateTOCEditMode(md) {
        const noCode = md.replace(/```[\s\S]*?```/g, '');
        const headingRegex = /^(#{1,6})\s+(.+)$/gm;
        let match;
        const headings = [];
        const idCounts = {};
        
        while ((match = headingRegex.exec(noCode)) !== null) {
            let cleanText = getCleanText(match[2].trim());
            let baseId = generateId(cleanText);
            let id = baseId;
            if (idCounts[baseId]) {
                id = `${baseId}-${idCounts[baseId]}`;
                idCounts[baseId]++;
            } else {
                idCounts[baseId] = 1;
            }

            headings.push({
                depth: match[1].length,
                text: cleanText,
                scrollTarget: () => {
                    const editorHeadings = document.querySelectorAll('.vditor-ir h1, .vditor-ir h2, .vditor-ir h3, .vditor-ir h4, .vditor-ir h5, .vditor-ir h6, .vditor-ir[data-type="NodeHeading"]');
                    let targetOccurrence = id.includes('-') ? parseInt(id.split('-').pop()) || 0 : 0;
                    let matchIndex = 0;
                    for (let el of editorHeadings) {
                        if (generateId(getCleanText(el.textContent)) === baseId) {
                            if (matchIndex === targetOccurrence) {
                                el.scrollIntoView({ behavior: 'smooth', block: 'start' });
                                break;
                            }
                            matchIndex++;
                        }
                    }
                }
            });
        }
        generateTOC(headings);
    }

    // --- TTL MASK AND TIMER LOGIC ---
    
    // Custom Vanilla JS Strict Mask (HH:MM:SS)
    ttlInput.addEventListener('input', function() {
        // Strip everything but numbers, limit to 6 digits maximum
        let val = this.value.replace(/\D/g, '').substring(0, 6);
        let result = '';
        
        for (let i = 0; i < val.length; i++) {
            // Cap the tens place of Minutes (index 2) and Seconds (index 4) at 5
            // So a user cannot enter 60+ minutes or seconds.
            if ((i === 2 || i === 4) && parseInt(val[i]) > 5) {
                result += '5';
            } else {
                result += val[i];
            }
            
            // Auto-inject colons after hours and minutes
            if ((i === 1 || i === 3) && i !== val.length - 1) {
                result += ':';
            }
        }
        this.value = result;
    });

    function getTtlSeconds() {
        if (!ttlInput.value.trim()) return null;
        
        // Because of the strict mask, we can safely split and evaluate from left to right.
        const parts = ttlInput.value.trim().split(':').map(Number);
        const h = parts[0] || 0;
        const m = parts[1] || 0;
        const s = parts[2] || 0;
        
        const total = (h * 3600) + (m * 60) + s;
        return total > 0 ? total : null;
    }

    function startTimer(expiresAtIso) {
        docTimer.classList.remove('hidden');
        const expiresAt = new Date(expiresAtIso).getTime();
        
        const updateTimer = () => {
            const now = new Date().getTime();
            const diff = expiresAt - now;
            if (diff <= 0) {
                window.location.reload(); // Self-destruct triggers DB 404 page
                return;
            }
            const s = Math.floor(diff / 1000);
            const hrs = String(Math.floor(s / 3600)).padStart(2, '0');
            const mins = String(Math.floor((s % 3600) / 60)).padStart(2, '0');
            const secs = String(s % 60).padStart(2, '0');
            docTimer.innerHTML = `<i class="bi bi-stopwatch"></i> ${hrs}:${mins}:${secs}`;
        };
        updateTimer();
        setInterval(updateTimer, 1000);
    }

    // --- MODES ---
    if (isViewMode) {
        btnUpload.style.display = 'none';
        ttlInput.style.display = 'none';
        
        btnAction.innerHTML = '<i class="bi bi-clipboard"></i>';
        btnAction.title = "Copy raw Markdown";
        btnAction.classList.remove('disabled');
        
        editorWrapper.classList.add('hidden');
        document.getElementById('loading').classList.remove('hidden');

        fetch(`${baseUrl}/api/docs/${uuid}`, { cache: 'no-store' })
            .then(res => {
                if (!res.ok) throw new Error("Not Found");
                return res.json();
            })
            .then(data => {
                rawMarkdown = data.content;
                if (data.expires_at) startTimer(data.expires_at);

                Vditor.preview(viewer, rawMarkdown, {
                    mode: 'dark',
                    theme: { current: 'dark' },
                    hljs: { style: 'atom-one-dark' },
                    after: () => {
                        document.getElementById('loading').classList.add('hidden');
                        viewer.classList.remove('hidden');
                        buildTOCFromDOM(viewer);
                    }
                });
            })
            .catch(() => {
                document.getElementById('loading').classList.add('hidden');
                document.getElementById('error-msg').classList.remove('hidden');
            });

        btnAction.addEventListener('click', () => {
            navigator.clipboard.writeText(rawMarkdown).then(() => showToast("Copied to clipboard!"));
        });

    } else {
        btnAction.innerHTML = '<i class="bi bi-cloud-arrow-up"></i>';
        btnAction.title = "Publish document";

        const savedDraft = localStorage.getItem(DRAFT_KEY) || "";
        rawMarkdown = savedDraft;

        vditorInstance = new Vditor('editor', {
            value: savedDraft,
            mode: 'ir',
            theme: 'dark',
            icon: 'material',
            toolbarConfig: { hide: true },
            cache: { enable: false },
            placeholder: "Type Markdown or drag & drop a file…",
            preview: {
                theme: { current: 'dark' },
                hljs: { style: 'atom-one-dark' } 
            },
            after: () => {
                vditorInstance.focus();
                updateSaveButtonState();
                updateTOCEditMode(rawMarkdown); 
            },
            input: (val) => {
                rawMarkdown = val;
                localStorage.setItem(DRAFT_KEY, val);
                updateSaveButtonState();
                updateTOCEditMode(val); 
            }
        });

        function updateSaveButtonState() {
            if (rawMarkdown.trim() === "") {
                btnAction.classList.add('disabled');
                btnAction.classList.remove('unsaved');
            } else {
                btnAction.classList.remove('disabled');
                btnAction.classList.add('unsaved'); 
            }
        }

        fileInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) handleFile(file);
        });

        window.addEventListener('dragover', (e) => { e.preventDefault(); e.stopPropagation(); }, true);
        window.addEventListener('drop', (e) => {
            e.preventDefault(); e.stopPropagation();
            const file = e.dataTransfer.files[0];
            if (file && (file.name.endsWith('.md') || file.name.endsWith('.txt'))) {
                handleFile(file);
            }
        }, true);

        function showConfirmModal() {
            return new Promise((resolve) => {
                const modal = document.getElementById('custom-confirm-modal');
                const btnReplace = document.getElementById('modal-btn-replace');
                const btnCancel = document.getElementById('modal-btn-cancel');

                modal.classList.remove('hidden');
                const cleanup = () => { modal.classList.add('hidden'); btnReplace.onclick = null; btnCancel.onclick = null; };

                btnReplace.onclick = () => { cleanup(); resolve(true); };
                btnCancel.onclick = () => { cleanup(); resolve(false); };
            });
        }

        function handleFile(file) {
            const reader = new FileReader();
            reader.onload = async (e) => {
                const incomingText = e.target.result;
                if (rawMarkdown.trim() !== '') {
                    const doReplace = await showConfirmModal();
                    if (doReplace) vditorInstance.setValue(incomingText);
                    else vditorInstance.insertValue(incomingText);
                } else {
                    vditorInstance.setValue(incomingText);
                }
                rawMarkdown = vditorInstance.getValue();
                localStorage.setItem(DRAFT_KEY, rawMarkdown);
                updateSaveButtonState();
                updateTOCEditMode(rawMarkdown);
            };
            reader.readAsText(file);
            fileInput.value = ""; 
        }

        btnAction.addEventListener('click', async () => {
            if (vditorInstance) rawMarkdown = vditorInstance.getValue(); 
            if (rawMarkdown.trim() === "") return showToast("You haven't entered anything!");

            // No validation check needed anymore. The mask makes format errors impossible.
            const ttlSeconds = getTtlSeconds();

            btnAction.innerHTML = '<i class="bi bi-arrow-repeat spinner"></i>';
            btnAction.classList.add('disabled');
            btnAction.classList.remove('unsaved');

            try {
                const payload = { content: rawMarkdown };
                if (ttlSeconds !== null) payload.ttl_seconds = ttlSeconds;

                const response = await fetch(`${baseUrl}/api/save`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                
                if(!response.ok) throw new Error("Failed to save.");
                
                const data = await response.json();
                localStorage.removeItem(DRAFT_KEY);
                window.location.href = `${baseUrl}/${data.uuid}`;
            } catch (err) {
                showToast("Failed to publish snippet!");
                btnAction.innerHTML = '<i class="bi bi-cloud-arrow-up"></i>';
                btnAction.classList.remove('disabled');
                btnAction.classList.add('unsaved');
            }
        });
    }
});