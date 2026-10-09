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

themeToggleBtn.addEventListener('click', (e) => {
  e.stopPropagation();
  currentTheme = currentTheme === 'dark' ? 'light' : 'dark';
  localStorage.setItem('dnd_theme', currentTheme);
  applyTheme(currentTheme);
});

// ---------- DATA AND LOGIC ----------
const UI = {
  ru: {
    title: "Бестиарий", catAll: "Все существа", catFam: "Фамильяры",
    catLvl2: "Облик: Уровень 2", descLvl2: "До 1/4 ПО (Суша)",
    catLvl4: "Облик: Уровень 4", descLvl4: "До 1/2 ПО (+ Плавание)",
    catLvl8: "Облик: Уровень 8", descLvl8: "До 1 ПО (+ Полёт)",
    search: "Поиск, фильтры и сортировка...",
    loading: "Чтение свитков (Загрузка базы данных)...",
    noRes: "По вашим фильтрам звери не найдены. 🍂",
    hintTitle: "Подсказки",
    hintSort: "<strong>Сортировка:</strong> скрытность, восприятие, скорость, урон, хп, кд, сил, лвк, тел, чувства (слепое, тёмное и т.д.).",
    hintFilter: "<strong>Фильтры:</strong> особенный, рой, яд, сбить, ездовое, захват, паутина, язык, иммунитет, чувства. <br><strong>Исключение:</strong> минус перед словом (напр. <i>-паук</i>).",
    hintSize: "<strong>Размер:</strong> крошечный, маленький, средний, большой, огромный, гигантский.",
    hintHab: "<strong>Местность:</strong> лес, луг, холмы, болото, горы, арктика, вода, берег, город, подземелье, пустыня, джунгли, космос.",
    hintNote: "* Неполное слово тоже считается: «скорос» сортирует как «скорость», «скрыт» как скрытность. Карточка подписана источником (SRD или книга, либо Homebrew). Числа существ SRD сверены с System Reference Document 5.1 (CC BY 4.0, Wizards of the Coast).",
    statAc: "КД", statHp: "ХП", statSt: "Скрыт.", statPr: "Воспр.", statDm: "Ср. Урон",
    statStr: "СИЛ", statDex: "ЛВК", statCon: "ТЕЛ",
    lblSenses: "Чувства", beast: "зверь",
    spWalk: "Ходьба", spFly: "Полёт", spSwim: "Плавание", spClimb: "Лазание", spBurrow: "Копание"
  },
  en: {
    title: "Bestiary", catAll: "All Creatures", catFam: "Familiars",
    catLvl2: "Wild Shape: Lvl 2", descLvl2: "Max CR 1/4 (Land)",
    catLvl4: "Wild Shape: Lvl 4", descLvl4: "Max CR 1/2 (+ Swim)",
    catLvl8: "Wild Shape: Lvl 8", descLvl8: "Max CR 1 (+ Fly)",
    search: "Search, filters and sorting...",
    loading: "Reading scrolls (Loading database)...",
    noRes: "No beasts found with these filters. 🍂",
    hintTitle: "Hints",
    hintSort: "<strong>Sort by:</strong> stealth, perception, speed, damage, hp, ac, str, dex, con, senses (blindsight, darkvision, etc.).",
    hintFilter: "<strong>Filters:</strong> special, swarm, poison, prone, mount, grapple, web, language, immunity, senses. <br><strong>Exclude:</strong> minus before word (e.g. <i>-spider</i>).",
    hintSize: "<strong>Size:</strong> tiny, small, medium, large, huge, gargantuan.",
    hintHab: "<strong>Habitat:</strong> forest, grassland, hills, swamp, mountain, arctic, water, coast, urban, underdark, desert, jungle, space.",
    hintNote: "* A short word still counts: \"stealt\" sorts as stealth, \"скорос\" as speed. Each card names its source (SRD, a book, or Homebrew). SRD numbers follow the System Reference Document 5.1 (CC BY 4.0, Wizards of the Coast).",
    statAc: "AC", statHp: "HP", statSt: "Stealth", statPr: "Perc.", statDm: "Avg. Dmg",
    statStr: "STR", statDex: "DEX", statCon: "CON",
    lblSenses: "Senses", beast: "beast",
    spWalk: "Walk", spFly: "Fly", spSwim: "Swim", spClimb: "Climb", spBurrow: "Burrow"
  }
};

