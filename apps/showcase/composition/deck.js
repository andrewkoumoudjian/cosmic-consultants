/* Analog Atlas deck runtime (standalone slideshow harness).
 *
 * The player seeks window.__timelines.root; this file maps the playhead to one
 * visible scene and plays that scene's entrance on GSAP's own ticker.
 *
 * Motion grammar (motion-doctrine):
 * - One current: forward navigation travels LEFT. Content exits left
 *   (power4.in) and the next scene enters from the right (power4.out), cut
 *   mid-motion, one scene visible at a time (no crossfade).
 * - Going back reverses the current; the Back key is the visible cause.
 * - Inside a slide the frame keeps gaining information: step slides pan the
 *   real screenshot to each focus, ring it, and add its caption.
 * - No idle loops. Reduced motion skips every tween and shows rest states.
 */
(function () {
  'use strict';
  var DECK = window.__DECK;
  var scenes = DECK.scenes;
  var hasGsap = typeof window.gsap !== 'undefined';
  var reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  var EXIT = 0.24;
  var activeIndex = -1;
  var running = null; // entrance timeline of the active scene
  var pendingShow = null;

  function el(id) { return document.getElementById('scene-' + id); }
  function q(root, sel) { return Array.prototype.slice.call(root.querySelectorAll(sel)); }

  function setShown(node, on) {
    node.style.opacity = on ? '1' : '0';
    node.style.visibility = on ? 'visible' : 'hidden';
    node.style.pointerEvents = on ? 'auto' : 'none';
  }

  function indexAt(t) {
    for (var i = 0; i < scenes.length; i++) if (t >= scenes[i].start && t < scenes[i].start + scenes[i].duration) return i;
    return scenes.length - 1;
  }

  // ---------- entrances ----------

  function base(node, dir) {
    var tl = gsap.timeline();
    var anim = q(node, '[data-anim]');
    var glide = q(node, '[data-glide]');
    if (anim.length) tl.fromTo(anim, { x: 80 * dir, opacity: 0 }, { x: 0, opacity: 1, duration: 0.66, ease: 'power4.out', stagger: 0.06 }, 0);
    if (glide.length) tl.fromTo(glide, { x: 170 * dir, opacity: 0 }, { x: 0, opacity: 1, duration: 0.82, ease: 'power4.out', stagger: 0.08 }, 0.08);
    return tl;
  }

  var extras = {
    problem: function (node, tl, dir) {
      var rows = q(node, '.vrow');
      var punch = node.querySelector('[data-punch]');
      gsap.set(rows, { opacity: 0 });
      gsap.set(punch, { opacity: 0 });
      rows.forEach(function (row, i) {
        var at = 0.9 + i * 0.3;
        tl.fromTo(row, { x: 36 * dir, opacity: 0 }, { x: 0, opacity: 1, duration: 0.42, ease: 'power3.out' }, at);
        // the verdict glyph lands a beat after its row: cause, then effect
        tl.fromTo(row.querySelector('.vg'), { scale: 0.4 }, { scale: 1, duration: 0.32, ease: 'back.out(1.6)' }, at + 0.12);
      });
      // stillness before the conclusion, then it rises (upward = conclusion)
      tl.fromTo(punch, { y: 26, opacity: 0 }, { y: 0, opacity: 1, duration: 0.55, ease: 'power3.out' }, 0.9 + rows.length * 0.3 + 0.5);
    },
    approach: function (node, tl) {
      var hx = q(node, '.hx');
      var fit = q(node, '.hx.fit');
      gsap.set(fit, { fill: '#1f2330' });
      tl.fromTo(hx, { opacity: 0, scale: 0.6, transformOrigin: '50% 50%' }, { opacity: 1, scale: 1, duration: 0.4, ease: 'power2.out', stagger: { each: 0.0024, from: 'start' } }, 0.2);
      // the cells that fit the test light up once the grid has landed
      tl.to(fit, { fill: '#a5b4fc', duration: 0.35, ease: 'power2.out', stagger: { each: 0.03, from: 'start' } }, 1.6);
    },
    team: function (node, tl) {
      var people = q(node, '[data-person]');
      tl.fromTo(people, { y: 40, opacity: 0 }, { y: 0, opacity: 1, duration: 0.6, ease: 'power3.out', stagger: 0.08 }, 0.45);
    },
    demo: function (node) {
      var frame = node.querySelector('#demo-app');
      if (frame && !frame.getAttribute('src')) frame.setAttribute('src', frame.getAttribute('data-src'));
    },
  };

  function step(node, tl, dir) {
    var shot = node.querySelector('[data-shot]');
    var rings = q(node, '[data-ring]');
    var caps = q(node, '[data-cap]');
    var H = Number(shot.getAttribute('data-h'));
    var visible = DECK.frameH / DECK.scale; // page px visible in the frame
    gsap.set(shot, { scale: DECK.scale, transformOrigin: '0 0', y: 0 });
    gsap.set(rings, { opacity: 0 });
    gsap.set(caps, { opacity: 0 });
    caps.forEach(function (c) { c.classList.remove('is-past'); });
    var lastY = 0;
    rings.forEach(function (ring, i) {
      var at = 1.3 + i * 2.7;
      var fy = Number(ring.getAttribute('data-y'));
      var target = Math.max(0, Math.min(H - visible, fy - 150));
      if (i > 0) {
        tl.to(rings[i - 1], { opacity: 0, duration: 0.22, ease: 'power2.in' }, at - 0.25);
        tl.call(function () { caps[i - 1].classList.add('is-past'); }, null, at - 0.1);
      }
      var landed = at;
      if (Math.abs(target - lastY) > 4) {
        // camera with intent: travel to the next focus, arrive, then mark it
        tl.to(shot, { y: -target * DECK.scale, duration: 0.95, ease: 'power2.inOut' }, at);
        landed = at + 0.8;
        lastY = target;
      }
      tl.fromTo(ring, { opacity: 0, scale: 1.06, transformOrigin: '50% 50%' }, { opacity: 1, scale: 1, duration: 0.42, ease: 'power3.out' }, landed);
      tl.fromTo(caps[i], { x: 34 * dir, opacity: 0 }, { x: 0, opacity: 1, duration: 0.45, ease: 'power3.out' }, landed);
    });
  }

  function enter(i, dir) {
    var s = scenes[i];
    var node = el(s.id);
    setShown(node, true);
    if (extras.demo && s.id === 'demo') extras.demo(node);
    try { parent.postMessage({ source: 'analog-atlas-deck', type: 'slide', id: s.id, index: i }, '*'); } catch (e) {}
    if (!hasGsap || reduce) return;
    running = base(node, dir);
    if (s.id.indexOf('step-') === 0) step(node, running, dir);
    else if (extras[s.id] && s.id !== 'demo') extras[s.id](node, running, dir);
  }

  function resetScene(node) {
    if (!hasGsap) return;
    var all = q(node, '[data-anim],[data-glide],[data-person],.vrow,.vg,[data-punch],.hx,[data-cap],[data-ring],[data-shot]');
    gsap.killTweensOf(all);
    gsap.set(all, { clearProps: 'transform,opacity' });
    q(node, '.hx.fit').forEach(function (h) { h.style.fill = ''; });
  }

  function go(next) {
    if (next === activeIndex) return;
    var prev = activeIndex;
    var dir = prev < 0 || next > prev ? 1 : -1;
    activeIndex = next;
    if (running) { running.kill(); running = null; }
    if (pendingShow) { pendingShow.kill(); pendingShow = null; }
    // hide everything that isn't the outgoing scene (rapid navigation)
    for (var k = 0; k < scenes.length; k++) if (k !== prev) { setShown(el(scenes[k].id), false); if (k !== next) resetScene(el(scenes[k].id)); }
    if (prev < 0 || !hasGsap || reduce) {
      if (prev >= 0) { setShown(el(scenes[prev].id), false); resetScene(el(scenes[prev].id)); }
      enter(next, dir);
      return;
    }
    var out = el(scenes[prev].id);
    var parts = q(out, '[data-anim],[data-glide],.caps,.people');
    gsap.to(parts, { x: -70 * dir, opacity: 0, duration: EXIT, ease: 'power4.in', overwrite: true });
    pendingShow = gsap.delayedCall(EXIT, function () {
      pendingShow = null;
      setShown(out, false);
      resetScene(out);
      enter(next, dir);
    });
  }

  function update(t) { go(indexAt(t)); }
  window.__hfSetTime = update;
  update(0);

  var root = window.__timelines && window.__timelines.root;
  if (root) root.eventCallback('onUpdate', function () { update(root.time()); });

  // Scene manifest for <hyperframes-slideshow> (standalone harness §5).
  function postTimeline() {
    try {
      parent.postMessage({
        source: 'hf-preview',
        type: 'timeline',
        durationInFrames: DECK.total * 30,
        scenes: scenes.map(function (s) { return { id: s.id, start: s.start, duration: s.duration }; }),
      }, '*');
    } catch (e) {}
  }
  if (document.readyState === 'complete') setTimeout(postTimeline, 300);
  else window.addEventListener('load', function () { setTimeout(postTimeline, 300); });
})();
