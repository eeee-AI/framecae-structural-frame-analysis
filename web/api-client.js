/* Make local service failures visible across all analysis modules. */
(() => {
  const nativeFetch = window.fetch.bind(window);
  const message = '无法连接 FrameCAE 本地服务。请双击项目目录中的“启动FrameCAE.cmd”，等待服务启动后重试。当前模型仍保留在此页面，请勿直接刷新未保存的模型。';
  let notice;
  function showNotice() {
    if (!document.body) return;
    if (!notice) {
      notice = document.createElement('div');
      notice.id = 'serviceNotice';
      notice.setAttribute('role', 'alert');
      notice.style.cssText = 'position:sticky;top:0;z-index:1000;padding:12px 24px;background:#fff0f0;color:#8b1d1d;border-bottom:1px solid #f1c1c1;font:14px/1.6 "Microsoft YaHei",sans-serif';
      notice.textContent = message;
      document.body.prepend(notice);
    }
    notice.hidden = false;
  }
  window.fetch = async (input, options) => {
    const url = new URL(typeof input === 'string' || input instanceof URL ? input : input.url, location.href);
    if (url.origin !== location.origin || !url.pathname.startsWith('/api/')) return nativeFetch(input, options);
    try {
      const response = await nativeFetch(input, options);
      if (notice) notice.hidden = true;
      return response;
    } catch (cause) {
      if (cause?.name === 'AbortError') throw cause;
      showNotice();
      throw new Error(message, {cause});
    }
  };
})();
