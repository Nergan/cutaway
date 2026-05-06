document.addEventListener('DOMContentLoaded', () => {
    const { baseUrl, uuid } = window.MARKBIN_CONFIG;
    const isViewMode = Boolean(uuid);
    
    const btnAction = document.getElementById('btn-action');
    const btnToc = document.getElementById('btn-toc');
    const btnUpload = document.getElementById('btn-upload');
    const sidebar = document.getElementById('toc-sidebar');
    const editorWrapper = document.getElementById('editor-wrapper');
    const viewer = document.getElementById('viewer');
    const toast = document.getElementById('toast');
    const fileInput = document.getElementById('file-input');
    
    let vditorInstance = null;
    let rawMarkdown = "";
    const DRAFT_KEY = 'markbin_draft';

    // --- SETUP GITHUB-FLAVORED MARKDOWN PARSER ---
    const mdParser = window.markdownit({
        html: true,       // Allow HTML tags
        linkify: true,    // Autoconvert URL-like text to links
        typographer: true, // Beautify quotes and dashes
        breaks: true      // GitHub style line-breaks
    }).use(window.markdownitTaskLists, { enabled: false }); // Add GitHub task lists support
    
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

    function generateId(text) {
        let id = text.toLowerCase().trim()
            .replace(/[\s]+/g, '-')
            .replace(/[^\p{L}\p{N}\-_]/gu, '') 
            .replace(/^-+|-+$/g, '');
        return id || 'heading'; 
    }

    // --- REVOLUTIONARY DOM-BASED TOC & SCROLLING ---
    // Instead of guessing with regex, this reads the actual rendered elements on the screen.
    function updateTOC() {
        const tocContent = document.getElementById('toc-content');
        tocContent.innerHTML = "";
        
        // Determine the correct container based on the mode
        const container = isViewMode ? viewer : document.querySelector('.vditor-ir');
        if (!container) return;

        // Find all rendered headings physically present in the DOM
        const headings = container.querySelectorAll('h1, h2, h3, h4, h5, h6');
        
        if (headings.length === 0) {
            tocContent.innerHTML = "<span style='color: #666; font-size: 0.9rem'>No headings found.</span>";
            return;
        }
        
        const idCounts = {};
        
        headings.forEach(h => {
            // Natively extracts clean text, ignoring any nested HTML like <p> inside headers!
            const cleanText = h.innerText || h.textContent || '';
            if (!cleanText.trim()) return;
            
            let baseId = generateId(cleanText);
            let id = baseId;
            if (idCounts[baseId]) {
                id = `${baseId}-${idCounts[baseId]}`;
                idCounts[baseId]++;
            } else {
                idCounts[baseId] = 1;
            }

            // Ensure the element has the ID assigned to it
            if (!h.id) h.id = id;
            
            const depth = parseInt(h.tagName.substring(1)); // e.g., 'H2' -> 2
            const tocItem = document.createElement('a');
            tocItem.href = `#${id}`;
            tocItem.className = 'toc-item';
            tocItem.style.marginLeft = `${(depth - 1) * 15}px`;
            tocItem.textContent = cleanText;
            
            // Native, direct node scrolling. It scrolls the exact physical element!
            tocItem.addEventListener('click', (e) => {
                e.preventDefault(); 
                h.scrollIntoView({ behavior: 'smooth', block: 'start' });
            });

            tocContent.appendChild(tocItem);
        });
    }

    if (isViewMode) {
        btnAction.innerHTML = '<i class="bi bi-clipboard"></i>';
        btnAction.title = "Copy raw Markdown";
        btnAction.classList.remove('disabled');
        
        if (btnUpload) btnUpload.style.display = 'none'; // Hide upload button in view mode
        
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
        
        if (btnUpload) {
            btnUpload.addEventListener('click', () => fileInput.click());
        }
        
        const savedDraft = localStorage.getItem(DRAFT_KEY) || "";
        rawMarkdown = savedDraft;

        vditorInstance = new Vditor('editor', {
            value: savedDraft, 
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
                updateSaveButtonState();
                updateTOC(); 
            },
            input: (val) => {
                rawMarkdown = val;
                localStorage.setItem(DRAFT_KEY, val); 
                updateSaveButtonState();
                updateTOC(); 
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
                localStorage.setItem(DRAFT_KEY, rawMarkdown); 
                updateSaveButtonState();
                updateTOC();
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
        // Parse with Markdown-It
        const rawHtml = mdParser.render(md);
        
        // Sanitize for security (Added inputs/classes to safely allow GitHub Task Checkboxes)
        viewer.innerHTML = DOMPurify.sanitize(rawHtml, {
            ADD_TAGS: ['iframe', 'input'],
            ADD_ATTR:['allow', 'allowfullscreen', 'frameborder', 'scrolling', 'id', 'class', 'type', 'disabled', 'checked']
        });

        // Generate the TOC dynamically from the finalized DOM
        updateTOC();
    }
});