const SYNONYMS = {
  ru: {
    'кошка': ['кот', 'котик', 'кошка', 'кошачий', 'кошачья', 'львица', 'тигрица'],
    'собака': ['пес', 'пёс', 'собака', 'собачка', 'щенок'],
    'лошадь': ['конь', 'лошадь', 'скакун', 'жеребец', 'кобыла', 'пони'],
    'вьючное': ['грузоподъемность', 'груз', 'нести', 'вьючное', 'вьючный', 'вьючные'],
    'ездовое': ['маунт', 'верхом', 'седло', 'кататься', 'ездовой', 'ездовое', 'верховое', 'верховая'],
    'яд': ['яд', 'отрава', 'токсин', 'отравлен', 'ядом', 'отравление'],
    'сбить': ['сбить', 'ног', 'упасть', 'опрокинуть', 'таран', 'сбивает'],
    'захват': ['захват', 'схватить', 'удержать', 'опутать', 'опутан', 'схвачен'],
    'паутина': ['паутина', 'паутину', 'паутине', 'паучь', 'web'],
    'язык': ['язык', 'говорит', 'понимает', 'речь'],
    'сопротивление': ['иммунитет', 'сопротивление', 'невосприимчивость', 'устойчивость', 'резист'],
    'особенный': ['особенный', 'уникальный', 'специфичный', 'магия', 'магический'],
    'рой': ['рой', 'рои', 'стая']
  },
  en: {
    'cat': ['cat', 'kitty', 'feline', 'tomcat'],
    'dog': ['dog', 'hound', 'canine', 'pup'],
    'horse': ['horse', 'steed', 'stallion', 'mare', 'pony'],
    'pack': ['carrying capacity', 'carry', 'burden', 'pack'],
    'mount': ['riding', 'saddle', 'ride', 'mount', 'steed'],
    'poison': ['toxin', 'poisoned', 'venom', 'poison'],
    'prone': ['knock', 'fall', 'ram', 'prone'],
    'grapple': ['grab', 'hold', 'restrain', 'grapple'],
    'web': ['web', 'spider web', 'webs'],
    'language': ['speak', 'understand', 'speech', 'language'],
    'immunity': ['resistance', 'immune', 'resist', 'immunity'],
    'special': ['unique', 'specific', 'magic', 'magical', 'special'],
    'swarm': ['flock', 'school', 'swarm']
  }
};

let currentLang = localStorage.getItem('wildwood_lang') || 'ru';
let db = [];
let currentCat = 'all';
let lastNumCols = 0;

const gridEl = document.getElementById('grid');
const searchInput = document.getElementById('searchInput');
const clearBtn = document.getElementById('clearSearch');
const sidebar = document.getElementById('sidebar');
const navBtns = document.querySelectorAll('.nav-btn');
const langBtn = document.getElementById('langBtn');
const hintBtn = document.getElementById('hintBtn');
const hintPopup = document.getElementById('hintPopup');

langBtn.textContent = currentLang === 'ru' ? 'en' : 'ru';

function setSidebarInitialState() {
  const isMobile = window.innerWidth <= 850;
  if (isMobile) sidebar.classList.add('collapsed');
  else sidebar.classList.remove('collapsed');
}

setSidebarInitialState();
window.addEventListener('resize', () => {
  setSidebarInitialState();
  if (window.innerWidth <= 850) {
    if (!mobileOverlay) createMobileOverlay();
    updateMobileOverlay();
  } else {
    if (mobileOverlay) mobileOverlay.remove();
    mobileOverlay = null;
  }

  if (db.length > 0) {
    const containerWidth = gridEl.clientWidth;
    let numCols = Math.floor((containerWidth + 24) / (280 + 24));
    if (numCols < 1) numCols = 1;
    if (numCols !== lastNumCols) {
      processQuery();
    }
  }
});

let mobileOverlay = null;
function createMobileOverlay() {
  if (mobileOverlay) return;
  mobileOverlay = document.createElement('div');
  mobileOverlay.className = 'mobile-overlay';
  document.body.appendChild(mobileOverlay);
  mobileOverlay.addEventListener('click', () => {
    if (sidebar && !sidebar.classList.contains('collapsed')) {
      sidebar.classList.add('collapsed');
      updateMobileOverlay();
    }
  });
}
function updateMobileOverlay() {
  if (!mobileOverlay) return;
  if (!sidebar.classList.contains('collapsed')) mobileOverlay.classList.add('active');
  else mobileOverlay.classList.remove('active');
}

hintBtn.addEventListener('click', () => hintPopup.classList.toggle('active'));

