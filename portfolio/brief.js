(() => {
  const sections = [...document.querySelectorAll('[data-language]')];
  const languageButtons = [...document.querySelectorAll('[data-select-language]')];
  const copyButtons = [...document.querySelectorAll('[data-copy]')];
  const fallback = document.querySelector('.copy-fallback');
  let content;
  for (const button of copyButtons) button.disabled = true;

  for (const button of languageButtons) {
    button.addEventListener('click', () => {
      const language = button.dataset.selectLanguage;
      for (const section of sections) section.hidden = section.dataset.language !== language;
      for (const control of languageButtons) control.setAttribute('aria-pressed', String(control === button));
      for (const result of document.querySelectorAll('.copy-result')) result.textContent = '';
      fallback.hidden = true;
      fallback.value = '';
      document.documentElement.lang = language === 'zh' ? 'zh-CN' : 'en';
    });
  }

  fetch('portfolio-content.json').then(response => {
    if (!response.ok) throw new Error('Content unavailable');
    return response.json();
  }).then(value => {
    content = value;
    for (const button of copyButtons) button.disabled = false;
  }).catch(() => {
    for (const section of sections) {
      section.querySelector('.copy-result').textContent = section.dataset.language === 'zh'
        ? '复制文本暂不可用，可直接选择页面文字。'
        : 'Copy text is unavailable. Select the visible text instead.';
    }
  });

  for (const button of copyButtons) {
    button.addEventListener('click', async () => {
      if (!content) return;
      const language = button.dataset.copy;
      const c = content.languages[language];
      const text = [c.project_title, content.stack, c.project_intro,
        ...c.bullets.map(value => '- ' + value), c.project_scope].join('\n\n');
      const result = button.parentElement.querySelector('.copy-result');
      try {
        if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
        await navigator.clipboard.writeText(text);
        fallback.hidden = true;
        result.textContent = language === 'zh' ? '已复制项目描述。' : 'Project description copied.';
      } catch {
        fallback.value = text;
        fallback.hidden = false;
        fallback.focus();
        fallback.select();
        result.textContent = language === 'zh' ? '文本已选中，可按 Ctrl/Cmd+C 复制。' : 'Text selected. Press Ctrl/Cmd+C to copy.';
      }
    });
  }
})();
