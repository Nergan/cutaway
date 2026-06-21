// ---------- THEME MANAGEMENT ----------
const themeToggleBtn = document.getElementById('themeToggle');
const themeIcon = themeToggleBtn.querySelector('i');
let currentTheme = localStorage.getItem('dnd_theme') || 'dark';

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  if(theme === 'dark') {
    themeIcon.className = 'bi bi-sun-fill';
  } else {
    themeIcon.className = 'bi bi-moon-stars-fill';
  }
}

applyTheme(currentTheme);

themeToggleBtn.addEventListener('click', () => {
  currentTheme = currentTheme === 'dark' ? 'light' : 'dark';
  localStorage.setItem('dnd_theme', currentTheme);
  applyTheme(currentTheme);
});

// ---------- DATA LOGIC ----------
const fileInput = document.getElementById('file-input');
const dropZone = document.getElementById('drop-zone');

fileInput.addEventListener('change', (e) => handleFiles(e.target.files));
dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', (e) => { e.preventDefault(); dropZone.classList.remove('dragover'); });
dropZone.addEventListener('drop', (e) => { e.preventDefault(); dropZone.classList.remove('dragover'); handleFiles(e.dataTransfer.files); });

function handleFiles(files) {
  if (!files.length) return;
  const file = files[0];
  if (!file.name.endsWith('.json')) {
    alert('Please select a valid .json parchment.');
    return;
  }

  const reader = new FileReader();
  reader.onload = (e) => {
    try {
      const data = JSON.parse(e.target.result);
      renderCharacterSheet(data);
    } catch (err) {
      alert('Error interpreting the runes. Ensure it is a valid Foundry VTT actor file.');
      console.error(err);
    }
  };
  reader.readAsText(file);
}

function resetViewer() {
  document.getElementById('character-sheet').style.display = 'none';
  document.getElementById('upload-section').style.display = 'block';
  fileInput.value = "";
}

function showTab(tabId) {
  document.querySelectorAll('.tab-content').forEach(el => el.style.display = 'none');
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + tabId).style.display = 'block';
  document.getElementById('btn-' + tabId).classList.add('active');
}

function getModifier(score) {
  const mod = Math.floor((score - 10) / 2);
  return mod >= 0 ? `+${mod}` : `${mod}`;
}

function processFoundryText(text) {
  if (!text) return "";
  text = text.replace(/\[\[\/(?:r|roll)\s+([^\]]+)\]\]/gi, "<span class='foundry-roll'>$1</span>");
  
  text = text.replace(/(?:@|&amp;|&)[a-zA-Z0-9_]+\[([^\]]+)\](?:\{([^\}]+)\})?/g, (match, bracketContent, braceContent) => {
    if (braceContent) return `<span class='foundry-ref'>${braceContent}</span>`;
    if (bracketContent.includes('.') || bracketContent.length > 20) return '';
    return `<span class='foundry-ref'>${bracketContent}</span>`;
  });
  return text;
}

function renderCharacterSheet(data) {
  document.getElementById('upload-section').style.display = 'none';
  document.getElementById('character-sheet').style.display = 'block';
  showTab('core'); 

  document.getElementById('char-name').textContent = data.name || "Unnamed Wanderer";
  const imgEl = document.getElementById('char-img');
  if (data.img) {
    imgEl.src = data.img;
    imgEl.style.display = 'block';
  } else {
    imgEl.style.display = 'none';
  }

  let cls =[], race = "Unknown Form", bg = "Unknown Path";
  let featuresHtml = "", inventoryHtml = "", spellsHtml = "";
  const items = data.items ||[];
  
  items.forEach(item => {
    if (item.type === 'class') {
      const level = item.system?.levels || 1;
      cls.push(`${item.name} (Lvl ${level})`);
    } else if (item.type === 'race') {
      race = item.name;
    } else if (item.type === 'background') {
      bg = item.name;
    } 
    
    let descRaw = item.system?.description?.value || "No records provided in the archives.";
    let desc = processFoundryText(descRaw);
    const qty = item.system?.quantity ? `<span class="foundry-ref">[${item.system.quantity}x]</span> ` : "";
    
    const detailsBlock = `
      <details>
        <summary>${qty}${item.name}</summary>
        <div class="item-desc">${desc}</div>
      </details>
    `;

    if (item.type === 'spell') {
      spellsHtml += detailsBlock;
    } else if (['feat', 'classfeature', 'subclass', 'background', 'race'].includes(item.type)) {
      featuresHtml += detailsBlock;
    } else if (['weapon', 'equipment', 'consumable', 'loot', 'container', 'tool'].includes(item.type)) {
      inventoryHtml += detailsBlock;
    }
  });

  const classStr = cls.length > 0 ? cls.join(", ") : "Unknown Class";
  document.getElementById('char-subtitle').textContent = `${classStr} | ${race} | ${bg}`;
  document.getElementById('list-features').innerHTML = featuresHtml || "<p>The winds carry no features for this one.</p>";
  document.getElementById('list-spells').innerHTML = spellsHtml || "<p>No magical affinities found.</p>";
  document.getElementById('list-inventory').innerHTML = inventoryHtml || "<p>The traveler carries no worldly burdens.</p>";

  const attrs = data.system?.attributes || {};
  const ac = attrs.ac?.value || attrs.ac?.flat || attrs.ac?.calc || "10";
  document.getElementById('stat-ac').textContent = ac;

  const hpVal = attrs.hp?.value !== null ? attrs.hp?.value : 0;
  const hpMax = attrs.hp?.max !== null ? attrs.hp?.max : hpVal;
  document.getElementById('stat-hp').textContent = `${hpVal} / ${hpMax}`;

  const speed = attrs.movement?.walk || attrs.movement?.value || "30";
  document.getElementById('stat-speed').textContent = `${speed} ft`;

  const abs = ['str', 'dex', 'con', 'int', 'wis', 'cha'];
  let attrHtml = "";
  abs.forEach(ab => {
    const score = data.system?.abilities?.[ab]?.value || 10;
    const mod = getModifier(score);
    attrHtml += `
      <td>
        <div class="attr-score">${score}</div>
        <div class="attr-mod">${mod}</div>
      </td>`;
  });
  document.getElementById('attr-row').innerHTML = attrHtml;

  let bioRaw = data.system?.details?.biography?.value || "The story of this spirit is yet to be written...";
  let bioText = processFoundryText(bioRaw);
  document.getElementById('char-bio').innerHTML = bioText;
}