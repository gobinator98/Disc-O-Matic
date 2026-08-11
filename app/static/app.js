// Disc-O-Matic shared client-side behavior: theme + menu dropdown.
// Theme is stored client-side (localStorage) for now — no AppSetting
// backend yet, so it isn't shared across devices/browsers.

(function () {
  function resolveTheme(mode) {
    if (mode === 'system') {
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    return mode;
  }

  function applyTheme(mode) {
    var app = document.getElementById('app');
    if (!app) return;
    var resolved = resolveTheme(mode);
    app.classList.remove('theme-dark', 'theme-light');
    app.classList.add(resolved === 'light' ? 'theme-light' : 'theme-dark');
  }

  window.discomatic = window.discomatic || {};
  window.discomatic.setTheme = function (mode) {
    localStorage.setItem('discomatic-theme', mode);
    applyTheme(mode);
    document.querySelectorAll('[data-theme-pick]').forEach(function (btn) {
      btn.classList.toggle('active', btn.getAttribute('data-theme-pick') === mode);
    });
  };

  // Apply as early as possible to avoid a flash of the wrong theme.
  var stored = localStorage.getItem('discomatic-theme') || 'dark';
  applyTheme(stored);

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-theme-pick]').forEach(function (btn) {
      btn.classList.toggle('active', btn.getAttribute('data-theme-pick') === stored);
    });

    var menuBtn = document.getElementById('menuToggle');
    var menuDrop = document.getElementById('menuDrop');
    if (menuBtn && menuDrop) {
      menuBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        menuDrop.classList.toggle('open');
      });
      document.addEventListener('click', function (e) {
        if (!menuDrop.contains(e.target)) menuDrop.classList.remove('open');
      });
    }
  });
})();
