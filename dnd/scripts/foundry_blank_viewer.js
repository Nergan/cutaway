// ---------- THEME MANAGEMENT ----------
const themeToggleBtn = document.getElementById('themeToggle');
const themeIcon = themeToggleBtn.querySelector('i');
let currentTheme = localStorage.getItem('dnd_theme') || 'dark';

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  themeIcon.className = theme === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-stars-fill';
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
const actor = window.FoundryActor;
let currentActors = [];
let currentIndex = 0;

fileInput.addEventListener('change', (e) => handleFiles(e.target.files));
dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', (e) => { e.preventDefault(); dropZone.classList.remove('dragover'); });
dropZone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropZone.classList.remove('dragover');
  handleFiles(e.dataTransfer.files);
});

document.getElementById('character-sheet').addEventListener('click', (event) => {
  const button = event.target.closest('.foundry-roll');
  if (!button) return;
  const formula = button.dataset.formula || '';
  const resolved = actor.resolveFormula(formula, currentActors[currentIndex]?.context || {});
  const rolled = actor.rollFormula(resolved);
  const note = button.nextElementSibling && button.nextElementSibling.classList.contains('roll-result')
    ? button.nextElementSibling
    : null;
  const target = note || document.createElement('span');
  target.className = 'roll-result';
  if (!rolled) {
    target.textContent = resolved === formula ? '' : ' ' + resolved;
  } else {
    target.textContent = ' ' + rolled.total + ' (' + rolled.detail + ')';
  }
  if (!note) button.after(target);
});

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
      const text = String(e.target.result || '').replace(/^\uFEFF/, '');
      const parsed = actor.normalizeDocument(JSON.parse(text));
      if (parsed.error) {
        alert(parsed.error);
        return;
      }
      currentActors = parsed.actors;
      currentIndex = 0;
      renderCharacterSheet();
    } catch (err) {
      alert('Error interpreting the runes. Ensure it is a valid Foundry VTT actor file.');
      console.error(err);
    }
  };
  reader.readAsText(file);
}

function resetViewer() {
  currentActors = [];
  currentIndex = 0;
  document.getElementById('character-sheet').style.display = 'none';
  document.getElementById('upload-section').style.display = 'block';
  fileInput.value = '';
}

function showTab(tabId) {
  document.querySelectorAll('.tab-content').forEach(el => el.style.display = 'none');
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + tabId).style.display = 'block';
  document.getElementById('btn-' + tabId).classList.add('active');
}

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[ch]));
}

function fmtMod(n) {
  const value = Math.trunc(Number(n) || 0);
  return value >= 0 ? '+' + value : String(value);
}

function pips(filled, total) {
  let text = '';
  for (let i = 0; i < total; i += 1) text += i < filled ? '●' : '○';
  return text;
}

function rollHtml(text) {
  const source = String(text || '');
  const pattern = /\[\[\/(?:r|roll|damage)\s+([^\]]+)\]\]/gi;
  let html = '';
  let last = 0;
  let match;
  while ((match = pattern.exec(source))) {
    html += esc(source.slice(last, match.index));
    html += `<button type="button" class="foundry-roll" data-formula="${esc(match[1].trim())}">${esc(match[1].trim())}</button>`;
    last = match.index + match[0].length;
  }
  html += esc(source.slice(last));
  return html.replace(/\n/g, '<br>');
}

function speedLabel(key) {
  return { walk: 'Walk', fly: 'Fly', swim: 'Swim', climb: 'Climb', burrow: 'Burrow' }[key] || key;
}

function prepLabel(mode) {
  return {
    prepared: 'prepared',
    always: 'always prepared',
    atwill: 'at will',
    innate: 'innate',
    pact: 'pact'
  }[mode] || '';
}

