(() => {
  const builder = document.querySelector('#visualBuilderSettings');
  if (!builder || document.querySelector('#aiModelingAssistant')) return;

  const style = document.createElement('style');
  style.textContent = '#aiModelingAssistant{margin-top:12px;border:1px solid #cbdcf0;border-radius:10px;background:#fbfdff}#aiModelingAssistant summary{padding:12px 14px;font-weight:700;color:#1c4778;cursor:pointer}.ai-modeling-body{padding:0 14px 14px}.ai-modeling-lead{margin:0 0 10px;color:#60738b;font-size:13px;line-height:1.65}.ai-chat-log{max-height:220px;overflow:auto;display:grid;gap:8px;margin:10px 0;padding:3px}.ai-message{max-width:92%;padding:9px 11px;border-radius:10px;font-size:13px;line-height:1.55;white-space:pre-wrap}.ai-message.user{justify-self:end;background:#ddecff;color:#174a80;border:1px solid #bfdbf7}.ai-message.assistant{background:#f1edff;color:#44258e;border:1px solid #dad0fc}.ai-modeling-input{width:100%;min-height:76px;box-sizing:border-box;resize:vertical;padding:10px;border:1px solid #bcd0e6;border-radius:8px;font:13px/1.55 inherit;color:#23354f;background:#fff}.ai-modeling-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:9px}.ai-modeling-actions button{margin:0}.ai-draft{margin-top:10px;padding:10px 12px;border:1px solid #d5c8fb;border-radius:8px;background:#faf8ff;color:#3f326d;font-size:13px;line-height:1.55}.ai-draft strong{color:#3b278d}.ai-draft ul{margin:7px 0 0;padding-left:19px}.ai-draft.is-hidden{display:none}.ai-modeling-note{margin:9px 0 0;font-size:12px;line-height:1.55;color:#6d7e92}.ai-modeling-state{margin-top:8px;min-height:20px;color:#28629c;font-size:13px}';
  document.head.append(style);

  const panel = document.createElement('details');
  panel.id = 'aiModelingAssistant';
  panel.open = true;
  panel.innerHTML = '<summary>AI 自然语言建模 <span class="help">题目 → BigModel JSON 草案</span></summary><div class="ai-modeling-body"><p class="ai-modeling-lead">输入结构题目后，BigModel 会核对缺失条件；每次都需要确认材料和截面，再生成可预览的有限元模型草案。</p><div id="aiChatLog" class="ai-chat-log" aria-live="polite"><div class="ai-message assistant">请描述几何、连接、支座和荷载。若信息不全，我会先提问。</div></div><textarea id="aiModelPrompt" class="ai-modeling-input" placeholder="例如：跨度 6 m、柱高 4 m 的门式刚架，柱脚固定；横梁中点向下施加 20 kN。"></textarea><div class="ai-modeling-actions"><button id="aiCreateDraft">生成建模草案</button><button id="aiPreviewDraft" class="secondary" disabled>预览到画布</button><button id="aiApplyDraft" class="secondary" disabled>应用到图表</button><button id="aiClearPreview" class="secondary" disabled>清除预览</button></div><div id="aiDraftInfo" class="ai-draft is-hidden"></div><div id="aiModelingState" class="ai-modeling-state">等待题目输入。</div><p class="ai-modeling-note">BigModel 密钥只由本机后端读取。照片重建请切换到上方“图像建模”标签。</p></div>';
  builder.insertAdjacentElement('afterend', panel);
  const select = selector => panel.querySelector(selector);
  let draft = null;
  const setState = message => { select('#aiModelingState').textContent = message; };
  const addMessage = (role, message) => {
    const item = document.createElement('div');
    item.className = 'ai-message ' + role;
    item.textContent = message;
    select('#aiChatLog').append(item);
    select('#aiChatLog').scrollTop = select('#aiChatLog').scrollHeight;
  };
  const controls = enabled => ['#aiPreviewDraft', '#aiApplyDraft', '#aiClearPreview'].forEach(id => { select(id).disabled = !enabled; });
  const readModelingResponse = async (response, fallback) => {
    const contentType = response.headers.get('content-type') || '';
    if (!contentType.toLowerCase().includes('application/json')) {
      if (response.status === 404) throw Error('当前连接的是旧版 FrameCAE 后端，缺少 AI 建模接口。请运行本目录的“启动FrameCAE.cmd”，打开新地址后重试。');
      throw Error(fallback + '（服务器返回 HTTP ' + response.status + '，不是 JSON；请检查后端服务。）');
    }
    const result = await response.json();
    if (!response.ok || result.error) throw Error(result.error || fallback);
    return result;
  };
  const escapeHTML = text => String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;');
  const sourceLabel = source => source === 'bigmodel-glm' ? 'BigModel · GLM-5.3-Flash 结构化输出' : source === 'openai' ? 'GPT 结构化输出' : '未知来源';
  const reviewPanel = document.createElement('div');
  reviewPanel.id = 'aiParameterReview'; reviewPanel.hidden = true;
  reviewPanel.style.cssText = 'margin:10px 0;padding:12px;border:1px solid #b8cbea;border-radius:9px;background:#f5f9ff;color:#253e5e;font-size:13px;line-height:1.6';
  reviewPanel.innerHTML = '<strong>生成前确认参数</strong><p style="margin:5px 0">每次建模都请选择默认值或填写参数；所选参数会进入模型 JSON，计算前仍需复核。</p><div id="aiParameterMaterial"></div><div id="aiParameterSection"></div><div id="aiParameterQuestions"></div><button id="aiConfirmParameters" style="margin-top:10px">确认参数并调用 BigModel 生成草案</button>';
  select('#aiModelPrompt').insertAdjacentElement('afterend', reviewPanel);
  let reviewContext = null;
  const parameterFields = {
    material: [['e', 'E (GPa)'], ['nu', '泊松比 ν'], ['alpha', 'α (10⁻⁶/K)'], ['density', '密度 (kg/m³)']],
    section: [['a', 'A (m²)'], ['iy', 'Iy (m⁴)'], ['iz', 'Iz (m⁴)'], ['j', 'J (m⁴)'], ['d', 'D (m)']],
  };
  const renderParameterChoice = (kind, title, defaults, source) => {
    const container = reviewPanel.querySelector(kind === 'material' ? '#aiParameterMaterial' : '#aiParameterSection');
    container.replaceChildren();
    const heading = document.createElement('strong'); heading.textContent = title; container.append(heading);
    const details = document.createElement('div');
    details.textContent = '本次建议值（' + (source || '软件示例参数') + '）：' + parameterFields[kind].map(([key, label]) => label + ' = ' + defaults[key]).join('；');
    container.append(details);
    const options = document.createElement('div');
    for (const [value, label] of [['default', '使用上述值'], ['custom', '修改参数（未改项沿用上述值）']]) {
      const choice = document.createElement('label'); choice.style.cssText = 'display:inline-flex;align-items:center;gap:4px;margin:4px 14px 4px 0';
      const input = document.createElement('input'); input.type = 'radio'; input.name = 'ai-' + kind + '-mode'; input.value = value;
      choice.append(input, document.createTextNode(label)); options.append(choice);
    }
    container.append(options);
    const fields = document.createElement('div'); fields.style.cssText = 'display:flex;flex-wrap:wrap;gap:8px';
    for (const [key, label] of parameterFields[kind]) {
      const field = document.createElement('label'); field.style.cssText = 'display:flex;flex-direction:column;min-width:105px;flex:1'; field.textContent = label;
      const input = document.createElement('input'); input.type = 'number'; input.step = 'any'; input.dataset.field = key;
      input.value = defaults[key] ?? ''; input.disabled = true; input.style.cssText = 'width:100%;box-sizing:border-box'; field.append(input); fields.append(field);
    }
    container.append(fields);
    container.querySelectorAll('input[type=radio]').forEach(input => input.onchange = () => {
      fields.querySelectorAll('input').forEach(field => { field.disabled = input.value !== 'custom'; });
    });
    container.style.marginTop = '10px';
  };
  const renderReview = review => {
    renderParameterChoice('material', '材料', review.defaults.material, review.defaultSources?.material);
    renderParameterChoice('section', '截面', review.defaults.section, review.defaultSources?.section);
    const questions = reviewPanel.querySelector('#aiParameterQuestions'); questions.replaceChildren();
    (review.questions || []).forEach((item, index) => {
      const block = document.createElement('div'); block.className = 'ai-extra-question';
      block.style.cssText = 'margin-top:10px;padding-top:8px;border-top:1px solid #d5e1ee';
      const question = document.createElement('strong'); question.textContent = (index + 1) + '. ' + item.question; block.append(question);
      const choices = document.createElement('div');
      if (item.default) {
        const label = document.createElement('label'); label.style.display = 'block';
        const radio = document.createElement('input'); radio.type = 'radio'; radio.name = 'ai-question-' + index; radio.value = 'default';
        label.append(radio, document.createTextNode(' 使用建议值：' + item.default)); choices.append(label);
      }
      const label = document.createElement('label'); label.style.display = 'block';
      const radio = document.createElement('input'); radio.type = 'radio'; radio.name = 'ai-question-' + index; radio.value = 'custom';
      label.append(radio, document.createTextNode(' 我来补充：')); choices.append(label); block.append(choices);
      const answer = document.createElement('textarea'); answer.rows = 2; answer.disabled = true;
      answer.placeholder = '请输入实际条件'; answer.style.cssText = 'width:100%;box-sizing:border-box;margin-top:4px'; block.append(answer);
      choices.querySelectorAll('input').forEach(choice => choice.onchange = () => { answer.disabled = choice.value !== 'custom'; });
      block.dataset.question = item.question; block.dataset.default = item.default || ''; questions.append(block);
    });
    reviewPanel.hidden = false;
  };
  const readConfirmedParameters = () => {
    const output = {answers: []};
    for (const kind of ['material', 'section']) {
      const container = reviewPanel.querySelector(kind === 'material' ? '#aiParameterMaterial' : '#aiParameterSection');
      const choice = container.querySelector('input[type=radio]:checked');
      if (!choice) throw Error('请先选择使用默认' + (kind === 'material' ? '材料' : '截面') + '，或填写参数。');
      const values = {};
      if (choice.value === 'custom') container.querySelectorAll('input[data-field]').forEach(input => {
        if (input.value.trim() === '' || !Number.isFinite(Number(input.value))) throw Error('请填写有效的' + input.dataset.field + ' 数值。');
        values[input.dataset.field] = Number(input.value);
      });
      output[kind] = {mode: choice.value, values};
    }
    reviewPanel.querySelectorAll('.ai-extra-question').forEach(block => {
      const choice = block.querySelector('input[type=radio]:checked');
      if (!choice) throw Error('请回答：' + block.dataset.question);
      const answer = choice.value === 'default' ? block.dataset.default : block.querySelector('textarea').value.trim();
      if (!answer) throw Error('请补充：' + block.dataset.question);
      output.answers.push({question: block.dataset.question, answer});
    });
    return output;
  };
  const showDraft = proposal => {
    const items = proposal.assumptions && proposal.assumptions.length
      ? '<ul>' + proposal.assumptions.map(item => '<li>' + escapeHTML(item) + '</li>').join('') + '</ul>'
      : '<p>未列出额外假设。</p>';
    const material = proposal.model?.materials?.[0], section = proposal.model?.sections?.[0];
    const parameters = material && section ? '<br>材料：E ' + escapeHTML(material.e) + ' GPa、ν ' + escapeHTML(material.nu) + '、ρ ' + escapeHTML(material.density) + ' kg/m³；截面：A ' + escapeHTML(section.a) + ' m²、D ' + escapeHTML(section.d) + ' m。' : '';
    select('#aiDraftInfo').innerHTML = '<strong>待确认建模草案</strong><br>' + proposal.summary.nodeCount + ' 个节点、' + proposal.summary.elementCount + ' 根杆件、' + proposal.summary.loadCount + ' 组节点荷载、' + proposal.summary.constraintCount + ' 组边界条件；推荐画布网格 ' + Number(proposal.recommendedGridStep).toFixed(2) + ' m。<br>来源：' + sourceLabel(proposal.source) + '。' + parameters + items;
    select('#aiDraftInfo').classList.remove('is-hidden');
  };
  select('#aiCreateDraft').onclick = async () => {
    const prompt = select('#aiModelPrompt').value.trim();
    if (!prompt) { setState('请先输入结构题目。'); select('#aiModelPrompt').focus(); return; }
    const assistant = window.frameCAEModelAssistant;
    if (!assistant) { setState('建模画布尚未初始化，请刷新页面后重试。'); return; }
    select('#aiCreateDraft').disabled = true;
    draft = null; controls(false); select('#aiDraftInfo').classList.add('is-hidden'); reviewPanel.hidden = true; reviewContext = null;
    setState('BigModel 正在检查题目中还缺少哪些建模条件…');
    addMessage('user', prompt);
    try {
      const baseModel = assistant.currentModel();
      const response = await fetch('/api/ai-model-questions', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({prompt, baseModel})});
      const review = await readModelingResponse(response, '检查建模条件失败。');
      reviewContext = {prompt, baseModel, review};
      renderReview(review);
      addMessage('assistant', review.questions.length ? '请先确认材料和截面，并回答下方 ' + review.questions.length + ' 个题意问题。每项都可选择建议值或提供实际参数。' : '题目中的关键建模条件已足够。请在下方确认本次材料和截面：使用建议值，或提供实际参数。');
      setState('等待你确认本次使用的材料、截面和题意补充信息。');
    } catch (error) {
      addMessage('assistant', '无法检查建模条件：' + error.message);
      setState('检查失败：' + error.message);
    } finally { select('#aiCreateDraft').disabled = false; }
  };
  reviewPanel.querySelector('#aiConfirmParameters').onclick = async () => {
    const assistant = window.frameCAEModelAssistant;
    if (!reviewContext || !assistant) { setState('请先输入题目并检查建模条件。'); return; }
    const {prompt, baseModel} = reviewContext;
    if (prompt !== select('#aiModelPrompt').value.trim() || JSON.stringify(baseModel) !== JSON.stringify(assistant.currentModel())) {
      setState('题目或当前模型已变化，请重新点击“生成建模草案”检查条件。'); return;
    }
    let confirmedParameters;
    try { confirmedParameters = readConfirmedParameters(); }
    catch (error) { setState(error.message); return; }
    const button = reviewPanel.querySelector('#aiConfirmParameters'); button.disabled = true;
    setState('正在将已确认参数提交 BigModel，生成并校验模型 JSON…');
    addMessage('user', '已确认本次材料、截面及 ' + confirmedParameters.answers.length + ' 项题意补充信息。');
    try {
      const response = await fetch('/api/ai-model-draft', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({prompt, baseModel, confirmedParameters})});
      const proposal = await readModelingResponse(response, '生成建模草案失败。');
      draft = proposal; showDraft(draft); controls(true); reviewPanel.hidden = true; reviewContext = null;
      addMessage('assistant', draft.assistantMessage + '\n已生成 ' + draft.summary.nodeCount + ' 个节点、' + draft.summary.elementCount + ' 根杆件。请先“预览到画布”，再决定是否应用。');
      setState('BigModel 草案已通过有限元输入校验，材料和截面已加入模型 JSON，可预览。');
    } catch (error) {
      addMessage('assistant', '无法生成草案：' + error.message);
      setState('生成失败：' + error.message);
    } finally { button.disabled = false; }
  };
  select('#aiPreviewDraft').onclick = () => {
    try { window.frameCAEModelAssistant.preview(draft); setState('紫色虚线表示待确认草案；当前结构和右侧大屏尚未修改。'); }
    catch (error) { setState('预览失败：' + error.message); }
  };
  select('#aiApplyDraft').onclick = () => {
    try {
      window.frameCAEModelAssistant.apply(draft);
      setState('草案已写入节点、杆件、边界条件和荷载图表。请检查后确认并求解。');
      addMessage('assistant', '草案已写入当前图表。下一步请核对几何与假设，然后点击“确认当前结构并更新右侧大屏”。');
    } catch (error) { setState('应用失败：' + error.message); }
  };
  select('#aiClearPreview').onclick = () => { window.frameCAEModelAssistant?.clearPreview(); setState('已清除紫色虚线预览；当前图表没有改变。'); };
})();
