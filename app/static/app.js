const form = document.querySelector('#extract-form');
const statusEl = document.querySelector('#status');
const analysisButton = document.querySelector('#analysis-button');
const scriptButton = document.querySelector('#script-button');
const videoButton = document.querySelector('#video-button');
const pageTitle = document.querySelector('#page-title');
const navItems = [...document.querySelectorAll('.nav-item')];
const recordsList = document.querySelector('#records-list');
const refreshRecordsButton = document.querySelector('#refresh-records');
const createVoiceButton = document.querySelector('#create-voice-button');
const inputMethodSelect = document.querySelector('#input-method');
const urlField = document.querySelector('#url-field');
const manualField = document.querySelector('#manual-field');
let stageState = {
  product: null,
  analysis: null,
  script: null,
  video: null,
};

const labels = {
  target_users: '目标用户',
  use_scenarios: '使用场景',
  pain_points: '用户痛点',
  selling_points: '核心卖点',
  content_angles: '内容角度',
};

navItems.forEach((item) => {
  item.addEventListener('click', () => showPage(item.dataset.target));
});

loadSavedResultFromPath();
loadRecordsList();
loadVoices();
refreshRecordsButton.addEventListener('click', loadRecordsList);
createVoiceButton.addEventListener('click', createVoiceProfile);
inputMethodSelect.addEventListener('change', updateInputMethodFields);
document.querySelector('#voice-select').addEventListener('change', updateVoiceGenerationAvailability);
updateInputMethodFields();

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  setStatus('整理产品信息中...');
  form.querySelector('button').disabled = true;
  try {
    const inputMethod = inputMethodSelect.value;
    const payload = { input_method: inputMethod };
    if (inputMethod === 'manual') {
      payload.manual_text = document.querySelector('#manual_text').value || null;
    } else {
      payload.url = document.querySelector('#url').value;
      payload.manual_text = null;
    }
    const data = await postJson('/api/extract-product', payload);
    stageState = { product: data, analysis: null, script: null, video: null };
    renderProduct(data);
    renderWarnings(data.warnings || []);
    loadRecordsList();
    setStatus('产品信息整理完成');
    showPage('product-page');
  } catch (error) {
    setStatus(`产品信息整理失败：${error.message}`);
  } finally {
    form.querySelector('button').disabled = false;
  }
});

analysisButton.addEventListener('click', async () => {
  if (!stageState.product) return;
  setStatus('生成产品分析中...');
  analysisButton.disabled = true;
  try {
    const payload = {
      task_id: stageState.product.task_id,
      product: stageState.product.product,
      localized_product: stageState.product.localized_product,
      visible_text: stageState.product.visible_text,
      warnings: stageState.product.warnings || [],
    };
    const data = await postJson('/api/analyze-product', payload);
    stageState.analysis = data;
    if (stageState.product && data.localized_product) {
      stageState.product.localized_product = data.localized_product;
      renderProduct(stageState.product);
    }
    renderAnalysis(data);
    renderWarnings(data.warnings || []);
    loadRecordsList();
    setStatus('产品分析完成');
    showPage('analysis-page');
  } catch (error) {
    setStatus(`产品分析失败：${error.message}`);
  } finally {
    analysisButton.disabled = false;
  }
});

scriptButton.addEventListener('click', async () => {
  if (!stageState.analysis) return;
  setStatus('生成视频口播文案中...');
  scriptButton.disabled = true;
  try {
    const payload = {
      task_id: stageState.analysis.task_id,
      product: stageState.analysis.product,
      analysis: stageState.analysis.analysis,
      visible_text: stageState.product?.visible_text || stageState.analysis.visible_text || '',
      warnings: stageState.analysis.warnings || [],
    };
    const data = await postJson('/api/generate-script', payload);
    stageState.script = data;
    renderScript(data);
    updateVoiceGenerationAvailability();
    renderWarnings(data.warnings || []);
    loadRecordsList();
    setStatus('视频口播文案完成');
    showPage('script-page');
  } catch (error) {
    setStatus(`视频口播文案失败：${error.message}`);
  } finally {
    scriptButton.disabled = false;
  }
});

