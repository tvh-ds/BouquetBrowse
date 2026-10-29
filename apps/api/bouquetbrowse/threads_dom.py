"""Read-only extraction of rendered UI. No hydration state, cookies or private API."""

READ_SURFACE = r"""() => {
  const shown = e => !!e && !!e.getClientRects().length;
  const owned = (e, card) => e.closest('[data-pressable-container]') === card;
  const cards = [...document.querySelectorAll('[data-pressable-container]')]
    .filter(e => shown(e) && [...e.querySelectorAll('time[datetime]')].some(t => owned(t,e))).slice(0,100);
  const posts = cards.map(card => {
    const time = [...card.querySelectorAll('time[datetime]')].find(e => owned(e,card));
    const anchor = time?.closest('a[href]');
    const href = anchor?.getAttribute('href');
    if (!href) return null;
    const spans = [...card.querySelectorAll('span[dir="auto"]')].filter(e => owned(e,card)
      && !e.closest('a,time,button,[role="button"]') && !e.querySelector('time'));
    const textOf = e => {
      const walker = document.createTreeWalker(e, NodeFilter.SHOW_TEXT);
      let text='', n;
      while ((n=walker.nextNode())) {
        if (!n.parentElement?.closest('button,[role="button"]') && owned(n.parentElement,card)) text += n.textContent;
      }
      return text.trim();
    };
    const caption = spans.map(textOf).find(t => t && !/^(?:[\d.,]+|\d+\s*[smhdwmy]|\d+\s*(?:hours?|minutes?|days?)\s+ago|\d{1,2}\/\d{1,2}\/\d{2,4})$/i.test(t)) || '';
    const images = [...card.querySelectorAll('img')].filter(e=>owned(e,card) && shown(e)
      && !/profile picture/i.test(e.alt||'') && Math.max(e.naturalWidth,parseInt(e.getAttribute('width'))||0)>128)
      .map(e=>e.currentSrc || e.getAttribute('src')).filter(Boolean).slice(0,10);
    const quoted = [...card.querySelectorAll('[data-pressable-container] time')]
      .map(e=>e.closest('a[href]')?.getAttribute('href')).filter(Boolean);
    const topics=[...card.querySelectorAll('a[href*="serp_type=tags"]')].map(e=>e.textContent?.slice(0,120));
    const privateAuthor=!!card.querySelector('[aria-label="Private profile"],[aria-label="Private"],[aria-label="Riêng tư"]');
    return {href, text:caption.slice(0,20000), topics, private:privateAuthor, published_at:time.getAttribute('datetime'), media_urls:images,
      quoted:quoted.length===1 ? quoted[0] : null, nested:quoted.length, videos:card.querySelectorAll('video').length};
  }).filter(Boolean);
  const controls = [...document.querySelectorAll('button,[role="button"],[role="menuitem"]')]
    .filter(shown).map((e,index)=>({index, label:(e.getAttribute('aria-label')||e.textContent||'').trim().slice(0,160),
      role:e.getAttribute('role')||'button', sort:!!e.querySelector('[aria-label="Sort"]'),
      card:e.closest('[data-pressable-container]')?.querySelector('time')?.closest('a')?.getAttribute('href')}))
    .filter(x=>x.sort || /^(?:view|show|load|see).{0,50}(?:repl|more)|^(?:xem|hiển thị|tải).{0,50}(?:phản hồi|trả lời)|^sort\b|^sắp xếp\b/i.test(x.label)
      || x.role==='menuitem' && /^(?:top|recent|newest|most recent|all replies)$/i.test(x.label)).slice(0,40);
  const path=location.pathname;
  const profile=/^\/@[A-Za-z0-9_.]+\/?$/.test(path)
    ? {url:location.origin+path, text:(document.querySelector('meta[property="og:description"]')?.getAttribute('content')||'').slice(0,4000)} : null;
  const blocked=!!document.querySelector('input[type="password"],iframe[src*="captcha"]')
    || /\/(?:login|accounts|challenge|checkpoint)(?:\/|$)/.test(path);
  const authenticated=!!document.querySelector('a[href^="/@"] [aria-label="Profile"]');
  return {url:location.href, posts, controls, profile, blocked, authenticated,
    sorting:[...document.querySelectorAll('button,[role="button"]')].filter(shown)
      .find(e=>e.querySelector('[aria-label="Sort"]'))?.textContent?.trim().slice(0,40)||'unknown'};
}"""
