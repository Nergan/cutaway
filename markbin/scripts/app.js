document.addEventListener('DOMContentLoaded', () => {
    const { baseUrl, uuid } = window.MARKBIN_CONFIG;
    const isViewMode = Boolean(uuid);
    
    const btnAction = document.getElementById('btn-action');
    const btnToc = document.getElementById('btn-toc');
    const btnClear = document.getElementById('btn-clear');
    const sidebar = document.getElementById('toc-sidebar');
    const editorWrapper = document.getElementById('editor-wrapper');
    const viewer = document.getElementById('viewer');
    const toast = document.getElementById('toast');
    const fileInput = document.getElementById('file-input');
    const btnUpload = document.getElementById('btn-upload'); 
    
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
            if (bottomContainer.classList.contains('collapsed')) {
                icon.classList.replace('bi-chevron-up', 'bi-chevron-down');
            } else {
                icon.classList.replace('bi-chevron-down', 'bi-chevron-up');
            }
        } else {
            if (bottomContainer.classList.contains('collapsed')) {
                icon.classList.replace('bi-chevron-down', 'bi-chevron-up');
            } else {
                icon.classList.replace('bi-chevron-up', 'bi-chevron-down');
            }
        }
    });

    window.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'S' || e.code === 'KeyS')) {
            e.preventDefault();
            e.stopPropagation();
            if (!isViewMode && window.saveSnippet) {
                window.saveSnippet();
            }
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

    // --- TOC GENERATORS ---
    // 1. Used in View Mode (Scrapes rendered HTML DOM)
    function buildTOCFromDOM(container) {
        const tocContent = document.getElementById('toc-content');
        tocContent.innerHTML = "";
        const headings = container.querySelectorAll('h1, h2, h3, h4, h5, h6');
        
        if (headings.length === 0) {
            tocContent.innerHTML = "<span style='color: #666; font-size: 0.9rem'>No headings found.</span>";
            return;
        }

        headings.forEach(h => {
            const depth = parseInt(h.tagName.substring(1));
            const text = getCleanText(h.textContent);
            if (!h.id) h.id = generateId(text);
            
            const tocItem = document.createElement('a');
            tocItem.href = `#${h.id}`;
            tocItem.className = 'toc-item';
            tocItem.style.marginLeft = `${(depth - 1) * 15}px`;
            tocItem.textContent = text;
            
            tocItem.addEventListener('click', (e) => {
                e.preventDefault();
                h.scrollIntoView({ behavior: 'smooth', block: 'start' });
            });
            tocContent.appendChild(tocItem);
        });
    }

    // 2. Used in Edit Mode (Lightweight Regex + Virtual DOM Scraper)
    function updateTOCEditMode(md) {
        const tocContent = document.getElementById('toc-content');
        tocContent.innerHTML = "";
        
        // Strip out code blocks to prevent false-positive headings
        const noCode = md.replace(/```[\s\S]*?```/g, '');
        const headingRegex = /^(#{1,6})\s+(.+)$/gm;
        let match;
        const headings =[];
        
        while ((match = headingRegex.exec(noCode)) !== null) {
            headings.push({
                depth: match[1].length,
                text: getCleanText(match[2].trim())
            });
        }
        
        if (headings.length === 0) {
            tocContent.innerHTML = "<span style='color: #666; font-size: 0.9rem'>No headings found.</span>";
            return;
        }

        const idCounts = {};
        
        headings.forEach(h => {
            if (!h.text) return;
            
            let baseId = generateId(h.text);
            let id = baseId;
            if (idCounts[baseId]) {
                id = `${baseId}-${idCounts[baseId]}`;
                idCounts[baseId]++;
            } else {
                idCounts[baseId] = 1;
            }
            
            const tocItem = document.createElement('a');
            tocItem.href = `#`;
            tocItem.className = 'toc-item';
            tocItem.style.marginLeft = `${(h.depth - 1) * 15}px`;
            tocItem.textContent = h.text;
            
            tocItem.addEventListener('click', (e) => {
                e.preventDefault();
                const editorHeadings = document.querySelectorAll('.vditor-ir h1, .vditor-ir h2, .vditor-ir h3, .vditor-ir h4, .vditor-ir h5, .vditor-ir h6, .vditor-ir[data-type="NodeHeading"]');
                
                let targetOccurrence = id.includes('-') ? parseInt(id.split('-').pop()) || 0 : 0;
                let matchIndex = 0;
                
                for (let el of editorHeadings) {
                    const elCleanText = getCleanText(el.textContent);
                    if (generateId(elCleanText) === baseId) {
                        if (matchIndex === targetOccurrence) {
                            el.scrollIntoView({ behavior: 'smooth', block: 'start' });
                            break;
                        }
                        matchIndex++;
                    }
                }
            });
            tocContent.appendChild(tocItem);
        });
    }

    if (isViewMode) {
        // --- VIEW MODE ---
        btnUpload.style.display = 'none';
        btnClear.style.display = 'none';
        
        btnAction.innerHTML = '<i class="bi bi-clipboard"></i>';
        btnAction.title = "Copy raw Markdown";
        btnAction.classList.remove('disabled');
        
        editorWrapper.classList.add('hidden');
        document.getElementById('loading').classList.remove('hidden');

        fetch(`${baseUrl}/api/docs/${uuid}`)
            .then(res => {
                if (!res.ok) throw new Error("Not Found");
                return res.json();
            })
            .then(data => {
                rawMarkdown = data.content;
                // Render view mode natively using Vditor for 100% engine parity
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
        // --- EDIT MODE ---
        btnAction.innerHTML = '<i class="bi bi-cloud-arrow-up"></i>';
        btnAction.title = "Save snippet (Ctrl + S)";
        
        btnUpload.addEventListener('click', () => fileInput.click());
        
        btnClear.addEventListener('click', () => {
            if (rawMarkdown.trim() === "") return;
            if (confirm("Are you sure you want to clear your current draft? This cannot be undone.")) {
                vditorInstance.setValue('');
                rawMarkdown = '';
                localStorage.removeItem(DRAFT_KEY);
                updateSaveButtonState();
                updateTOCEditMode(rawMarkdown);
            }
        });

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
                btnAction.classList.add('unsaved'); // Visual indicator
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

        // Safe Drag and drop handling
        function handleFile(file) {
            const reader = new FileReader();
            reader.onload = (e) => {
                const incomingText = e.target.result;
                if (rawMarkdown.trim() !== '') {
                    if (confirm("Replace existing document with this file?\n\nClick 'Cancel' to append it at your cursor instead.")) {
                        vditorInstance.setValue(incomingText);
                    } else {
                        vditorInstance.insertValue(incomingText);
                    }
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

        window.saveSnippet = async function() {
            if (vditorInstance) rawMarkdown = vditorInstance.getValue(); 

            if (rawMarkdown.trim() === "") {
                showToast("You haven't entered anything!");
                return;
            }

            btnAction.innerHTML = '<i class="bi bi-arrow-repeat spinner"></i>';
            btnAction.classList.add('disabled');
            btnAction.classList.remove('unsaved'); // Hide dot while saving

            try {
                const response = await fetch(`${baseUrl}/api/save`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ content: rawMarkdown })
                });
                
                if(!response.ok) throw new Error("Failed to save.");
                
                const data = await response.json();
                localStorage.removeItem(DRAFT_KEY);
                window.location.href = `${baseUrl}/${data.uuid}`;
            } catch (err) {
                showToast("Failed to save snippet!");
                btnAction.innerHTML = '<i class="bi bi-cloud-arrow-up"></i>';
                btnAction.classList.remove('disabled');
                btnAction.classList.add('unsaved'); // Restore dot on failure
            }
        };

        btnAction.addEventListener('click', window.saveSnippet);
    }
});