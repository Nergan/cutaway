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
    
    let vditorInstance = null;
    let rawMarkdown = "";
    
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
    
    btnToggleBar.addEventListener('click', () => {
        bottomContainer.classList.toggle('collapsed');
        editorContainer.classList.toggle('expanded-view');
        
        const icon = btnToggleBar.querySelector('i');
        if (bottomContainer.classList.contains('collapsed')) {
            icon.classList.remove('bi-chevron-down');
            icon.classList.add('bi-chevron-up');
        } else {
            icon.classList.remove('bi-chevron-up');
            icon.classList.add('bi-chevron-down');
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

    // --- TEXT & ID CLEANERS (Supports Cyrillic & other languages!) ---
    function getCleanText(rawText) {
        if (!rawText) return '';
        let text = rawText.replace(/[*_~`]/g, '');
        text = text.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
        let tmp = document.createElement('div');
        tmp.innerHTML = text;
        return (tmp.textContent || tmp.innerText || '').trim();
    }

    function generateId(text) {
        // \p{L} keeps all letters (including Russian/Cyrillic)
        // \p{N} keeps all numbers
        let id = text.toLowerCase().trim()
            .replace(/[\s]+/g, '-')
            .replace(/[^\p{L}\p{N}\-_]/gu, '') 
            .replace(/^-+|-+$/g, '');
        return id || 'heading'; // Fallback so it's never completely empty
    }

    // --- TOC GENERATOR & NATIVE SCROLL ---
    function updateTOC(md) {
        const tocContent = document.getElementById('toc-content');
        tocContent.innerHTML = "";
        
        const tokens = marked.lexer(md);
        const headings =[];
        
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
            
            // Create a unique ID even if multiple headings have the same name
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
                    // Standard native browser smooth scroll
                    if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                } else {
                    const editorHeadings = document.querySelectorAll('.vditor-ir h1, .vditor-ir h2, .vditor-ir h3, .vditor-ir h4, .vditor-ir h5, .vditor-ir h6, .vditor-ir[data-type="NodeHeading"]');
                    
                    // Match the correct heading occurrence
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
        btnAction.innerHTML = '<i class="bi bi-cloud-arrow-up"></i>';
        btnAction.title = "Save snippet (Ctrl + S)";
        
        vditorInstance = new Vditor('editor', {
            mode: 'ir',
            theme: 'dark',
            icon: 'material',
            toolbarConfig: { hide: true },
            cache: { enable: false },
            placeholder: "Type Markdown, drag & drop a file, or click here to upload...",
            preview: {
                theme: { current: 'dark' },
                hljs: { style: 'atom-one-dark' } 
            },
            after: () => {
                bindEditorEvents();
                vditorInstance.focus();
                updateTOC(""); 
            },
            input: (val) => {
                rawMarkdown = val;
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

        function bindEditorEvents() {
            const vditorContainer = document.querySelector('.vditor-ir');
            if (vditorContainer) {
                vditorContainer.addEventListener('click', () => {
                    if (rawMarkdown.trim() === "") fileInput.click();
                });
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
            ADD_ATTR:['allow', 'allowfullscreen', 'frameborder', 'scrolling', 'id']
        });
    }
});