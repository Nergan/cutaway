document.addEventListener('DOMContentLoaded', () => {
    const { baseUrl, uuid } = window.MARKBIN_CONFIG;
    const isViewMode = Boolean(uuid);
    
    const btnAction = document.getElementById('btn-action');
    const btnToc = document.getElementById('btn-toc');
    const sidebar = document.getElementById('toc-sidebar');
    const editorWrapper = document.getElementById('editor-wrapper');
    const viewer = document.getElementById('viewer');
    const toast = document.getElementById('toast');
    const fileInput = document.getElementById('file-input');
    const btnUpload = document.getElementById('btn-upload');   // upload button
    
    let vditorInstance = null;
    let rawMarkdown = "";
    
    const DRAFT_KEY = 'markbin_draft';
    
    function showToast(message) {
        toast.textContent = message;
        toast.classList.add('show');
        setTimeout(() => toast.classList.remove('show'), 3000);
    }

    // --- PANEL TOGGLES ---
    btnToc.addEventListener('click', () => {
        sidebar.classList.toggle('hidden');
    });

    const bottomContainer = document.getElementById('bottom-container');
    const btnToggleBar = document.getElementById('toggle-bar-btn');
    const editorContainer = document.getElementById('editor-container');
    
    // ✅ Set initial icon based on screen size
    const isDesktopInit = window.matchMedia('(min-width: 769px)').matches;
    const iconInit = btnToggleBar.querySelector('i');
    if (isDesktopInit) {
        iconInit.classList.remove('bi-chevron-down');
        iconInit.classList.add('bi-chevron-up');      // panel at top, collapse upward
    } else {
        iconInit.classList.remove('bi-chevron-up');
        iconInit.classList.add('bi-chevron-down');    // panel at bottom, collapse downward
    }
    
    // Toggle panel collapse (works for both mobile bottom and desktop top)
    btnToggleBar.addEventListener('click', () => {
        bottomContainer.classList.toggle('collapsed');
        editorContainer.classList.toggle('expanded-view');
        
        const icon = btnToggleBar.querySelector('i');
        const isDesktop = window.matchMedia('(min-width: 769px)').matches;
        
        if (isDesktop) {
            // Desktop top bar: swap icon meanings
            if (bottomContainer.classList.contains('collapsed')) {
                // Collapsed (hidden up) → show down arrow to expand
                icon.classList.remove('bi-chevron-up');
                icon.classList.add('bi-chevron-down');
            } else {
                // Visible → show up arrow to collapse
                icon.classList.remove('bi-chevron-down');
                icon.classList.add('bi-chevron-up');
            }
        } else {
            // Mobile bottom bar: original logic
            if (bottomContainer.classList.contains('collapsed')) {
                icon.classList.remove('bi-chevron-down');
                icon.classList.add('bi-chevron-up');
            } else {
                icon.classList.remove('bi-chevron-up');
                icon.classList.add('bi-chevron-down');
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

    // --- TOC GENERATOR & NATIVE SCROLL ---
    function updateTOC(md) {
        const tocContent = document.getElementById('toc-content');
        tocContent.innerHTML = "";
        
        const tokens = marked.lexer(md);
        const headings = [];
        
        function walkTokens(tokenList) {
            if (!tokenList) return;
            tokenList.forEach(t => {
                if (t.type === 'heading') headings.push(t);
                if (t.tokens) walkTokens(t.tokens);
                else if (t.items) walkTokens(t.items);
            });
        }
        walkTokens(tokens);
        
        if (headings.length === 0) {
            tocContent.innerHTML = "<span style='color: #666; font-size: 0.9rem'>No headings found.</span>";
            return;
        }
        
        const idCounts = {};
        
        headings.forEach(h => {
            const cleanText = getCleanText(h.text);
            if (!cleanText) return; 
            
            let baseId = generateId(cleanText);
            let id = baseId;
            if (idCounts[baseId]) {
                id = `${baseId}-${idCounts[baseId]}`;
                idCounts[baseId]++;
            } else {
                idCounts[baseId] = 1;
            }
            
            const tocItem = document.createElement('a');
            tocItem.href = `#${id}`;
            tocItem.className = 'toc-item';
            tocItem.style.marginLeft = `${(h.depth - 1) * 15}px`;
            tocItem.textContent = cleanText;
            
            tocItem.addEventListener('click', (e) => {
                e.preventDefault(); 
                
                if (isViewMode) {
                    const target = document.getElementById(id);
                    if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                } else {
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
                }
            });

            tocContent.appendChild(tocItem);
        });
    }

    if (isViewMode) {
        // --- VIEW MODE ---
        btnUpload.style.display = 'none';  // hide upload button
        
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
                renderMarkdown(rawMarkdown);
                document.getElementById('loading').classList.add('hidden');
                viewer.classList.remove('hidden');
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
        
        // Upload button: click triggers hidden file input
        btnUpload.addEventListener('click', () => {
            fileInput.click();
        });
        
        // Check for saved draft in local storage
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
                updateTOC(rawMarkdown); 
            },
            input: (val) => {
                rawMarkdown = val;
                localStorage.setItem(DRAFT_KEY, val);
                updateSaveButtonState();
                updateTOC(val); 
            }
        });

        function updateSaveButtonState() {
            if (rawMarkdown.trim() === "") {
                btnAction.classList.add('disabled');
            } else {
                btnAction.classList.remove('disabled');
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

        function handleFile(file) {
            const reader = new FileReader();
            reader.onload = (e) => {
                vditorInstance.setValue(e.target.result);
                rawMarkdown = e.target.result;
                localStorage.setItem(DRAFT_KEY, rawMarkdown);
                updateSaveButtonState();
                updateTOC(rawMarkdown);
            };
            reader.readAsText(file);
            fileInput.value = ""; 
        }

        window.saveSnippet = async function() {
            if (vditorInstance) {
                rawMarkdown = vditorInstance.getValue(); 
            }

            if (rawMarkdown.trim() === "") {
                showToast("You haven't entered anything!");
                return;
            }

            btnAction.innerHTML = '<i class="bi bi-arrow-repeat spinner"></i>';
            btnAction.classList.add('disabled');

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
            }
        };

        btnAction.addEventListener('click', window.saveSnippet);
    }

    function renderMarkdown(md) {
        updateTOC(md);
        
        const renderer = new marked.Renderer();
        const idCounts = {};
        
        renderer.heading = function(headingObj) {
            const text = headingObj.text || arguments[0];
            const depth = headingObj.depth || arguments[1];
            
            const cleanText = getCleanText(text);
            let baseId = generateId(cleanText);
            let id = baseId;
            
            if (idCounts[baseId]) {
                id = `${baseId}-${idCounts[baseId]}`;
                idCounts[baseId]++;
            } else {
                idCounts[baseId] = 1;
            }
            
            return `<h${depth} id="${id}">${text}</h${depth}>`;
        };
        marked.use({ renderer });
        
        const rawHtml = marked.parse(md);
        
        viewer.innerHTML = DOMPurify.sanitize(rawHtml, {
            ADD_TAGS: ['iframe'],
            ADD_ATTR: ['allow', 'allowfullscreen', 'frameborder', 'scrolling', 'id']
        });
    }
});