videoButton.addEventListener('click', async () => {
  if (!stageState.script) return;
  const selectedVoiceId = document.querySelector('#voice-select').value;
  if (!selectedVoiceId) {
    setStatus('请先创建或选择音色');
    updateVoiceGenerationAvailability();
    return;
  }
  setStatus('生成口播语音中...');
  videoButton.disabled = true;
  try {
    const text = speechTextForScript(stageState.script);
    const data = await postJson('/api/generate-voice', {
      task_id: stageState.script.task_id,
      text,
      voice: document.querySelector('#voice-id').value || 'custom_voice',
      voice_id: selectedVoiceId,
      voice_instruction: document.querySelector('#voice-instruction').value || '',
      audio_format: document.querySelector('#voice-format').value || 'wav',
      sample_rate: Number(document.querySelector('#sample-rate').value || 24000),
    });
    stageState.video = data;
    renderVoice(data);
    renderWarnings([...(stageState.script.warnings || []), ...(data.warnings || [])]);
    loadRecordsList();
    setStatus(data.audio_url ? '口播语音生成完成' : '口播语音生成被跳过');
  } catch (error) {
    setStatus(`口播语音生成失败：${error.message}`);
  } finally {
    updateVoiceGenerationAvailability();
  }
});

function updateInputMethodFields() {
  const isManual = inputMethodSelect.value === 'manual';
  const urlInput = document.querySelector('#url');
  const manualInput = document.querySelector('#manual_text');
  urlField.classList.toggle('hidden', isManual);
  manualField.classList.toggle('hidden', !isManual);
  urlInput.required = !isManual;
  urlInput.disabled = isManual;
  manualInput.required = isManual;
  manualInput.disabled = !isManual;
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

async function loadVoices() {
  try {
    const response = await fetch('/api/voices');
    if (!response.ok) throw new Error(await response.text());
    renderVoiceOptions(await response.json());
  } catch (error) {
    setStatus(`音色列表加载失败：${error.message}`);
  }
}

function renderVoiceOptions(voices) {
  const select = document.querySelector('#voice-select');
  select.innerHTML = '<option value="">先创建或选择音色</option>';
  voices.forEach((voice) => {
    const option = document.createElement('option');
    option.value = voice.voice_id;
    option.textContent = `${voice.name} · ${voice.prompt || voice.voice_id}`;
    select.appendChild(option);
  });
  updateVoiceGenerationAvailability();
}

function updateVoiceGenerationAvailability() {
  const selectedVoiceId = document.querySelector('#voice-select').value;
  videoButton.disabled = !stageState.script || !selectedVoiceId;
}

function speechTextForScript(scriptResponse) {
  const script = scriptResponse?.short_video_script || {};
  const hook = String(scriptResponse?.short_video_script?.hook || '').trim();
  const body = String(scriptResponse?.short_video_script?.script || '').trim();
  return [hook, body].filter(Boolean).join('\n');
}

async function createVoiceProfile() {
  setStatus('创建音色中...');
  createVoiceButton.disabled = true;
  try {
    const data = await postJson('/api/voices', {
      name: document.querySelector('#voice-id').value || 'custom_voice',
      prompt: document.querySelector('#voice-instruction').value || '',
      audio_format: document.querySelector('#voice-format').value || 'wav',
      sample_rate: Number(document.querySelector('#sample-rate').value || 24000),
    });
    if (data.profile) {
      await loadVoices();
      document.querySelector('#voice-select').value = data.profile.voice_id;
      updateVoiceGenerationAvailability();
      setStatus('音色创建完成');
    } else {
      renderWarnings(data.warnings || []);
      setStatus('音色创建失败');
    }
  } catch (error) {
    setStatus(`音色创建失败：${error.message}`);
  } finally {
    createVoiceButton.disabled = false;
  }
}

function showPage(pageId) {
  const page = document.querySelector(`#${pageId}`);
  if (!page) return;
  document.querySelectorAll('.page').forEach((item) => item.classList.toggle('active', item.id === pageId));
  navItems.forEach((item) => item.classList.toggle('active', item.dataset.target === pageId));
  pageTitle.textContent = page.dataset.title || '产品分析工作台';
}

function renderProduct(data) {
  const product = data.product || {};
  setText('#scrape-method', formatExtractionMethod(data.extraction_method));
  setText('#product-title', valueOf(product.title));
  setText('#product-category', valueOf(product.category));
  setText('#product-price', valueOf(product.price));
  setText('#product-rating', valueOf(product.rating));
  setText('#product-reviews', valueOf(product.review_count));

  const image = document.querySelector('#product-image');
  if (product.main_image_url) {
    image.src = product.main_image_url;
    image.classList.remove('hidden');
  } else {
    image.classList.add('hidden');
  }

  renderList('#product-features', product.core_features || []);
  renderSpecs('#product-specs', product.specifications || {});

  const localized = data.localized_product || {};
  setText('#localized-title', localized.title || 'unknown');
  setText('#localized-category', localized.category || 'unknown');
  setText('#localized-price', localized.price || 'unknown');
  setText('#localized-rating', localized.rating || 'unknown');
  setText('#localized-reviews', localized.review_count || 'unknown');
  setText('#localized-summary', localized.summary || 'unknown');
  renderList('#localized-features', localized.core_features || []);
  renderSpecs('#localized-specs', localized.specifications || {});
  renderQa('#product-qa', data.product_qa);
}

function renderAnalysis(data) {
  renderAnalysisLogic(data.analysis?.content_logic || []);
  const analysisRoot = document.querySelector('#analysis-sections');
  const hasContentLogic = Boolean(data.analysis?.content_logic?.length);
  analysisRoot.classList.toggle('hidden', hasContentLogic);
  analysisRoot.innerHTML = '';
  if (!hasContentLogic) {
    Object.entries(labels).forEach(([key, label]) => {
      const items = data.analysis?.[key] || [];
      const block = document.createElement('section');
      block.className = 'analysis-block';
      block.innerHTML = `<h3>${label}</h3><ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>`;
      analysisRoot.appendChild(block);
    });
  }
  renderQa('#product-qa', data.product_qa);
}

function renderAnalysisLogic(rows) {
  const root = document.querySelector('#analysis-logic');
  if (!root) return;
  if (!rows.length) {
    root.innerHTML = '';
    return;
  }
  root.innerHTML = `
    <h3>分析逻辑</h3>
    <div class="analysis-logic-grid">
      ${rows.map((row) => `
        <article class="analysis-logic-row">
          <strong>${escapeHtml(row.dimension || '分析维度')}</strong>
          <p><span>分析结论</span>${escapeHtml(row.conclusion || '暂无')}</p>
          <p><span>依据</span>${escapeHtml(row.evidence || '暂无')}</p>
          <p><span>口播文案内容启发</span>${escapeHtml(row.content_angle || '暂无')}</p>
        </article>
      `).join('')}
    </div>
  `;
}

function renderScript(data) {
  setText('#script-hook', data.short_video_script?.hook || '');
  setText('#script-body', data.short_video_script?.script || '');
  renderQa('#analysis-qa', data.analysis_qa);
}

function renderVoice(data) {
  const panel = document.querySelector('#video-panel');
  const empty = document.querySelector('#asset-empty');
  const audio = document.querySelector('#voice-audio');
  const links = document.querySelector('#download-links');
  panel.classList.remove('hidden');
  empty.classList.add('hidden');
  links.innerHTML = '';
  if (data.audio_url) {
    audio.src = data.audio_url;
    audio.classList.remove('hidden');
    links.appendChild(downloadLink(data.audio_url, '下载口播音频'));
  } else {
    audio.classList.add('hidden');
  }
  if (data.remote_audio_url && data.remote_audio_url !== data.audio_url) links.appendChild(downloadLink(data.remote_audio_url, '24小时临时音频'));
}

async function loadSavedResultFromPath() {
  const match = window.location.pathname.match(/^\/r\/([A-Za-z0-9_-]+)$/);
  if (!match) return;
  setStatus('加载保存记录中...');
  try {
    const response = await fetch(`/api/results/${match[1]}`);
    if (!response.ok) throw new Error(await response.text());
    const record = await response.json();
    hydrateSavedRecord(record);
    setStatus('保存记录已加载');
    showPage(pageForHydratedRecord(record));
  } catch (error) {
    setStatus(`保存记录加载失败：${error.message}`);
  }
}

function hydrateSavedRecord(record) {
  clearWorkspaceData();
  if (record.product_response) {
    stageState.product = record.product_response;
    renderProduct(stageState.product);
  }
  if (record.stage_analysis_response) {
    stageState.analysis = record.stage_analysis_response;
    renderAnalysis(stageState.analysis);
  }
  if (record.script_response) {
    stageState.script = record.script_response;
    renderScript(stageState.script);
    updateVoiceGenerationAvailability();
  }
  const voiceResponse = voiceResponseForRecord(record);
  if (voiceResponse) {
    stageState.video = voiceResponse;
    renderVoice(stageState.video);
  }
  if (record.analysis_response && !stageState.product) {
    const legacy = record.analysis_response;
    stageState.product = { task_id: legacy.task_id, source_url: record.source_url, product: legacy.product, visible_text: '', warnings: legacy.warnings || [] };
    stageState.analysis = { task_id: legacy.task_id, product: legacy.product, analysis: legacy.analysis, warnings: legacy.warnings || [] };
    stageState.script = legacy;
    renderProduct(stageState.product);
    renderAnalysis(stageState.analysis);
    renderScript(stageState.script);
  }
}

async function loadRecordsList() {
  try {
    const response = await fetch('/api/results');
    if (!response.ok) throw new Error(await response.text());
    const data = await response.json();
    renderRecordsList(data.records || []);
  } catch (error) {
    recordsList.innerHTML = `<div class="history-empty">历史记录加载失败</div>`;
  }
}

function renderRecordsList(records) {
  recordsList.innerHTML = '';
  if (!records.length) {
    recordsList.innerHTML = '<div class="history-empty">暂无记录，完成一次产品信息整理后会出现在这里。</div>';
    return;
  }
  records.forEach((record) => {
    const item = document.createElement('article');
    item.className = 'history-record';
    item.innerHTML = `
      <div class="history-record-head">
        <button type="button" class="history-expand" data-task-id="${escapeHtml(record.task_id)}">
          <span>${escapeHtml(record.title || 'unknown')}</span>
          <small>${escapeHtml(record.source_url || '')}</small>
        </button>
        <div class="history-actions">
          <button type="button" class="history-delete" data-task-id="${escapeHtml(record.task_id)}">删除</button>
        </div>
      </div>
      <div class="history-badges">
        <span>${record.has_product ? '产品信息' : '未整理'}</span>
        <span>${record.has_analysis ? '产品分析' : '未分析'}</span>
        <span>${record.has_script ? '口播文案' : '无文案'}</span>
        <span>${record.has_voice ? '口播语音' : '无语音'}</span>
      </div>
      <div class="history-detail hidden" id="detail-${escapeHtml(record.task_id)}"></div>
    `;
    recordsList.appendChild(item);
  });
  recordsList.querySelectorAll('.history-expand').forEach((button) => {
    button.addEventListener('click', () => toggleRecordDetail(button.dataset.taskId));
  });
  recordsList.querySelectorAll('.history-delete').forEach((button) => {
    button.addEventListener('click', () => deleteRecord(button.dataset.taskId));
  });
}

async function toggleRecordDetail(taskId) {
  const detail = document.querySelector(`#detail-${CSS.escape(taskId)}`);
  if (!detail) return;
  if (!detail.classList.contains('hidden')) {
    detail.classList.add('hidden');
    return;
  }
  detail.textContent = '加载中...';
  detail.classList.remove('hidden');
  try {
    const response = await fetch(`/api/results/${encodeURIComponent(taskId)}`);
    if (!response.ok) throw new Error(await response.text());
    renderRecordDetail(detail, await response.json());
  } catch (error) {
    detail.textContent = `加载失败：${error.message}`;
  }
}

function voiceResponseForRecord(record) {
  const voice = record.voice_response || {};
  if (voice.audio_url || voice.remote_audio_url) return voice;
  const legacy = record.video_response || {};
  if (legacy.audio_url) return legacy;
  return null;
}

function pageForHydratedRecord(record) {
  if (record.voice_response || record.video_response || record.script_response || record.analysis_response?.short_video_script) return 'script-page';
  if (record.stage_analysis_response || record.analysis_response) return 'analysis-page';
  if (record.product_response) return 'product-page';
  return 'product-page';
}

function speechTextForShortVideoScript(script) {
  return [script.hook, script.script].map((part) => String(part || '').trim()).filter(Boolean).join('\n');
}

function renderRecordDetail(root, record) {
  const product = record.product_response?.localized_product || record.product_response?.product || record.analysis_response?.product || {};
  const analysis = record.stage_analysis_response?.analysis || record.analysis_response?.analysis || {};
  const script = record.script_response?.short_video_script || record.analysis_response?.short_video_script || {};
  const voice = voiceResponseForRecord(record) || {};
  root.innerHTML = `
    <section><h3>产品信息</h3><p>${escapeHtml(product.title?.value || product.title || 'unknown')}</p></section>
    <section><h3>产品分析</h3><p>${escapeHtml(firstText(analysis.selling_points) || firstText(analysis.content_angles) || '暂无')}</p></section>
    <section><h3>口播文案</h3><p>${escapeHtml(speechTextForShortVideoScript(script) || '暂无')}</p></section>
    <section><h3>口播语音</h3><div class="history-links">${artifactLink(voice.audio_url, '音频')}${artifactLink(voice.remote_audio_url, '临时音频')}</div></section>
  `;
}

function firstText(items) {
  return Array.isArray(items) && items.length ? String(items[0]) : '';
}

function artifactLink(url, label) {
  return url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${label}</a>` : `<span>${label}暂无</span>`;
}

async function loadRecord(taskId) {
  setStatus('加载历史记录中...');
  try {
    const response = await fetch(`/api/results/${encodeURIComponent(taskId)}`);
    if (!response.ok) throw new Error(await response.text());
    const record = await response.json();
    hydrateSavedRecord(record);
    setStatus('历史记录已加载');
    showPage(pageForHydratedRecord(record));
  } catch (error) {
    setStatus(`历史记录加载失败：${error.message}`);
  }
}

async function deleteRecord(taskId) {
  try {
    const response = await fetch(`/api/results/${encodeURIComponent(taskId)}`, { method: 'DELETE' });
    if (!response.ok) throw new Error(await response.text());
    if (stageState.product?.task_id === taskId || stageState.script?.task_id === taskId) {
      resetWorkspace();
    }
    await loadRecordsList();
    setStatus('历史记录已删除');
    showPage('records-page');
  } catch (error) {
    setStatus(`删除失败：${error.message}`);
  }
}

function resetWorkspace() {
  clearWorkspaceData();
  showPage('input-page');
}

function clearWorkspaceData() {
  stageState = { product: null, analysis: null, script: null, video: null };
  const productImage = document.querySelector('#product-image');
  productImage.classList.add('hidden');
  productImage.removeAttribute('src');
  ['#scrape-method', '#product-title', '#product-category', '#product-price', '#product-rating', '#product-reviews', '#localized-title', '#localized-category', '#localized-price', '#localized-rating', '#localized-reviews', '#localized-summary', '#script-hook', '#script-body'].forEach((selector) => {
    document.querySelector(selector).textContent = '';
  });
  ['#product-features', '#localized-features', '#product-specs', '#localized-specs', '#analysis-logic', '#analysis-sections', '#download-links'].forEach((selector) => {
    document.querySelector(selector).innerHTML = '';
  });
  document.querySelector('#video-panel').classList.add('hidden');
  document.querySelector('#asset-empty').classList.remove('hidden');
  document.querySelector('#voice-audio').classList.add('hidden');
  document.querySelector('#voice-audio').removeAttribute('src');
  updateVoiceGenerationAvailability();
  renderQa('#product-qa', null);
  renderQa('#analysis-qa', null);
  renderWarnings([]);
}

function renderQa(selector, qa) {
  const root = document.querySelector(selector);
  if (!root) return;
  if (!qa) {
    root.className = 'qa-panel empty-state';
    root.textContent = selector === '#product-qa' ? '产品信息 QA 尚未运行' : '产品分析 QA 尚未运行';
    return;
  }
  root.className = `qa-panel qa-${qa.status || 'passed'}`;
  const issues = qa.issues || [];
  root.innerHTML = `<strong>QA ${qa.status === 'passed' ? '通过' : '需处理'} · ${qa.attempts || 1}/3</strong>${issues.length ? `<ul>${issues.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>` : '<p>未发现明显错误或夸大描述。</p>'}${qa.rewrite_guidance ? `<p>${escapeHtml(qa.rewrite_guidance)}</p>` : ''}`;
}

function renderWarnings(warnings) {
  const panel = document.querySelector('#warnings-panel');
  const list = document.querySelector('#warnings');
  list.innerHTML = '';
  if (!warnings.length) {
    panel.classList.add('hidden');
    return;
  }
  panel.classList.remove('hidden');
  warnings.forEach((warning) => {
    const li = document.createElement('li');
    li.textContent = warning;
    list.appendChild(li);
  });
}

function renderList(selector, items) {
  const list = document.querySelector(selector);
  list.innerHTML = '';
  if (!items.length) {
    const li = document.createElement('li');
    li.textContent = 'unknown';
    list.appendChild(li);
    return;
  }
  items.forEach((item) => {
    const li = document.createElement('li');
    li.textContent = item;
    list.appendChild(li);
  });
}

function renderSpecs(selector, specs) {
  const root = document.querySelector(selector);
  root.innerHTML = '';
  const entries = Object.entries(specs);
  if (!entries.length) {
    root.innerHTML = '<div><dt>规格</dt><dd>unknown</dd></div>';
    return;
  }
  entries.forEach(([key, value]) => {
    const row = document.createElement('div');
    row.innerHTML = `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd>`;
    root.appendChild(row);
  });
}

function downloadLink(url, label) {
  const link = document.createElement('a');
  link.href = url;
  link.textContent = label;
  link.download = '';
  return link;
}

function valueOf(field) {
  return field?.value && field.value !== 'unknown' ? field.value : 'unknown';
}

function formatExtractionMethod(method) {
  const labels = {
    firecrawl: 'Firecrawl 抓取',
    local: '本地抓取',
    manual: '手动复制粘贴',
    firecrawl_failed: 'Firecrawl 抓取失败',
    local_failed: '本地抓取失败',
    fallback_local: 'Firecrawl 失败后回退本地抓取',
    blocked: 'Amazon 反爬/继续购物页',
    unsupported: '非支持链接',
  };
  return labels[method] || '未知方式';
}

function setText(selector, text) {
  document.querySelector(selector).textContent = text || 'unknown';
}

function setStatus(text) {
  statusEl.textContent = text;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
}
