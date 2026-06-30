(function() {
    'use strict';

    let vfs = [];
    let activeFilePath = null;
    let selectedTreeNodes = new Set();
    let expandedDirs = new Set();
    let focusedIndex = -1;
    let anchorIndex = -1;
    let maxRepoSize = 10 * 1024 * 1024;
    
    let historyStack = [];
    let historyIndex = -1;
    let typingTimer = null;
    let dragDebounceTimer = null;
    
    const ui = {
        dropZone: document.getElementById('dropZone'),
        folderInput: document.getElementById('folderInput'),
        filesInput: document.getElementById('filesInput'),
        zipInput: document.getElementById('zipInput'),
        uploadFolderBtn: document.getElementById('uploadFolderBtn'),
        uploadFilesBtn: document.getElementById('uploadFilesBtn'),
        uploadZipBtn: document.getElementById('uploadZipBtn'),
        githubBtnToggle: document.getElementById('githubBtnToggle'),
        githubPrompt: document.getElementById('githubPrompt'),
        githubUrlInput: document.getElementById('githubUrlInput'),
        githubSubmitBtn: document.getElementById('githubSubmitBtn'),
        addFileBtn: document.getElementById('addFileBtn'),
        addFolderBtn: document.getElementById('addFolderBtn'),
        publishBtn: document.getElementById('publishBtn'),
        forkBtn: document.getElementById('forkBtn'),
        downloadDropdownBtn: document.getElementById('downloadDropdownBtn'),
        downloadZip: document.getElementById('downloadZip'),
        downloadMd: document.getElementById('downloadMd'),
        downloadCurrentFileBtn: document.getElementById('downloadCurrentFileBtn'),
        fileTree: document.getElementById('fileTree'),
        sidebar: document.getElementById('sidebar'),
        resizer: document.getElementById('sidebarResizer'),
        toggleSidebarBtn: document.getElementById('toggleSidebarBtn'),
        codeInput: document.getElementById('codeInput'),
        noFileScreen: document.getElementById('noFileScreen'),
        currentFilePath: document.getElementById('currentFilePath'),
        charCount: document.getElementById('charCount'),
        repoSizeText: document.getElementById('repoSizeText'),
        repoSizeProgress: document.getElementById('repoSizeProgress'),
        uuidDisplay: document.getElementById('uuid-display')
    };

    const saveStateToHistory = () => {
        if (window.IS_READONLY) return;
        const state = {
            vfs: JSON.parse(JSON.stringify(vfs)),
            activeFilePath,
            selected: Array.from(selectedTreeNodes),
            expanded: Array.from(expandedDirs),
            cursor: document.activeElement === ui.codeInput ? 
                    { start: ui.codeInput.selectionStart, end: ui.codeInput.selectionEnd } : null
        };
        
        if (historyIndex < historyStack.length - 1) historyStack = historyStack.slice(0, historyIndex + 1);
        historyStack.push(state);
        if (historyStack.length > 50) historyStack.shift();
        else historyIndex++;
        persistState();
    };

    const restoreHistoryState = (index) => {
        if (index < 0 || index >= historyStack.length) return;
        const state = historyStack[index];
        vfs = JSON.parse(JSON.stringify(state.vfs));
        activeFilePath = state.activeFilePath;
        selectedTreeNodes = new Set(state.selected);
        expandedDirs = new Set(state.expanded);
        
        renderTree();
        if (activeFilePath) {
            const f = vfs.find(x => x.path === activeFilePath);
            if (f && !f.is_dir) {
                ui.codeInput.value = f.content || '';
                ui.codeInput.dispatchEvent(new Event('input'));
                updateCurrentFilePathUI(f.path);
                if (state.cursor) {
                    ui.codeInput.focus();
                    ui.codeInput.setSelectionRange(state.cursor.start, state.cursor.end);
                }
            } else {
                showNoFile();
            }
        } else {
            showNoFile();
        }
        persistState();
    };

    const performUndo = () => { if (historyIndex > 0) { historyIndex--; restoreHistoryState(historyIndex); } };
    const performRedo = () => { if (historyIndex < historyStack.length - 1) { historyIndex++; restoreHistoryState(historyIndex); } };

    const init = () => {
        const rawData = document.getElementById('repo-data').textContent;
        const injectedData = JSON.parse(rawData || '[]');

        if (window.IS_READONLY) {
            vfs = injectedData;
            expandedDirs.clear();
            renderTree();
        } else {
            const saved = localStorage.getItem('toadcode_vfs');
            if (saved && injectedData.length === 0) {
                try { vfs = JSON.parse(saved); } catch (e) { vfs = []; }
            } else {
                vfs = injectedData;
            }
            expandedDirs.clear();
            saveStateToHistory(); 
            renderTree();
            bindEditEvents();
        }

        checkTotalSize();
        
        const pathParts = window.location.pathname.split('/').filter(Boolean);
        if (pathParts.length > 2 && window.IS_READONLY) {
            const targetPath = pathParts.slice(2).join('/');
            const targetFile = vfs.find(f => f.path === targetPath);
            if (targetFile && !targetFile.is_dir) {
                openFile(targetPath);
                const dirs = targetPath.split('/');
                let current = '';
                for(let i=0; i<dirs.length-1; i++) {
                    current += dirs[i] + '/';
                    expandedDirs.add(current);
                }
                renderTree();
            }
        } else if (vfs.length > 0) {
            const files = vfs.filter(f => !f.is_dir).sort((a,b) => a.path.localeCompare(b.path));
            if (files.length > 0) openFile(files[0].path);
        }

        bindGlobalEvents();
        bindResizer();
        bindLassoSelection();
    };

    const persistState = () => {
        if (!window.IS_READONLY) {
            localStorage.setItem('toadcode_vfs', JSON.stringify(vfs));
            checkTotalSize();
        }
    };

    const updateCurrentFilePathUI = (path) => {
        ui.currentFilePath.innerHTML = `<i class="bi bi-file-code me-1"></i> ${path}`;
        ui.downloadCurrentFileBtn.classList.remove('d-none');
        if (window.IS_READONLY && window.CODE_ID) {
            window.history.replaceState(null, '', `/toadcode/${window.CODE_ID}/${path}`);
        }
    };

    const showNoFile = () => {
        ui.codeInput.classList.add('d-none');
        ui.noFileScreen.style.display = 'flex';
        ui.currentFilePath.innerHTML = `<i class="bi bi-terminal me-1"></i> Ready`;
        ui.downloadCurrentFileBtn.classList.add('d-none');
        ui.codeInput.value = '';
        ui.codeInput.dispatchEvent(new Event('input')); 
        ui.charCount.textContent = '0 characters';
        activeFilePath = null;
    };

    const isTextContent = async (fileBlob) => {
        const buffer = await fileBlob.slice(0, 8192).arrayBuffer();
        const view = new Uint8Array(buffer);
        for (let i = 0; i < view.length; i++) if (view[i] === 0) return false;
        return true;
    };

    const hoistRoot = (files) => {
        if (files.length <= 1) return files;
        const firstParts = files[0].path.split('/');
        if (firstParts.length === 1) return files; 
        const rootDir = firstParts[0] + '/';
        const allMatch = files.every(f => f.path.startsWith(rootDir));
        if (allMatch) {
            files.forEach(f => f.path = f.path.substring(rootDir.length));
            return hoistRoot(files.filter(f => f.path.length > 0)); 
        }
        return files;
    };

    const processFiles = async (entries) => {
        let newFiles = [];
        let ignoredCount = 0;
        for (const entry of entries) {
            if (entry.is_dir) {
                newFiles.push({ path: entry.path.endsWith('/') ? entry.path : entry.path + '/', is_dir: true, content: '' });
                continue;
            }
            if (await isTextContent(entry.file)) {
                newFiles.push({ path: entry.path, is_dir: false, content: await entry.file.text() });
            } else {
                ignoredCount++;
            }
        }

        if (newFiles.length > 0) {
            newFiles = hoistRoot(newFiles);
            newFiles.forEach(nf => {
                const existing = vfs.findIndex(f => f.path === nf.path);
                if (existing >= 0) vfs[existing] = nf;
                else vfs.push(nf);
            });
            saveStateToHistory();
            renderTree();
            if (ignoredCount > 0) showNotification(`Ignored ${ignoredCount} binary files.`);
        } else {
            showNotification('No valid files found to upload.', true);
        }
    };

    const traverseFileTree = async (item, path = '') => {
        let entries = [];
        if (item.isFile) {
            const file = await new Promise(resolve => item.file(resolve));
            if (file.name.endsWith('.zip') || file.type === 'application/zip') {
                await handleZipBlob(file); 
            } else {
                entries.push({ path: path + file.name, is_dir: false, file });
            }
        } else if (item.isDirectory) {
            entries.push({ path: path + item.name + '/', is_dir: true });
            const dirReader = item.createReader();
            const childEntries = await new Promise(resolve => dirReader.readEntries(resolve));
            for (let i = 0; i < childEntries.length; i++) {
                entries.push(...await traverseFileTree(childEntries[i], path + item.name + '/'));
            }
        }
        return entries;
    };

    const handleZipBlob = async (blob, targetSubpath = '') => {
        try {
            const zip = await JSZip.loadAsync(blob);
            const entries = [];
            const rootFolders = new Set();
            for (const p in zip.files) {
                const parts = p.split('/');
                if (parts.length > 1) rootFolders.add(parts[0]);
            }
            let rootPrefix = rootFolders.size === 1 ? Array.from(rootFolders)[0] + '/' : '';
            if (targetSubpath && !targetSubpath.endsWith('/')) targetSubpath += '/';

            for (const p in zip.files) {
                let relativePath = p;
                if (rootPrefix && relativePath.startsWith(rootPrefix)) {
                    relativePath = relativePath.substring(rootPrefix.length);
                }
                if (targetSubpath) {
                    if (!relativePath.startsWith(targetSubpath)) continue;
                    relativePath = relativePath.substring(targetSubpath.length);
                }
                if (!relativePath) continue;

                const zipObj = zip.files[p];
                if (zipObj.dir) {
                    entries.push({ path: relativePath, is_dir: true });
                } else {
                    const fileBlob = await zipObj.async("blob");
                    entries.push({ path: relativePath, is_dir: false, file: fileBlob });
                }
            }
            if (entries.length > 0) await processFiles(entries);
            else showNotification("Folder/subpath not found or empty in ZIP.", true);

        } catch (e) {
            showNotification('Failed to parse ZIP file', true);
        }
    };

    const parseRepoUrl = (url) => {
        let zipUrl = ''; let subpath = '';
        url = url.trim().replace(/\/$/, '');

        let ghMatch = url.match(/github\.com\/([^\/]+)\/([^\/]+)(?:\/tree\/([^\/]+)\/?(.*))?/);
        if (ghMatch) {
            const [, owner, repo, branch, path] = ghMatch;
            zipUrl = `https://api.github.com/repos/${owner}/${repo}/zipball/${branch || ''}`;
            subpath = path || '';
            return { zipUrl, subpath };
        }

        return null;
    };

    const buildTreeData = () => {
        const root = { name: '', children: {}, isDir: true, path: '' };
        vfs.forEach(file => {
            const parts = file.path.split('/').filter(Boolean);
            let current = root;
            parts.forEach((part, i) => {
                const isLast = i === parts.length - 1;
                const isDir = !isLast || file.is_dir;
                if (!current.children[part]) {
                    current.children[part] = {
                        name: part,
                        path: parts.slice(0, i + 1).join('/') + (isDir ? '/' : ''),
                        isDir: isDir,
                        children: {}
                    };
                }
                current = current.children[part];
            });
        });
        return root;
    };

    const renderTree = () => {
        if (vfs.length === 0 && window.IS_READONLY) {
            ui.sidebar.classList.add('d-none');
            ui.resizer.classList.add('d-none');
            ui.toggleSidebarBtn.classList.add('d-none');
            return;
        }
        
        ui.toggleSidebarBtn.classList.remove('d-none');
        if (!ui.sidebar.classList.contains('collapsed')) {
            ui.sidebar.classList.remove('d-none');
            ui.sidebar.classList.add('d-flex');
            ui.resizer.classList.remove('d-none');
        }
        
        const root = buildTreeData();
        ui.fileTree.innerHTML = '';
        const renderList = [];
        
        const flattenNode = (node, indent = 0) => {
            const sortedKeys = Object.keys(node.children).sort((a,b) => {
                const aIsDir = node.children[a].isDir;
                const bIsDir = node.children[b].isDir;
                if (aIsDir && !bIsDir) return -1;
                if (!aIsDir && bIsDir) return 1;
                return a.localeCompare(b);
            });

            sortedKeys.forEach(key => {
                const child = node.children[key];
                renderList.push({ child, indent });
                if (child.isDir && expandedDirs.has(child.path)) flattenNode(child, indent + 1);
            });
        };
        
        flattenNode(root);

        renderList.forEach((item, index) => {
            const { child, indent } = item;
            const div = document.createElement('div');
            div.className = `tree-item ${child.path === activeFilePath && !child.isDir ? 'active' : ''}`;
            div.style.paddingLeft = `${indent * 15 + 10}px`;
            div.dataset.path = child.path;
            div.dataset.isdir = child.isDir;
            div.dataset.index = index;
            
            if (selectedTreeNodes.has(child.path)) div.classList.add('selected');
            if (focusedIndex === index) div.classList.add('focused-item');

            const icon = child.isDir ? (expandedDirs.has(child.path) ? 'bi-folder2-open' : 'bi-folder-fill') : 'bi-file-earmark-code';
            const caret = child.isDir ? `<i class="bi ${expandedDirs.has(child.path) ? 'bi-caret-down-fill' : 'bi-caret-right-fill'} me-1" style="font-size:0.7rem;"></i>` : `<span class="me-3"></span>`;
            
            let html = `${caret}<i class="bi ${icon} me-2 tree-icon"></i><span class="tree-name">${child.name}</span>`;
            
            if (!window.IS_READONLY) {
                html += `<div class="tree-actions ms-auto">
                            <i class="bi bi-pencil rename-btn" title="Rename"></i>
                            <i class="bi bi-trash delete-btn ms-2 text-danger" title="Delete"></i>
                         </div>`;
            }
            div.innerHTML = html;
            ui.fileTree.appendChild(div);
        });
        
        bindTreeEvents();
    };

    const bindTreeEvents = () => {
        const items = Array.from(ui.fileTree.querySelectorAll('.tree-item'));
        
        items.forEach((item, index) => {
            item.addEventListener('click', (e) => {
                e.stopPropagation();
                if (e.target.closest('.rename-btn, .delete-btn, .inline-edit-input')) return;
                
                const path = item.dataset.path;
                const isDir = item.dataset.isdir === 'true';

                if (isDir) {
                    if (expandedDirs.has(path)) expandedDirs.delete(path);
                    else expandedDirs.add(path);
                }

                if (e.shiftKey && anchorIndex !== -1) {
                    const start = Math.min(anchorIndex, index);
                    const end = Math.max(anchorIndex, index);
                    selectedTreeNodes.clear();
                    for (let i = start; i <= end; i++) selectedTreeNodes.add(items[i].dataset.path);
                } else if (e.ctrlKey || e.metaKey) {
                    anchorIndex = index;
                    if (selectedTreeNodes.has(path)) selectedTreeNodes.delete(path);
                    else selectedTreeNodes.add(path);
                } else {
                    anchorIndex = index;
                    selectedTreeNodes.clear();
                    selectedTreeNodes.add(path);
                    if (!isDir) openFile(path);
                }
                
                focusedIndex = index;
                renderTree();
            });

            if (!window.IS_READONLY) {
                const renameBtn = item.querySelector('.rename-btn');
                const deleteBtn = item.querySelector('.delete-btn');
                
                if (renameBtn) renameBtn.addEventListener('click', () => initiateRenameInline(item));
                if (deleteBtn) deleteBtn.addEventListener('click', () => {
                    const pathToDelete = item.dataset.path;
                    vfs = vfs.filter(f => !f.path.startsWith(pathToDelete));
                    if (activeFilePath?.startsWith(pathToDelete)) showNoFile();
                    selectedTreeNodes.delete(pathToDelete);
                    saveStateToHistory();
                    renderTree();
                });

                item.draggable = true;
                item.addEventListener('dragstart', (e) => {
                    if (e.target.closest('input')) { e.preventDefault(); return; }
                    if (!selectedTreeNodes.has(item.dataset.path)) {
                        selectedTreeNodes.clear();
                        selectedTreeNodes.add(item.dataset.path);
                    }
                    e.dataTransfer.setData('text/plain', JSON.stringify([...selectedTreeNodes]));
                });
                item.addEventListener('dragover', (e) => {
                    if (!e.dataTransfer.types.includes('Files')) {
                        e.preventDefault();
                        item.classList.add('drag-hover');
                    }
                });
                item.addEventListener('dragleave', () => item.classList.remove('drag-hover'));
                item.addEventListener('drop', (e) => {
                    if (e.dataTransfer.types.includes('Files')) return;
                    e.preventDefault(); e.stopPropagation();
                    item.classList.remove('drag-hover');
                    
                    let targetDir = item.dataset.isdir === 'true' ? item.dataset.path : item.dataset.path.split('/').slice(0,-1).join('/') + '/';
                    if (targetDir === '/') targetDir = '';
                    
                    const pathsToMove = JSON.parse(e.dataTransfer.getData('text/plain') || '[]');
                    pathsToMove.forEach(oldPath => {
                        const name = oldPath.split('/').filter(Boolean).pop();
                        const newPath = oldPath.endsWith('/') ? `${targetDir}${name}/` : `${targetDir}${name}`;
                        if (oldPath !== newPath && !newPath.startsWith(oldPath)) renamePath(oldPath, newPath);
                    });
                    selectedTreeNodes.clear();
                    saveStateToHistory();
                    renderTree();
                });

                let touchTimer = null;
                let isTouchDragging = false;
                let ghostEl = null;

                item.addEventListener('touchstart', (e) => {
                    if (e.target.closest('input')) return;
                    touchTimer = setTimeout(() => {
                        isTouchDragging = true;
                        ghostEl = item.cloneNode(true);
                        ghostEl.style.position = 'fixed';
                        ghostEl.style.opacity = '0.5';
                        ghostEl.style.pointerEvents = 'none';
                        ghostEl.style.zIndex = '9999';
                        document.body.appendChild(ghostEl);
                        if (!selectedTreeNodes.has(item.dataset.path)) {
                            selectedTreeNodes.clear();
                            selectedTreeNodes.add(item.dataset.path);
                            renderTree();
                        }
                    }, 500);
                }, { passive: true });

                item.addEventListener('touchmove', (e) => {
                    if (!isTouchDragging) { clearTimeout(touchTimer); return; }
                    e.preventDefault();
                    const touch = e.touches[0];
                    ghostEl.style.left = touch.clientX + 10 + 'px';
                    ghostEl.style.top = touch.clientY + 10 + 'px';
                    
                    const targetEl = document.elementFromPoint(touch.clientX, touch.clientY);
                    const dropItem = targetEl?.closest('.tree-item');
                    ui.fileTree.querySelectorAll('.tree-item').forEach(i => i.classList.remove('drag-hover'));
                    if (dropItem) dropItem.classList.add('drag-hover');
                }, { passive: false });

                item.addEventListener('touchend', (e) => {
                    clearTimeout(touchTimer);
                    if (isTouchDragging) {
                        isTouchDragging = false;
                        if (ghostEl) ghostEl.remove();
                        const touch = e.changedTouches[0];
                        const targetEl = document.elementFromPoint(touch.clientX, touch.clientY);
                        const dropItem = targetEl?.closest('.tree-item');
                        ui.fileTree.querySelectorAll('.tree-item').forEach(i => i.classList.remove('drag-hover'));
                        
                        if (dropItem) {
                            let targetDir = dropItem.dataset.isdir === 'true' ? dropItem.dataset.path : dropItem.dataset.path.split('/').slice(0,-1).join('/') + '/';
                            if (targetDir === '/') targetDir = '';
                            
                            const pathsToMove = Array.from(selectedTreeNodes);
                            pathsToMove.forEach(oldPath => {
                                const name = oldPath.split('/').filter(Boolean).pop();
                                const newPath = oldPath.endsWith('/') ? `${targetDir}${name}/` : `${targetDir}${name}`;
                                if (oldPath !== newPath && !newPath.startsWith(oldPath)) renamePath(oldPath, newPath);
                            });
                            selectedTreeNodes.clear();
                            saveStateToHistory();
                            renderTree();
                        }
                    }
                });
            }
        });
    };

    const bindLassoSelection = () => {
        let isLassoing = false;
        let lassoBox = null;
        let startX, startY;

        ui.fileTree.addEventListener('mousedown', (e) => {
            if (e.target.closest('.tree-item')) return;
            isLassoing = true;
            startX = e.clientX;
            startY = e.clientY + ui.fileTree.scrollTop;
            
            lassoBox = document.createElement('div');
            lassoBox.className = 'lasso-selection';
            ui.fileTree.appendChild(lassoBox);
            
            if (!e.ctrlKey && !e.metaKey && !e.shiftKey) {
                selectedTreeNodes.clear();
                Array.from(ui.fileTree.querySelectorAll('.tree-item.selected')).forEach(i => i.classList.remove('selected'));
            }
        });

        document.addEventListener('mousemove', (e) => {
            if (!isLassoing) return;
            const currentX = e.clientX;
            const currentY = e.clientY + ui.fileTree.scrollTop;
            const left = Math.min(startX, currentX);
            const top = Math.min(startY, currentY);
            const width = Math.abs(currentX - startX);
            const height = Math.abs(currentY - startY);
            
            const treeRect = ui.fileTree.getBoundingClientRect();
            lassoBox.style.left = (left - treeRect.left) + 'px';
            lassoBox.style.top = (top - treeRect.top) + 'px';
            lassoBox.style.width = width + 'px';
            lassoBox.style.height = height + 'px';
            
            const items = Array.from(ui.fileTree.querySelectorAll('.tree-item'));
            items.forEach(item => {
                const rect = item.getBoundingClientRect();
                const itemTop = rect.top + ui.fileTree.scrollTop;
                const itemBottom = itemTop + rect.height;
                const itemLeft = rect.left;
                const itemRight = rect.right;
                
                const intersect = !(itemRight < left || itemLeft > left + width || itemBottom < top || itemTop > top + height);
                if (intersect) {
                    selectedTreeNodes.add(item.dataset.path);
                    item.classList.add('selected');
                } else if (!e.ctrlKey && !e.metaKey && !e.shiftKey) {
                    selectedTreeNodes.delete(item.dataset.path);
                    item.classList.remove('selected');
                }
            });
        });

        document.addEventListener('mouseup', () => {
            if (isLassoing) {
                isLassoing = false;
                if (lassoBox) lassoBox.remove();
            }
        });
    };

    const initiateRenameInline = (itemEl) => {
        const oldPath = itemEl.dataset.path;
        const isDir = itemEl.dataset.isdir === 'true';
        const nameSpan = itemEl.querySelector('.tree-name');
        const originalName = nameSpan.textContent;
        const parentDir = oldPath.split('/').slice(0, oldPath.endsWith('/') ? -2 : -1).join('/') + (oldPath.includes('/') ? '/' : '');
        
        const input = document.createElement('input');
        input.type = 'text';
        input.value = originalName;
        input.className = 'inline-edit-input form-control form-control-sm bg-dark text-white border-secondary p-0 px-1 ms-1 custom-font';
        input.style.height = '20px';
        
        nameSpan.replaceWith(input);
        input.focus();
        input.setSelectionRange(0, originalName.lastIndexOf('.') > 0 && !isDir ? originalName.lastIndexOf('.') : originalName.length);

        const commit = () => {
            if (input.dataset.committed) return;
            input.dataset.committed = 'true';
            let newName = input.value.trim();
            if (newName && newName !== originalName) {
                const newPath = parentDir + newName + (isDir ? '/' : '');
                if (vfs.some(f => f.path === newPath)) {
                    showNotification(`Name '${newName}' already exists here!`, true);
                } else {
                    renamePath(oldPath, newPath);
                    saveStateToHistory();
                }
            }
            renderTree();
        };

        const checkDupe = () => {
            let val = input.value.trim();
            if(val !== originalName && vfs.some(f => f.path === parentDir + val + (isDir ? '/' : ''))) input.style.borderColor = 'red';
            else input.style.borderColor = '';
        };

        input.addEventListener('input', checkDupe);
        input.addEventListener('blur', commit);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                if(input.style.borderColor === 'red') e.preventDefault();
                else commit();
            }
            if (e.key === 'Escape') { input.dataset.committed = 'true'; renderTree(); }
        });
    };

    const initiateCreateInline = (isDir) => {
        let parentDir = '';
        if (selectedTreeNodes.size > 0) {
            const sel = Array.from(selectedTreeNodes)[0];
            parentDir = sel.endsWith('/') ? sel : sel.split('/').slice(0, -1).join('/') + (sel.includes('/') ? '/' : '');
        }

        const div = document.createElement('div');
        div.className = 'tree-item ps-4';
        div.innerHTML = `<i class="bi ${isDir ? 'bi-folder' : 'bi-file-earmark-code'} me-2 tree-icon"></i>`;
        
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'inline-edit-input form-control form-control-sm bg-dark text-white border-secondary p-0 px-1 custom-font';
        input.style.height = '20px';
        input.placeholder = isDir ? 'Folder Name' : 'File Name';
        div.appendChild(input);

        if (ui.fileTree.firstChild) ui.fileTree.insertBefore(div, ui.fileTree.firstChild);
        else ui.fileTree.appendChild(div);
        
        input.focus();

        const commit = () => {
            if (input.dataset.committed) return;
            input.dataset.committed = 'true';
            let newName = input.value.trim();
            if (newName) {
                const fullPath = parentDir + newName + (isDir ? '/' : '');
                if (vfs.some(f => f.path === fullPath)) {
                    showNotification(`Name '${newName}' already exists here!`, true);
                } else {
                    vfs.push({ path: fullPath, is_dir: isDir, content: '' });
                    if (isDir) expandedDirs.add(fullPath);
                    saveStateToHistory();
                    if (!isDir) openFile(fullPath);
                }
            }
            renderTree();
        };

        const checkDupe = () => {
            let val = input.value.trim();
            if(val && vfs.some(f => f.path === parentDir + val + (isDir ? '/' : ''))) input.style.borderColor = 'red';
            else input.style.borderColor = '';
        };

        input.addEventListener('input', checkDupe);
        input.addEventListener('blur', commit);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                if(input.style.borderColor === 'red') e.preventDefault();
                else commit();
            }
            if (e.key === 'Escape') { input.dataset.committed = 'true'; renderTree(); }
        });
    };

    const renamePath = (oldPath, newPath) => {
        vfs.forEach(f => {
            if (f.path === oldPath) f.path = newPath;
            else if (f.path.startsWith(oldPath)) f.path = f.path.replace(oldPath, newPath);
        });
        if (activeFilePath?.startsWith(oldPath)) {
            activeFilePath = activeFilePath.replace(oldPath, newPath);
            updateCurrentFilePathUI(activeFilePath);
        }
    };

    const bindEditEvents = () => {
        ui.codeInput.addEventListener('input', () => {
            if (activeFilePath) {
                const file = vfs.find(f => f.path === activeFilePath);
                if (file) {
                    file.content = ui.codeInput.value;
                    ui.charCount.textContent = `${ui.codeInput.value.length} characters`;
                    clearTimeout(typingTimer);
                    typingTimer = setTimeout(saveStateToHistory, 500);
                }
            }
        });

        ui.addFileBtn?.addEventListener('click', () => initiateCreateInline(false));
        ui.addFolderBtn?.addEventListener('click', () => initiateCreateInline(true));
        
        ui.fileTree.addEventListener('click', (e) => {
            if (!e.target.closest('.tree-item')) {
                selectedTreeNodes.clear();
                focusedIndex = -1;
                renderTree();
            }
        });
    };

    const bindGlobalEvents = () => {
        document.addEventListener('keydown', (e) => {
            const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0;
            const modifier = isMac ? e.metaKey : e.ctrlKey;
            
            if (modifier && (e.code === 'KeyZ' || e.key.toLowerCase() === 'z')) { e.preventDefault(); performUndo(); }
            if (modifier && (e.code === 'KeyY' || e.key.toLowerCase() === 'y')) { e.preventDefault(); performRedo(); }

            if (modifier && (e.code === 'KeyS' || e.key.toLowerCase() === 's')) {
                e.preventDefault();
                if(ui.downloadDropdownBtn) {
                    const bsDropdown = new bootstrap.Dropdown(ui.downloadDropdownBtn);
                    bsDropdown.show();
                }
            }

            if (!['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName) && vfs.length > 0) {
                if ((e.code === 'KeyA' || e.key.toLowerCase() === 'a') && modifier) {
                    e.preventDefault();
                    if (ui.githubPrompt && !ui.githubPrompt.classList.contains('d-none')) return;
                    vfs.forEach(f => selectedTreeNodes.add(f.path));
                    renderTree();
                }
                
                if (e.key === 'Delete' && !window.IS_READONLY && document.activeElement.tagName !== 'INPUT') {
                    e.preventDefault();
                    selectedTreeNodes.forEach(pathToDelete => {
                        vfs = vfs.filter(f => !f.path.startsWith(pathToDelete));
                        if (activeFilePath?.startsWith(pathToDelete)) showNoFile();
                    });
                    selectedTreeNodes.clear();
                    saveStateToHistory();
                    renderTree();
                }

                if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                    if (document.activeElement === ui.fileTree || ui.fileTree.contains(document.activeElement)) {
                        e.preventDefault();
                        const items = Array.from(ui.fileTree.querySelectorAll('.tree-item'));
                        if (items.length === 0) return;

                        let newIndex = focusedIndex;
                        if (e.key === 'ArrowDown') newIndex = Math.min(items.length - 1, focusedIndex + 1);
                        if (e.key === 'ArrowUp') newIndex = Math.max(0, focusedIndex - 1);

                        if (e.shiftKey) {
                            if (anchorIndex === -1) anchorIndex = focusedIndex === -1 ? 0 : focusedIndex;
                            const start = Math.min(anchorIndex, newIndex);
                            const end = Math.max(anchorIndex, newIndex);
                            selectedTreeNodes.clear();
                            for (let i = start; i <= end; i++) selectedTreeNodes.add(items[i].dataset.path);
                        } else {
                            anchorIndex = newIndex;
                            selectedTreeNodes.clear();
                            selectedTreeNodes.add(items[newIndex].dataset.path);
                        }
                        focusedIndex = newIndex;
                        renderTree();
                    }
                }
            }
        });

        document.addEventListener('click', (e) => {
            if (ui.githubPrompt && !ui.githubPrompt.classList.contains('d-none')) {
                if (!ui.githubPrompt.contains(e.target) && !ui.githubBtnToggle.contains(e.target)) {
                    ui.githubPrompt.classList.add('d-none');
                }
            }
        });

        if (!window.IS_READONLY) {
            const dragOverlay = document.createElement('div');
            dragOverlay.className = 'position-fixed top-0 start-0 w-100 h-100 d-none z-3';
            dragOverlay.style.background = 'rgba(0,255,0,0.1)';
            dragOverlay.style.border = '4px dashed lime';
            document.body.appendChild(dragOverlay);

            document.body.addEventListener('dragover', (e) => {
                if (e.dataTransfer.types.includes('Files')) { 
                    e.preventDefault(); 
                    dragOverlay.classList.remove('d-none'); 
                    clearTimeout(dragDebounceTimer);
                    dragDebounceTimer = setTimeout(() => dragOverlay.classList.add('d-none'), 150);
                }
            });
            document.body.addEventListener('drop', async (e) => {
                e.preventDefault();
                dragOverlay.classList.add('d-none');
                if (e.dataTransfer.types.includes('Files')) {
                    const items = e.dataTransfer.items;
                    const promises = [];
                    for (let i = 0; i < items.length; i++) {
                        const item = items[i].webkitGetAsEntry();
                        if (item) promises.push(traverseFileTree(item));
                    }
                    const results = await Promise.all(promises);
                    const entries = results.flat();
                    if (entries.length > 0) await processFiles(entries);
                }
            });

            ui.uploadFolderBtn?.addEventListener('click', () => ui.folderInput.click());
            ui.folderInput?.addEventListener('change', async (e) => {
                const entries = Array.from(e.target.files).map(f => ({ path: f.webkitRelativePath || f.name, is_dir: false, file: f }));
                await processFiles(entries);
                ui.folderInput.value = '';
            });

            ui.uploadFilesBtn?.addEventListener('click', () => ui.filesInput.click());
            ui.filesInput?.addEventListener('change', async (e) => {
                const entries = Array.from(e.target.files).map(f => ({ path: f.name, is_dir: false, file: f }));
                await processFiles(entries);
                ui.filesInput.value = '';
            });

            ui.uploadZipBtn?.addEventListener('click', () => ui.zipInput.click());
            ui.zipInput?.addEventListener('change', async (e) => {
                if (e.target.files.length > 0) await handleZipBlob(e.target.files[0]);
                ui.zipInput.value = '';
            });

            document.addEventListener('paste', async (e) => {
                if (document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'TEXTAREA') return;
                const items = e.clipboardData.items;
                const promises = [];
                for (let i = 0; i < items.length; i++) {
                    if (items[i].kind === 'file') {
                        const item = items[i].webkitGetAsEntry();
                        if (item) promises.push(traverseFileTree(item));
                    }
                }
                if (promises.length > 0) {
                    e.preventDefault();
                    const results = await Promise.all(promises);
                    const entries = results.flat();
                    if (entries.length > 0) await processFiles(entries);
                }
            });

            ui.githubBtnToggle?.addEventListener('click', (e) => {
                e.preventDefault(); e.stopPropagation();
                ui.githubPrompt.classList.toggle('d-none');
                if (!ui.githubPrompt.classList.contains('d-none')) {
                    ui.githubUrlInput.focus();
                }
            });

            const validateRepoUrl = () => {
                const parsed = parseRepoUrl(ui.githubUrlInput.value);
                if (parsed) {
                    ui.githubSubmitBtn.disabled = false;
                    ui.githubSubmitBtn.innerHTML = '<i class="bi bi-cloud-download"></i>';
                } else {
                    ui.githubSubmitBtn.disabled = true;
                    ui.githubSubmitBtn.innerHTML = '<i class="bi bi-x-circle text-danger"></i>';
                }
            };

            ui.githubUrlInput?.addEventListener('input', validateRepoUrl);
            ui.githubUrlInput?.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !ui.githubSubmitBtn.disabled) {
                    e.preventDefault();
                    ui.githubSubmitBtn.click();
                }
            });

            ui.githubSubmitBtn?.addEventListener('click', () => {
                const url = ui.githubUrlInput.value;
                const parsed = parseRepoUrl(url);
                if (parsed) {
                    ui.githubPrompt.classList.add('d-none');
                    ui.githubUrlInput.value = '';
                    validateRepoUrl();
                    fetchGithubZip(parsed.zipUrl, parsed.subpath);
                }
            });

            ui.publishBtn.addEventListener('click', async () => {
                if (vfs.length === 0) return showNotification('Repository is empty', true);
                if (ui.publishBtn.disabled) return;

                const originalHtml = ui.publishBtn.innerHTML;
                ui.publishBtn.innerHTML = '<i class="bi bi-arrow-repeat spin"></i>';
                ui.publishBtn.disabled = true;

                try {
                    const res = await fetch('/toadcode/api/save', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ id: crypto.randomUUID(), files: vfs })
                    });
                    if (!res.ok) throw new Error('Save failed');
                    const data = await res.json();
                    localStorage.removeItem('toadcode_vfs');
                    window.location.href = `/toadcode/${data.id}`;
                } catch(e) {
                    showNotification('Database is busy :(', true);
                    ui.publishBtn.innerHTML = originalHtml;
                    ui.publishBtn.disabled = false;
                }
            });
        } else {
            ui.forkBtn?.addEventListener('click', () => {
                localStorage.setItem('toadcode_vfs', JSON.stringify(vfs));
                window.location.href = '/toadcode/';
            });
        }

        ui.toggleSidebarBtn?.addEventListener('click', () => {
            ui.sidebar.classList.toggle('collapsed');
            if (ui.sidebar.classList.contains('collapsed')) ui.resizer.classList.add('d-none');
            else ui.resizer.classList.remove('d-none');
        });

        ui.uuidDisplay?.addEventListener('click', () => {
            const url = window.location.origin + window.location.pathname;
            navigator.clipboard.writeText(url).then(() => {
                const origHtml = ui.uuidDisplay.innerHTML;
                ui.uuidDisplay.innerHTML = '<i class="bi bi-check2 text-success"></i> Copied!';
                setTimeout(() => ui.uuidDisplay.innerHTML = origHtml, 2000);
            });
        });

        ui.downloadZip.addEventListener('click', e => { e.preventDefault(); downloadZip(); });
        ui.downloadMd.addEventListener('click', e => { e.preventDefault(); downloadMd(); });
        ui.downloadCurrentFileBtn.addEventListener('click', () => {
            if(activeFilePath) {
                const file = vfs.find(f => f.path === activeFilePath);
                if(file) {
                    const blob = new Blob([file.content], { type: 'text/plain' });
                    triggerDownload(blob, activeFilePath.split('/').pop());
                }
            }
        });
    };

    const bindResizer = () => {
        let isResizing = false;
        ui.resizer.addEventListener('mousedown', (e) => {
            isResizing = true;
            document.body.style.cursor = 'ew-resize';
            ui.sidebar.style.transition = 'none'; 
            e.preventDefault();
        });
        document.addEventListener('mousemove', (e) => {
            if (!isResizing) return;
            const newWidth = document.body.clientWidth - e.clientX - 10;
            if (newWidth > 150 && newWidth < document.body.clientWidth * 0.8) {
                ui.sidebar.style.setProperty('--sidebar-width', `${newWidth}px`);
            }
        });
        document.addEventListener('mouseup', () => {
            if (isResizing) {
                isResizing = false;
                document.body.style.cursor = 'default';
                ui.sidebar.style.transition = '';
            }
        });
    };

    const fetchGithubZip = async (zipUrl, subpath) => {
        showNotification("Fetching remote repository...");
        try {
            const res = await fetch(`/toadcode/api/proxy-zip?url=${encodeURIComponent(zipUrl)}`);
            if (!res.ok) throw new Error();
            const blob = await res.blob();
            await handleZipBlob(blob, subpath);
            showNotification("Repository loaded successfully!");
        } catch (e) {
            showNotification("Failed to fetch repository. Ensure the URL is valid and public.", true);
        }
    };

    const openFile = (path) => {
        const file = vfs.find(f => f.path === path);
        if (file && !file.is_dir) {
            activeFilePath = path;
            ui.noFileScreen.style.display = 'none';
            ui.codeInput.value = file.content;
            ui.codeInput.classList.remove('d-none');
            updateCurrentFilePathUI(path);
            ui.charCount.textContent = `${file.content.length} characters`;
            ui.codeInput.dispatchEvent(new Event('input')); 
            
            Array.from(ui.fileTree.querySelectorAll('.tree-item')).forEach(i => {
                i.classList.toggle('active', i.dataset.path === path && !i.dataset.isdir);
            });
        }
    };

    const checkTotalSize = () => {
        if (window.IS_READONLY) return;
        const size = new Blob([JSON.stringify(vfs)]).size;
        const mb = (size / 1024 / 1024);
        const pct = Math.min((mb / 10) * 100, 100);
        
        if (ui.repoSizeText && ui.repoSizeProgress) {
            ui.repoSizeText.textContent = mb.toFixed(2);
            ui.repoSizeProgress.style.width = pct + '%';
            ui.repoSizeProgress.className = `progress-bar ${pct > 90 ? 'bg-danger' : 'bg-success'}`;
        }
        
        ui.publishBtn.classList.toggle('btn-danger', size > maxRepoSize);
        ui.publishBtn.disabled = size > maxRepoSize;
    };

    const showNotification = (msg, isError = false) => {
        const notif = document.createElement('div');
        notif.className = `notification ${isError ? 'text-danger border-danger' : 'text-white border-secondary'} dropdown-menu-transparent show border custom-font`;
        notif.style.cssText = 'position:fixed; top:20px; right:20px; padding:12px 24px; border-radius:8px; z-index:9999; opacity:0; transition:opacity 0.3s; pointer-events: none;';
        notif.textContent = msg;
        document.body.appendChild(notif);
        setTimeout(() => notif.style.opacity = '1', 10);
        setTimeout(() => {
            notif.style.opacity = '0';
            setTimeout(() => notif.remove(), 300);
        }, 3000);
    };

    const downloadZip = async () => {
        if (!window.JSZip || vfs.length === 0) return;
        const zip = new JSZip();
        vfs.forEach(f => {
            if (f.is_dir) zip.folder(f.path);
            else zip.file(f.path, f.content);
        });
        const blob = await zip.generateAsync({ type: 'blob' });
        triggerDownload(blob, `toadcode-${window.CODE_ID || 'repo'}.zip`);
    };

    const generateAsciiTree = () => {
        const root = {};
        vfs.forEach(f => {
            const parts = f.path.split('/').filter(Boolean);
            let current = root;
            parts.forEach((p, i) => {
                if (!current[p]) current[p] = (i === parts.length - 1 && !f.is_dir) ? null : {};
                current = current[p];
            });
        });

        let out = '';
        const printTree = (node, prefix = '') => {
            const keys = Object.keys(node).sort();
            keys.forEach((key, index) => {
                const isLast = index === keys.length - 1;
                out += prefix + (isLast ? '└── ' : '├── ') + key + '\n';
                if (node[key]) printTree(node[key], prefix + (isLast ? '    ' : '│   '));
            });
        };
        printTree(root);
        return out;
    };

    const downloadMd = () => {
        if (vfs.length === 0) return;
        let md = `# Toadcode Repository: ${window.CODE_ID || 'Local'}\n\n## Structure\n\`\`\`\n`;
        md += generateAsciiTree();
        md += `\`\`\`\n\n## Files\n\n`;
        
        vfs.filter(f => !f.is_dir).sort((a,b) => a.path.localeCompare(b.path)).forEach(f => {
            const ext = f.path.split('.').pop() || 'txt';
            md += `### ${f.path}\n\`\`\`${ext}\n${f.content}\n\`\`\`\n\n`;
        });
        
        const blob = new Blob([md], { type: 'text/markdown' });
        triggerDownload(blob, `toadcode-${window.CODE_ID || 'repo'}.md`);
    };

    const triggerDownload = (blob, filename) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = filename; a.click();
        URL.revokeObjectURL(url);
    };

    document.addEventListener('DOMContentLoaded', init);
})();