sidebar.addEventListener('click', (e) => {
  if (e.target.closest('.nav-btn') || e.target.closest('.control-btn')) return;
  if (window.innerWidth <= 850) {
    sidebar.classList.toggle('collapsed');
    updateMobileOverlay();
  } else {
    sidebar.classList.toggle('collapsed');
  }
});

navBtns.forEach(btn => {
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    navBtns.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentCat = btn.dataset.cat;
    processQuery();
  });
});

langBtn.addEventListener('click', () => {
  currentLang = currentLang === 'ru' ? 'en' : 'ru';
  localStorage.setItem('wildwood_lang', currentLang);
  langBtn.textContent = currentLang === 'ru' ? 'en' : 'ru';
  updateUILang();
  processQuery();
});

searchInput.addEventListener('input', () => {
  clearBtn.style.display = searchInput.value ? 'block' : 'none';
  processQuery();
});

clearBtn.addEventListener('click', () => {
  searchInput.value = '';
  clearBtn.style.display = 'none';
  processQuery();
});

document.addEventListener('click', (e) => {
  if (window.innerWidth <= 850 && !sidebar.classList.contains('collapsed')) {
    if (!sidebar.contains(e.target)) {
      sidebar.classList.add('collapsed');
      updateMobileOverlay();
    }
  }
});

function updateUILang() {
  const texts = UI[currentLang];
  document.getElementById('ui-title').textContent = texts.title;
  document.getElementById('ui-cat-all').textContent = texts.catAll;
  document.getElementById('ui-cat-fam').textContent = texts.catFam;
  document.getElementById('ui-cat-lvl2').textContent = texts.catLvl2;
  document.getElementById('ui-desc-lvl2').textContent = texts.descLvl2;
  document.getElementById('ui-cat-lvl4').textContent = texts.catLvl4;
  document.getElementById('ui-desc-lvl4').textContent = texts.descLvl4;
  document.getElementById('ui-cat-lvl8').textContent = texts.catLvl8;
  document.getElementById('ui-desc-lvl8').textContent = texts.descLvl8;
  searchInput.placeholder = texts.search;
  document.getElementById('ui-hint-title').textContent = texts.hintTitle;
  document.getElementById('ui-hint-sort').innerHTML = texts.hintSort;
  document.getElementById('ui-hint-filter').innerHTML = texts.hintFilter;
  document.getElementById('ui-hint-size').innerHTML = texts.hintSize;
  document.getElementById('ui-hint-hab').innerHTML = texts.hintHab;
  document.getElementById('ui-hint-note').innerHTML = texts.hintNote;
  if (!db.length) document.getElementById('ui-loading').textContent = texts.loading;
}

function loadDatabase() {
  const timestamp = Date.now();
  fetch(`/dnd/static/db.json?nocache=${timestamp}`)
    .then(res => res.json())
    .then(data => { db = data; processQuery(); })
    .catch(err => {
      gridEl.innerHTML = `<div class="no-results" style="color:var(--speed-slow);">Не удалось загрузить db.json. Откройте файл через локальный сервер. / Failed to load db.json. Please use a local server.</div>`;
    });
}

function normalize(str) { return str.replace(/ё/g, 'е').toLowerCase(); }

function formatSpeed(sp) {
  sp = sp || {};
  const texts = UI[currentLang];
  const fmt = (lbl, val) => `<span class="${val > 0 && val < 30 ? 'speed-slow' : ''}"><strong>${lbl}</strong> ${val} ft.</span>`;
  let parts = [];
  if (sp.w) parts.push(fmt(texts.spWalk, sp.w));
  if (sp.f) parts.push(fmt(texts.spFly, sp.f));
  if (sp.s) parts.push(fmt(texts.spSwim, sp.s));
  if (sp.c) parts.push(fmt(texts.spClimb, sp.c));
  if (sp.b) parts.push(fmt(texts.spBurrow, sp.b));
  return parts.join(' • ');
}

const fmtMod = (val) => {
  if (val === undefined || val === null) return '--';
  return val > 0 ? '+' + val : val;
};

function getSenseDistance(creature, senseType) {
  let sensesStr = (creature.sn_ru || []).concat(creature.sn_en || []).join(' ').toLowerCase();
  let regex;
  if (senseType === 'blind') regex = /(?:blind|слепо)[^\d]*(\d+)/i;
  else if (senseType === 'dark') regex = /(?:dark|т[её]мн)[^\d]*(\d+)/i;
  else if (senseType === 'tremor') regex = /(?:tremor|вибрац)[^\d]*(\d+)/i;
  else if (senseType === 'true') regex = /(?:true|истин)[^\d]*(\d+)/i;

  if (!regex) return -1;
  let match = sensesStr.match(regex);
  return match ? parseInt(match[1]) : -1;
}