function renderCharacterSheet() {
  const sheet = currentActors[currentIndex];
  if (!sheet) return;
  document.getElementById('upload-section').style.display = 'none';
  document.getElementById('character-sheet').style.display = 'block';
  showTab('core');

  document.getElementById('char-name').textContent = sheet.name;
  const imgEl = document.getElementById('char-img');
  if (sheet.img) {
    imgEl.src = sheet.img;
    imgEl.style.display = 'block';
  } else {
    imgEl.removeAttribute('src');
    imgEl.style.display = 'none';
  }
  document.getElementById('char-subtitle').textContent = sheet.subtitle;
  document.getElementById('char-edition').textContent = sheet.edition || '';

  const picker = document.getElementById('actor-picker');
  if (currentActors.length > 1) {
    picker.style.display = 'flex';
    picker.innerHTML = currentActors.map((entry, index) =>
      `<button type="button" class="btn-leaf actor-pick ${index === currentIndex ? 'active' : ''}" data-index="${index}">${esc(entry.name)}</button>`
    ).join('');
  } else {
    picker.style.display = 'none';
    picker.innerHTML = '';
  }

  const hpText = (sheet.hp.value == null ? '—' : sheet.hp.value) + ' / ' + (sheet.hp.max == null ? '—' : sheet.hp.max);
  document.getElementById('stat-hp').textContent = sheet.hp.temp ? hpText + ' +' + sheet.hp.temp : hpText;
  document.getElementById('stat-ac').textContent = sheet.ac.value == null ? '—' : sheet.ac.value;
  document.getElementById('stat-ac-formula').textContent = sheet.ac.formula || '';
  const walk = sheet.speeds.find(speed => speed.key === 'walk');
  document.getElementById('stat-speed').textContent = walk ? walk.value + ' ' + walk.units : '—';

  document.getElementById('attr-row').innerHTML = sheet.abilities.map(ability =>
    `<td><div class="attr-score">${ability.score}</div><div class="attr-mod">${fmtMod(ability.mod)}</div></td>`
  ).join('');
  document.getElementById('save-row').innerHTML = sheet.abilities.map(ability =>
    `<td class="${ability.proficient ? 'proficient' : ''}">${fmtMod(ability.save)}</td>`
  ).join('');

  const extra = [];
  extra.push(`<div class="stat-box"><span>Initiative</span> <strong>${fmtMod(sheet.initiative.total)}</strong> <button type="button" class="foundry-roll" data-formula="${esc(sheet.initiative.formula)}">${esc(sheet.initiative.formula)}</button></div>`);
  extra.push(`<div class="stat-box"><span>Proficiency</span> <strong>${fmtMod(sheet.proficiency)}</strong></div>`);
  if (sheet.level) extra.push(`<div class="stat-box"><span>Level</span> <strong>${sheet.level}</strong></div>`);
  extra.push(`<div class="stat-box"><span>Inspiration</span> <strong>${sheet.inspiration ? 'Yes' : 'No'}</strong></div>`);
  extra.push(`<div class="stat-box"><span>Death saves</span> <strong>${pips(sheet.death.success, 3)} / ${pips(sheet.death.failure, 3)}</strong></div>`);
  if (sheet.exhaustion) extra.push(`<div class="stat-box"><span>Exhaustion</span> <strong>${sheet.exhaustion}</strong></div>`);
  if (sheet.spell.dc != null) extra.push(`<div class="stat-box"><span>Spell DC</span> <strong>${sheet.spell.dc}</strong></div>`);
  if (sheet.spell.attack != null) extra.push(`<div class="stat-box"><span>Spell attack</span> <strong>${fmtMod(sheet.spell.attack)}</strong></div>`);
  const concentration = [];
  if (sheet.concentration.active) concentration.push('concentrating');
  if (sheet.concentration.ability) concentration.push(sheet.concentration.ability + ' save');
  if (sheet.concentration.bonus) concentration.push(sheet.concentration.bonus);
  extra.push(`<div class="stat-box"><span>Concentration</span> <strong>${esc(concentration.join(', ') || '—')}</strong></div>`);
  document.getElementById('core-extra').innerHTML = extra.join('');

  const speedLine = sheet.speeds.map(speed =>
    `<span><strong>${speedLabel(speed.key)}</strong> ${speed.value} ${esc(speed.units)}${speed.hover ? ' hover' : ''}</span>`
  ).join(' · ');
  document.getElementById('speed-line').innerHTML = speedLine || '<span>No speeds recorded</span>';

  const senseLine = sheet.senses.join(', ');
  document.getElementById('sense-line').textContent = senseLine;

  const conditions = document.getElementById('condition-line');
  if (sheet.conditions.length) {
    conditions.style.display = 'block';
    conditions.textContent = 'Conditions: ' + sheet.conditions.join(', ');
  } else {
    conditions.style.display = 'none';
    conditions.textContent = '';
  }

  const skillRows = sheet.skills.filter(skill => skill.proficient || skill.expertise || skill.total !== 0);
  document.getElementById('skill-table').innerHTML = skillRows.length
    ? `<table class="data-table"><thead><tr><th>Skill</th><th>Mod</th><th>Passive</th></tr></thead><tbody>${
      skillRows.map(skill => `<tr class="${skill.proficient ? 'proficient' : ''}"><td>${esc(skill.label)}${skill.expertise ? ' (expertise)' : ''}</td><td>${fmtMod(skill.total)}</td><td>${skill.passive}</td></tr>`).join('')
    }</tbody></table>`
    : '<p>No skill bonuses recorded.</p>';

  document.getElementById('list-features').innerHTML = sheet.features.length
    ? sheet.features.map(renderDetails).join('')
    : '<p>The winds carry no features for this one.</p>';

  const slotLine = sheet.slots.map(slot => {
    const name = slot.pact ? 'Pact ' + slot.level : 'Level ' + slot.level;
    const remaining = slot.remaining == null ? '?' : slot.remaining;
    const max = slot.max == null ? '?' : slot.max;
    return `<span class="slot-pip"><strong>${esc(name)}</strong> ${remaining}/${max}</span>`;
  }).join('');
  document.getElementById('slot-line').innerHTML = slotLine;

  document.getElementById('list-spells').innerHTML = sheet.spells.length
    ? sheet.spells.map(group => {
      const title = group.level === 0 ? 'Cantrips' : 'Level ' + group.level;
      return `<h4>${title}</h4>${group.items.map(renderDetails).join('')}`;
    }).join('')
    : '<p>No magical affinities found.</p>';

  const coins = sheet.currencies.map(coin => coin.value + ' ' + coin.key).join(', ');
  document.getElementById('list-inventory').innerHTML =
    (coins ? `<p class="coin-line">${esc(coins)}</p>` : '') +
    (sheet.inventory.length ? sheet.inventory.map(renderDetails).join('') : '<p>The traveler carries no worldly burdens.</p>');

  document.getElementById('char-bio').innerHTML = sheet.biography.length
    ? sheet.biography.map(field => `<h4>${esc(field.label)}</h4><div class="bio-block">${rollHtml(field.text)}</div>`).join('')
    : '<p>The story of this spirit is yet to be written...</p>';
}

function renderDetails(item) {
  const marks = [];
  if (item.quantity) marks.push(item.quantity + '×');
  if (item.equipped) marks.push('equipped');
  if (item.attuned) marks.push('attuned');
  if (item.concentration) marks.push('concentration');
  const prep = prepLabel(item.preparation);
  if (prep) marks.push(prep);
  if (item.damage.length) marks.push(item.damage.join(', '));
  if (item.source) marks.push(item.source);
  const meta = marks.length ? `<span class="item-meta">${esc(marks.join(' · '))}</span>` : '';
  return `<details><summary>${esc(item.name)}${meta}</summary><div class="item-desc">${rollHtml(item.text) || 'No records provided in the archives.'}</div></details>`;
}

document.getElementById('actor-picker').addEventListener('click', (event) => {
  const button = event.target.closest('.actor-pick');
  if (!button) return;
  currentIndex = Number(button.dataset.index) || 0;
  renderCharacterSheet();
});
