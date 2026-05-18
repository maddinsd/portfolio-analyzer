/* Lindner Research Platform — Global Toast Notification System
   All DOM creation uses safe API methods only (no innerHTML, no user-controlled strings). */
(function () {

  function makeSvgEl(paths, viewBox) {
    const NS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('width', '15');
    svg.setAttribute('height', '15');
    svg.setAttribute('viewBox', viewBox || '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    paths.forEach(function(def) {
      var tag = def[0], attrs = def[1];
      var el = document.createElementNS(NS, tag);
      Object.keys(attrs).forEach(function(k) { el.setAttribute(k, attrs[k]); });
      svg.appendChild(el);
    });
    return svg;
  }

  function iconFor(type) {
    if (type === 'success') {
      return makeSvgEl([['polyline', { points: '20 6 9 17 4 12', 'stroke-width': '2.5' }]]);
    }
    if (type === 'error') {
      return makeSvgEl([
        ['circle', { cx: '12', cy: '12', r: '10' }],
        ['line', { x1: '12', y1: '8', x2: '12', y2: '12' }],
        ['line', { x1: '12', y1: '16', x2: '12.01', y2: '16' }],
      ]);
    }
    if (type === 'warning') {
      return makeSvgEl([
        ['path', { d: 'M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z' }],
        ['line', { x1: '12', y1: '9', x2: '12', y2: '13' }],
        ['line', { x1: '12', y1: '17', x2: '12.01', y2: '17' }],
      ]);
    }
    // info (default)
    return makeSvgEl([
      ['circle', { cx: '12', cy: '12', r: '10' }],
      ['line', { x1: '12', y1: '16', x2: '12', y2: '12' }],
      ['line', { x1: '12', y1: '8', x2: '12.01', y2: '8' }],
    ]);
  }

  function closeIcon() {
    var NS = 'http://www.w3.org/2000/svg';
    var svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('width', '11');
    svg.setAttribute('height', '11');
    svg.setAttribute('viewBox', '0 0 16 16');
    svg.setAttribute('fill', 'none');
    var p = document.createElementNS(NS, 'path');
    p.setAttribute('d', 'M3 3l10 10M13 3L3 13');
    p.setAttribute('stroke', 'currentColor');
    p.setAttribute('stroke-width', '1.75');
    p.setAttribute('stroke-linecap', 'round');
    svg.appendChild(p);
    return svg;
  }

  var ToastManager = function() {
    this._active = [];
    this._MAX = 4;
    this._container = null;
    this._queue = [];
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', this._init.bind(this));
    } else {
      this._init();
    }
  };

  ToastManager.prototype._init = function() {
    var el = document.createElement('div');
    el.id = 'toast-container';
    el.setAttribute('role', 'log');
    el.setAttribute('aria-live', 'polite');
    el.setAttribute('aria-atomic', 'false');
    document.body.appendChild(el);
    this._container = el;
    var self = this;
    this._queue.forEach(function(args) { self.show(args[0], args[1], args[2]); });
    this._queue = [];
  };

  ToastManager.prototype.show = function(message, type, duration) {
    type = type || 'info';
    duration = (duration === undefined) ? 4000 : duration;

    if (!this._container) {
      this._queue.push([message, type, duration]);
      return null;
    }

    if (this._active.length >= this._MAX) {
      this._dismiss(this._active[0]);
    }

    var self = this;
    var toast = document.createElement('div');
    toast.className = 'toast toast-' + type;
    toast.setAttribute('role', 'status');

    var iconWrap = document.createElement('span');
    iconWrap.className = 'toast-icon toast-icon-' + type;
    iconWrap.appendChild(iconFor(type));

    var msgEl = document.createElement('span');
    msgEl.className = 'toast-msg';
    msgEl.textContent = message;

    var btn = document.createElement('button');
    btn.className = 'toast-close';
    btn.setAttribute('aria-label', 'Dismiss notification');
    btn.setAttribute('type', 'button');
    btn.appendChild(closeIcon());
    btn.addEventListener('click', function() { self._dismiss(toast); });

    toast.appendChild(iconWrap);
    toast.appendChild(msgEl);
    toast.appendChild(btn);
    this._container.appendChild(toast);
    this._active.push(toast);

    // Two-rAF ensures CSS transition fires after element is in DOM
    requestAnimationFrame(function() {
      requestAnimationFrame(function() { toast.classList.add('toast-in'); });
    });

    if (duration > 0) {
      setTimeout(function() { self._dismiss(toast); }, duration);
    }
    return toast;
  };

  ToastManager.prototype._dismiss = function(toast) {
    if (!toast || !toast.isConnected) return;
    var self = this;
    toast.classList.remove('toast-in');
    toast.classList.add('toast-out');
    setTimeout(function() {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
      self._active = self._active.filter(function(t) { return t !== toast; });
    }, 220);
  };

  ToastManager.prototype.success = function(msg, dur) { return this.show(msg, 'success', dur); };
  ToastManager.prototype.error   = function(msg, dur) { return this.show(msg, 'error',   dur); };
  ToastManager.prototype.warning = function(msg, dur) { return this.show(msg, 'warning', dur); };
  ToastManager.prototype.info    = function(msg, dur) { return this.show(msg, 'info',    dur); };

  window.toast = new ToastManager();
})();