function getStatValue(c, key) {
  const speed = c.sp || {};
  if (key === 'speed') return Math.max(speed.w||0, speed.f||0, speed.s||0, speed.c||0, speed.b||0);
  if (key.startsWith('sp_')) return speed[key.split('_')[1]] || 0;
  if (key.startsWith('sn_') && key !== 'sn_any') {
    let dist = getSenseDistance(c, key.split('_')[1]);
    return dist > 0 ? dist : 0;
  }
  if (key === 'sn_any') {
    let sru = c.sn_ru || []; let sen = c.sn_en || [];
    return (sru.length > 0 || sen.length > 0) ? 1 : 0;
  }
  let v = c[key];
  return (typeof v === 'number') ? v : (parseInt(v) || 0);
}

let activeSortKeys = [];

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, ch => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"
  }[ch]));
}

function processQuery() {
  if (!db.length) return;
  const query = DruidQuery.classifyQuery(searchInput.value);
  let filterWords = query.filters;
  let negativeWords = query.negative;
  activeSortKeys = query.sort.slice();

  let filtered = db.filter(c => {
    if (currentCat !== 'all' && !DruidQuery.categoriesFor(c).includes(currentCat)) return false;
    
    let cName = currentLang === 'ru' ? c.n_ru : c.n_en;
    let cSz = currentLang === 'ru' ? c.sz_ru : c.sz_en;
    let cTg = (currentLang === 'ru' ? c.tg_ru : c.tg_en) || [];
    let cHb = (currentLang === 'ru' ? c.hb_ru : c.hb_en) || [];
    let searchableText = normalize([
      cName, c.n_en, cSz, c.cr, c.src, c.src_ru,
      cTg.join(" "), cHb.join(" "),
      (c.sn_ru || []).join(" "), (c.sn_en || []).join(" ")
    ].join(" "));
    
    const speed = c.sp || {};
    if (speed.w) searchableText += " walk ходьба ходьбу";
    if (speed.f) searchableText += " fly полет полёт flyby";
    if (speed.s) searchableText += " swim плавание";
    if (speed.c) searchableText += " climb лазание";
    if (speed.b) searchableText += " burrow копание";

    if ((c.sn_ru && c.sn_ru.length > 0) || (c.sn_en && c.sn_en.length > 0)) {
        searchableText += " чувства senses зрение vision sight";
    }

    const synDict = SYNONYMS[currentLang];
    for (let [key, synArray] of Object.entries(synDict)) {
      if (synArray.some(s => searchableText.includes(s))) {
        searchableText += " " + key + " " + synArray.join(" ");
      }
    }

    for (let nw of negativeWords) {
        if (searchableText.includes(nw)) return false;
    }
    
    for (let w of filterWords) {
      if (!searchableText.includes(w)) return false;
    }
    
    return true;
  });

  if (activeSortKeys.length > 0) {
    // Phase 1: Calculate global Min/Max for active stats to normalize scores
    let statsData = {};
    activeSortKeys.forEach(key => {
      let min = Infinity;
      let max = -Infinity;
      filtered.forEach(c => {
        let val = getStatValue(c, key);
        if (val < min) min = val;
        if (val > max) max = val;
        
        if (!c._sortVals) c._sortVals = {};
        c._sortVals[key] = val;
      });
      statsData[key] = { min, max };
    });

    // Phase 2: Calculate total multi-variate score and sort descending
    filtered.sort((a, b) => {
      let scoreA = 0;
      let scoreB = 0;
      
      activeSortKeys.forEach(key => {
        let sd = statsData[key];
        let range = sd.max - sd.min;
        
        if (range > 0) {
          scoreA += (a._sortVals[key] - sd.min) / range;
          scoreB += (b._sortVals[key] - sd.min) / range;
        }
      });
      
      if (Math.abs(scoreA - scoreB) > 0.0001) {
        return scoreB - scoreA;
      }
      
      // Tie Breaker (Alphabetical)
      let nA = currentLang === 'ru' ? a.n_ru : a.n_en;
      let nB = currentLang === 'ru' ? b.n_ru : b.n_en;
      return nA.localeCompare(nB);
    });
  } else {
    // Default Alphabetical Sort
    filtered.sort((a, b) => {
      let nA = currentLang === 'ru' ? a.n_ru : a.n_en;
      let nB = currentLang === 'ru' ? b.n_ru : b.n_en;
      return nA.localeCompare(nB);
    });
  }
  
  renderData(filtered);
}

function renderData(data) {
  gridEl.innerHTML = '';
  if (data.length === 0) {
    gridEl.innerHTML = `<div class="no-results">${UI[currentLang].noRes}</div>`;
    return;
  }
  
  const containerWidth = gridEl.clientWidth;
  let numCols = Math.floor((containerWidth + 24) / (280 + 24));
  if (numCols < 1) numCols = 1;
  lastNumCols = numCols;

  let columns = [];
  for(let i=0; i<numCols; i++) {
    let col = document.createElement('div');
    col.style.display = 'flex';
    col.style.flexDirection = 'column';
    col.style.gap = '1.5rem';
    col.style.flex = '1';
    col.style.minWidth = '280px';
    columns.push(col);
    gridEl.appendChild(col);
  }

  const texts = UI[currentLang];
  const hl = (key) => {
      if (activeSortKeys.includes(key)) return 'sort-highlight';
      if (activeSortKeys.some(k => k.startsWith('sp_')) && key === 'speed') return 'sort-highlight';
      return '';
  };
  const hlSenses = activeSortKeys.some(k => k.startsWith('sn_')) ? 'sort-highlight' : '';

  data.forEach((c, index) => {
    let cName = currentLang === 'ru' ? c.n_ru : c.n_en;
    let cSz = currentLang === 'ru' ? c.sz_ru : c.sz_en;
    let cTg = (currentLang === 'ru' ? c.tg_ru : c.tg_en) || [];
    let cHb = (currentLang === 'ru' ? c.hb_ru : c.hb_en) || [];
    let cSn = currentLang === 'ru' ? (c.sn_ru || []) : (c.sn_en || []);
    
    let tagsHTML = cTg.map(t => `<div class="tag ${(t.includes('Особенный') || t.includes('Special')) ? 'special' : ''}">${esc(t)}</div>`).join('');
    let habHTML = cHb.length ? `<div class="tag habitat">${esc(cHb.join(', '))}</div>` : '';
    let sourceName = currentLang === 'ru' ? (c.src_ru || c.src || '') : (c.src || '');
    let sourceHTML = sourceName ? `<div class="tag source">${esc(sourceName)}</div>` : '';
    let crLabel = currentLang === 'ru' ? 'ПО' : 'CR';
    
    let sensesBlock = cSn.length > 0 ? `<div class="senses-block ${hlSenses}"><strong>${texts.lblSenses}:</strong> ${esc(cSn.join(', '))}</div>` : '';

    let cardHTML = `
      <div class="card">
        <div class="card-header">
          <div><div class="name">${esc(cName)}</div><div class="en-name">${esc(c.n_en)}</div></div>
          <div class="cr-badge">${crLabel} ${esc(c.cr)}</div>
        </div>
        <div class="basic-info">${esc(cSz)} ${texts.beast}</div>
        
        <div class="stat-row">
          <div class="stat-box ${hl('hp')}"><span>${texts.statHp}:</span> <strong>${c.hp}</strong></div>
          <div class="stat-box ${hl('ac')}"><span>${texts.statAc}:</span> <strong>${c.ac}</strong></div>
          <div class="stat-box ${hl('dm')}"><span>${texts.statDm}:</span> <strong>${c.dm}</strong></div>
        </div>

        <div class="stat-row">
          <div class="stat-box ${hl('str')}"><span>${texts.statStr}:</span> <strong>${fmtMod(c.str)}</strong></div>
          <div class="stat-box ${hl('dex')}"><span>${texts.statDex}:</span> <strong>${fmtMod(c.dex)}</strong></div>
          <div class="stat-box ${hl('con')}"><span>${texts.statCon}:</span> <strong>${fmtMod(c.con)}</strong></div>
        </div>

        <div class="stat-row-2">
          <div class="stat-box ${hl('st')}"><span>${texts.statSt}:</span> <strong>${fmtMod(c.st)}</strong></div>
          <div class="stat-box ${hl('pr')}"><span>${texts.statPr}:</span> <strong>${fmtMod(c.pr)}</strong></div>
        </div>
        
        <div class="speeds ${hl('speed')}">${formatSpeed(c.sp)}</div>
        
        ${sensesBlock}

        <div class="tags">${sourceHTML}${habHTML}${tagsHTML}</div>
      </div>
    `;
    
    columns[index % numCols].insertAdjacentHTML('beforeend', cardHTML);
  });
}

updateUILang();
if (window.innerWidth <= 850) createMobileOverlay();
loadDatabase();