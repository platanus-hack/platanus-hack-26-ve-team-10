/* @ds-bundle: {"format":4,"namespace":"Prais","components":[{"name":"Wordmark"},{"name":"PraisAvatar"},{"name":"PraisSays"},{"name":"Button"},{"name":"Sticker"},{"name":"Chip"},{"name":"Icon"},{"name":"PriceTag"},{"name":"SearchBox"},{"name":"PriceRange"},{"name":"TrustDots"},{"name":"OfferRow"},{"name":"RankedList"},{"name":"MensajeCanal"},{"name":"IGSlide"},{"name":"FichaOferta"},{"name":"Badge"},{"name":"EstadoPrais"}]} */
(function(){
"use strict";
// Prais — generador del personaje (SVG). Compartido por bundle.js y por los assets.
// c = paleta: {piel, sombra, pelo, ojo, linea, gorra, franela, lapiz, fondo}
function praisSVG(mood, c, opts) {
  opts = opts || {};
  var L = c.linea, W = 3;
  var s = function (d, fill, sw, extra) {
    return '<path d="' + d + '" fill="' + (fill || 'none') + '" stroke="' + L + '" stroke-width="' + (sw || W) + '" stroke-linecap="round" stroke-linejoin="round"' + (extra || '') + '/>';
  };
  var parts = [], extras = [];
  if (opts.fondo) parts.push('<circle cx="80" cy="80" r="78" fill="' + c.fondo + '"/>');
  // Franela y cuello
  parts.push(s('M22 160 C26 130 50 118 80 118 C110 118 134 130 138 160 Z', c.franela));
  parts.push(s('M68 104 L68 121 Q80 129 92 121 L92 104 Z', c.sombra, 2.5));
  parts.push(s('M63 120 Q80 136 97 120', 'none', 2.5));
  // Lápiz detrás de la oreja (de bodeguero)
  parts.push('<g transform="rotate(-38 124 70)">' +
    '<rect x="104" y="66" width="34" height="8" rx="1.5" fill="' + c.lapiz + '" stroke="' + L + '" stroke-width="2.5"/>' +
    s('M138 66 L148 70 L138 74 Z', c.ojo, 2.5) + '</g>');
  // Visera hacia atrás (asoma por la izquierda)
  parts.push(s('M58 40 L26 24 Q19 25 23 33 L46 50 Z', c.gorra));
  // Orejas
  parts.push(s('M47 80 Q36 78 37 90 Q38 100 49 98', c.piel, 2.5));
  parts.push(s('M113 80 Q124 78 123 90 Q122 100 111 98', c.piel, 2.5));
  // Cabeza
  parts.push('<ellipse cx="80" cy="84" rx="35" ry="38" fill="' + c.piel + '" stroke="' + L + '" stroke-width="' + W + '"/>');
  // Patillas
  parts.push('<path d="M45.5 70 L52 70 L52 88 Q47 86 46 79 Z" fill="' + c.pelo + '"/>');
  parts.push('<path d="M114.5 70 L108 70 L108 88 Q113 86 114 79 Z" fill="' + c.pelo + '"/>');
  // Gorra
  parts.push(s('M43 72 C42 42 60 30 80 30 C100 30 118 42 117 72 Q80 61 43 72 Z', c.gorra));
  parts.push(s('M70 69 Q80 52 90 69', c.pelo, 2.5));
  parts.push('<circle cx="80" cy="31" r="3.5" fill="' + L + '"/>');
  parts.push(s('M60 38 Q64 52 62 66', 'none', 2));
  parts.push(s('M100 38 Q96 52 98 66', 'none', 2));
  // Nariz y chivita
  parts.push('<path d="M80 92 Q76 100 81.5 101.5" fill="none" stroke="' + c.sombra + '" stroke-width="2.6" stroke-linecap="round"/>');
  parts.push('<path d="M75 118 Q80 122.5 85 118 Q80 120 75 118 Z" fill="' + c.pelo + '" stroke="' + c.pelo + '" stroke-width="2" stroke-linejoin="round"/>');

  var eye = function (cx, cy, px, py, r) {
    return '<ellipse cx="' + cx + '" cy="' + cy + '" rx="' + (r || 6.5) + '" ry="' + ((r || 6.5) + 0.8) + '" fill="' + c.ojo + '" stroke="' + L + '" stroke-width="2.5"/>' +
      '<circle cx="' + px + '" cy="' + py + '" r="3.2" fill="' + L + '"/>';
  };
  var brow = function (d) { return '<path d="' + d + '" fill="none" stroke="' + c.pelo + '" stroke-width="4.5" stroke-linecap="round"/>'; };

  if (mood === 'ganga') {
    parts.push(s('M59 89 Q66 80 73 89', 'none', 3.5));
    parts.push(s('M87 89 Q94 80 101 89', 'none', 3.5));
    parts.push(brow('M57 72 Q65 66 73 70'));
    parts.push(brow('M87 70 Q95 66 103 72'));
    parts.push(s('M65 103 Q80 101 95 103 Q93 119 80 119 Q67 119 65 103 Z', L, 2.5));
    parts.push('<path d="M68 104 L92 104 L91 108.5 L69 108.5 Z" fill="' + c.ojo + '"/>');
    // Destello
    extras.push(s('M140 30 L143 39 L152 42 L143 45 L140 54 L137 45 L128 42 L137 39 Z', c.gorra, 2.5));
  } else if (mood === 'pilas') {
    parts.push(eye(66, 88, 67, 89, 7.2));
    parts.push(eye(94, 88, 95, 89, 7.2));
    parts.push(brow('M57 74 Q64 64 73 70'));
    parts.push(brow('M87 77 L103 73'));
    parts.push(s('M69 108 Q77 105 91 109', 'none', 3));
    // Gota de "ojo con eso"
    extras.push(s('M124 46 Q131 56 128 61 Q124 65 120 61 Q118 56 124 46 Z', c.ojo, 2.5));
  } else if (mood === 'pensando') {
    parts.push(eye(66, 88, 69, 85));
    parts.push(eye(94, 88, 97, 85));
    parts.push(brow('M58 75 Q66 72 73 75'));
    parts.push(brow('M87 72 Q95 66 103 70'));
    parts.push(s('M73 109 Q80 106 87 109', 'none', 3));
    extras.push('<circle cx="130" cy="44" r="3.5" fill="' + c.ojo + '" stroke="' + L + '" stroke-width="2.2"/>');
    extras.push('<circle cx="140" cy="32" r="5" fill="' + c.ojo + '" stroke="' + L + '" stroke-width="2.2"/>');
    extras.push('<circle cx="151" cy="17" r="6.5" fill="' + c.ojo + '" stroke="' + L + '" stroke-width="2.2"/>');
  } else { // tranqui
    parts.push(eye(66, 88, 67, 89));
    parts.push(eye(94, 88, 95, 89));
    parts.push('<path d="M59 86 Q66 83 73 86 L73 82 Q66 79 59 82 Z" fill="' + c.piel + '"/>');
    parts.push('<path d="M87 86 Q94 83 101 86 L101 82 Q94 79 87 82 Z" fill="' + c.piel + '"/>');
    parts.push(s('M59 85.5 Q66 82.5 73 85.5', 'none', 2.5));
    parts.push(s('M87 85.5 Q94 82.5 101 85.5', 'none', 2.5));
    parts.push(brow('M58 75 Q66 71 73 74'));
    parts.push(brow('M87 74 Q94 71 102 75'));
    parts.push(s('M68 105 Q79 114 93 103', 'none', 3));
    parts.push(s('M91 101 Q94 103 95 106', 'none', 2.2));
  }
  var inner = parts.join('');
  if (opts.fondo) {
    var id = 'pc' + (opts.id || Math.random().toString(36).slice(2, 8));
    inner = '<defs><clipPath id="' + id + '"><circle cx="80" cy="80" r="78"/></clipPath></defs>' +
      '<g clip-path="url(#' + id + ')">' + inner + '</g>' +
      '<circle cx="80" cy="80" r="77" fill="none" stroke="' + L + '" stroke-width="3"/>';
  }
  inner += extras.join('');
  if (opts.inner) return inner;
  var t = opts.title ? '<title>' + opts.title + '</title>' : '';
  return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 160" role="img">' + t + inner + '</svg>';
}

// Isotipo: la etiqueta de precio con la gorra de Prais
function isotipoSVG(c) {
  var L = c.linea;
  return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 160" role="img"><title>usaprais</title>' +
    '<g transform="rotate(-10 80 90)">' +
    '<path d="M30 68 L62 40 L134 40 Q142 40 142 48 L142 132 Q142 140 134 140 L62 140 L30 112 Z" fill="' + c.tag + '" stroke="' + L + '" stroke-width="5" stroke-linejoin="round"/>' +
    '<circle cx="52" cy="90" r="9" fill="' + c.fondo + '" stroke="' + L + '" stroke-width="5"/>' +
    '<path d="M84 76 L120 76 M84 96 L128 96 M84 116 L108 116" stroke="' + L + '" stroke-width="7" stroke-linecap="round"/>' +
    '</g>' +
    '<g transform="rotate(-10 80 90) translate(46 -6)">' +
    '<path d="M56 30 L82 18 Q88 18 85 25 L66 40 Z" fill="' + c.gorra + '" stroke="' + L + '" stroke-width="4.5" stroke-linejoin="round"/>' +
    '<path d="M22 46 C22 24 36 14 50 14 C64 14 78 24 78 46 Q50 38 22 46 Z" fill="' + c.gorra + '" stroke="' + L + '" stroke-width="4.5" stroke-linejoin="round"/>' +
    '<circle cx="50" cy="15" r="3.5" fill="' + L + '"/>' +
    '</g></svg>';
}


var R = window.React, h = R.createElement;

function cx() { return Array.prototype.filter.call(arguments, Boolean).join(' '); }
function omit(o, keys) { var r = {}; for (var k in o) if (keys.indexOf(k) < 0) r[k] = o[k]; return r; }

// ---------- Números en formato venezolano: punto de miles, coma decimal ----------
function num(n, dec) {
  var neg = n < 0; n = Math.abs(n);
  var s = n.toFixed(dec), p = s.split('.');
  var ent = p[0].replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  return (neg ? '−' : '') + ent + (dec ? ',' + p[1] : '');
}
function usd(n) { if (n == null || isNaN(n)) return '—'; var d = Math.round(Math.abs(n) * 100) % 100 === 0 ? 0 : 2; return (n < 0 ? '−' : '') + '$' + num(Math.abs(n), d); }
function bs(n) { if (n == null || isNaN(n)) return '—'; return 'Bs. ' + num(n, 2); }
function total(o) { return (o.usd || 0) + (o.envio || 0); }

// ---------- Prais ----------
var PRAIS = { piel: '#c68650', sombra: '#9a5f33', pelo: '#24170e', ojo: '#fffaf1', linea: '#1f1a14', gorra: '#ffc829', franela: '#e8402a', lapiz: '#2a4bd7', fondo: 'none' };
var MOODS = { tranqui: 'Prais, tranquilo', ganga: 'Prais, contento: encontró un buen precio', pilas: 'Prais, alerta: ese precio está caro', pensando: 'Prais, buscando precios' };

function PraisAvatar(p) {
  var mood = MOODS[p.mood] ? p.mood : 'tranqui';
  var size = p.size || 96, ground = p.ground !== false;
  var uid = R.useId().replace(/[^a-zA-Z0-9]/g, '');
  var svg = praisSVG(mood, PRAIS, { fondo: ground, id: uid, inner: true });
  return h('span', { className: cx('up-avatar', ground && 'up-avatar-ground', p.className), style: { width: size, height: size }, role: 'img', 'aria-label': p.title || MOODS[mood] },
    h('svg', { viewBox: '0 0 160 160', width: size, height: size, 'aria-hidden': true, dangerouslySetInnerHTML: { __html: svg } }));
}


// ---------- Íconos propios (24px, trazo 2.25, puntas redondas) ----------
var ICONS = {
  buscar: '<circle cx="11" cy="11" r="7"/><path d="M16.5 16.5 L21 21"/>',
  flecha: '<path d="M4 12 H19 M13 6 L19 12 L13 18"/>',
  enlace: '<path d="M10 14 L14 10"/><path d="M8.5 11.5 L6 14 A3.5 3.5 0 0 0 11 19 L13.5 16.5"/><path d="M15.5 12.5 L18 10 A3.5 3.5 0 0 0 13 5 L10.5 7.5"/>',
  check: '<path d="M5 12.5 L10 17.5 L19 7"/>',
  alerta: '<path d="M12 3.5 L21.5 20 H2.5 Z"/><path d="M12 10 V14"/><path d="M12 17 V17.2"/>',
  envio: '<rect x="2.5" y="6" width="11.5" height="10" rx="1"/><path d="M14 9.5 H18 L21.5 13 V16 H14"/><circle cx="7" cy="17.5" r="2"/><circle cx="17.5" cy="17.5" r="2"/>',
  escudo: '<path d="M12 3 L20 6 V12 C20 16.5 16.5 19.5 12 21 C7.5 19.5 4 16.5 4 12 V6 Z"/><path d="M8.5 12 L11 14.5 L15.5 9.5"/>',
  tienda: '<path d="M3.5 9 L5.5 4 H18.5 L20.5 9 Z"/><path d="M4.5 9 V20 H19.5 V9"/><path d="M9.5 20 V14.5 H14.5 V20"/>',
  compartir: '<path d="M12 3.5 V15"/><path d="M7 8.5 L12 3.5 L17 8.5"/><path d="M5 13 V20 H19 V13"/>',
  reloj: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5 V12 L15 14"/>',
  volver: '<path d="M20 12 H5 M11 6 L5 12 L11 18"/>',
  imagen: '<rect x="3" y="4.5" width="18" height="15" rx="2"/><circle cx="9" cy="10" r="1.8"/><path d="M4 18 L10 13 L14 16 L17 13.5 L20.5 16.5"/>',
  chevron: '<path d="M9 5 L16 12 L9 19"/>',
  usuario: '<circle cx="12" cy="8.5" r="3.8"/><path d="M4.5 20 C5.5 15.5 8.5 14 12 14 C15.5 14 18.5 15.5 19.5 20"/>'
};
function Icon(p) {
  var d = ICONS[p.name] || '';
  var s = p.size || 20;
  return h('svg', { className: cx('up-icon', p.className), viewBox: '0 0 24 24', width: s, height: s, fill: 'none', stroke: 'currentColor', strokeWidth: 2.25, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': p.label ? undefined : true, role: p.label ? 'img' : undefined, 'aria-label': p.label, dangerouslySetInnerHTML: { __html: d } });
}

// ---------- Marca ----------
function Wordmark(p) {
  var size = p.size || 'md';
  return h('span', { className: cx('up-wordmark', 'up-wordmark-' + size, p.className), role: 'img', 'aria-label': 'usaprais' + (p.dotcom ? '.com' : '') },
    h('span', { className: 'up-wordmark-usa', 'aria-hidden': true }, 'usa'),
    h('span', { className: 'up-wordmark-tag', 'aria-hidden': true }, 'prais'),
    p.dotcom ? h('span', { className: 'up-wordmark-com', 'aria-hidden': true }, '.com') : null);
}

// ---------- Acciones ----------
function Button(p) {
  var v = p.variant || 'primario', size = p.size || 'md';
  var rest = omit(p, ['variant', 'size', 'icon', 'iconRight', 'className', 'children']);
  return h('button', Object.assign({ type: 'button' }, rest, { className: cx('up-btn', 'up-btn-' + v, 'up-btn-' + size, p.className) }),
    p.icon ? h(Icon, { name: p.icon, size: size === 'lg' ? 22 : 18 }) : null,
    h('span', null, p.children),
    p.iconRight ? h(Icon, { name: p.iconRight, size: size === 'lg' ? 22 : 18 }) : null);
}

function Sticker(p) {
  var tone = p.tone || 'sol';
  var tilt = p.tilt == null ? -3 : p.tilt;
  return h('span', { className: cx('up-sticker', 'up-sticker-' + tone, p.className), style: { transform: 'rotate(' + tilt + 'deg)' } },
    p.icon ? h(Icon, { name: p.icon, size: 14 }) : null,
    h('span', null, p.children));
}

function Chip(p) {
  return h('span', { className: cx('up-chip', p.className) }, p.icon ? h(Icon, { name: p.icon, size: 14 }) : null, p.children);
}

// ---------- Precio ----------

// ---------- Búsqueda ----------
function SearchBox(p) {
  var st = R.useState(p.defaultValue || ''), v = st[0], set = st[1];
  var id = R.useId();
  return h('form', { className: cx('up-search', p.className), role: 'search', onSubmit: function (e) { e.preventDefault(); if (p.onSubmit) p.onSubmit(v); } },
    h('label', { className: 'up-search-label', htmlFor: id }, p.label || '¿Qué vas a comprar?'),
    h('div', { className: 'up-search-row' },
      h('span', { className: 'up-search-icon' }, h(Icon, { name: 'buscar', size: 20 })),
      h('input', { id: id, className: 'up-search-input', value: v, onChange: function (e) { set(e.target.value); }, placeholder: p.placeholder || 'Pega el link o escribe el producto', autoComplete: 'off' }),
      h(Button, { type: 'submit', variant: 'primario', iconRight: 'flecha' }, p.cta || 'Buscar precios')),
    p.hint ? h('p', { className: 'up-search-hint' }, p.hint) : null);
}

// ---------- Rango de precios ----------
function veredicto(valor, promedio) {
  if (valor <= promedio * 0.95) return 'barato';
  if (valor <= promedio * 1.05) return 'normal';
  return 'caro';
}
var VEREDICTO = { barato: 'Buen precio', normal: 'Precio normal', caro: 'Está caro' };


// ---------- Ofertas ----------



// ---------- Canales: el mismo resultado, en el formato nativo de cada uno ----------
var CANALES = { whatsapp: 'WhatsApp · Flow / mensaje', x: 'X · respuesta en el hilo', instagram: 'Instagram · DM' };

function textoParaCanal(canal, d) {
  var of = (d.ofertas || []).slice().sort(function (a, b) { return total(a) - total(b); });
  var prom = d.promedio != null ? d.promedio : of.reduce(function (s, o) { return s + total(o); }, 0) / Math.max(1, of.length);
  var top = of[0] || {}, ah = prom - total(top);
  var pb = function (o) { return usd(total(o)) + (d.tasa ? ' (' + bs(total(o) * d.tasa) + ')' : ''); };
  var link = d.enlace || 'usaprais.com';
  if (canal === 'x') {
    var t = d.producto + ': el más barato que encontré está en ' + top.tienda + ' a ' + usd(total(top)) + ' con envío, ' + usd(ah) + ' menos que el promedio. Top ' + Math.min(5, of.length) + ' y fuentes → ' + link;
    return t.length > 280 ? t.slice(0, 277) + '…' : t;
  }
  if (canal === 'instagram') {
    return 'Listo. Revisé ' + of.length + ' tiendas para ' + d.producto + '.\n\n' +
      'La mejor opción: ' + top.tienda + ', ' + pb(top) + ' con envío. Son ' + usd(ah) + ' menos que el promedio.\n\n' +
      'Te mandé el carrusel con el top ' + Math.min(5, of.length) + '. Desliza para ver dónde y a cuánto.';
  }
  var lines = of.slice(0, 3).map(function (o, i) {
    var m = [o.canal, o.condicion, o.envio ? 'envío ' + usd(o.envio) : o.envio === 0 ? 'envío gratis' : null].filter(Boolean).join(' · ');
    return (i + 1) + '. *' + o.tienda + '* — ' + pb(o) + (m ? '\n    ' + m : '');
  });
  return '*' + d.producto + '*\nRevisé ' + of.length + ' tiendas. Estos son los 3 precios más bajos con envío incluido:\n\n' +
    lines.join('\n') + '\n\nEl mejor está ' + usd(ah) + ' por debajo del promedio (' + usd(prom) + ').\nLista completa: ' + link;
}

function renderWA(text) {
  return text.split(/(\*[^*\n]+\*)/g).map(function (part, i) {
    return /^\*[^*]+\*$/.test(part) ? h('strong', { key: i }, part.slice(1, -1)) : part;
  });
}

function MensajeCanal(p) {
  var canal = CANALES[p.canal] ? p.canal : 'whatsapp';
  var text = p.texto || textoParaCanal(canal, p);
  return h('figure', { className: cx('up-msg', 'up-msg-' + canal, p.className) },
    h('figcaption', { className: 'up-msg-head' },
      h(PraisAvatar, { mood: p.mood || 'ganga', size: 32 }),
      h('span', { className: 'up-msg-who' }, canal === 'x' ? '@usaprais' : 'Prais · usaprais'),
      h('span', { className: 'up-msg-channel' }, CANALES[canal])),
    h('div', { className: 'up-msg-bubble' }, canal === 'whatsapp' ? renderWA(text) : text),
    canal === 'x' ? h('span', { className: cx('up-msg-count', text.length > 280 && 'over') }, text.length + ' / 280') : null);
}

var IG_TEXTO = { portada: 'Portada', oferta: 'Oferta', cierre: 'Cierre' };
function IGSlide(p) {
  var tipo = IG_TEXTO[p.tipo] ? p.tipo : 'portada';
  var w = p.ancho || 270, k = w / 1080;
  var o = p.oferta || {};
  var body;
  if (tipo === 'portada') {
    body = [
      h('div', { key: 'wm', className: 'up-ig-wm' }, h(Wordmark, { size: 'xl' })),
      h('p', { key: 'k', className: 'up-ig-kicker' }, p.kicker || 'Le preguntamos a Prais por'),
      h('h2', { key: 't', className: 'up-ig-title' }, p.producto),
      h('div', { key: 's', className: 'up-ig-stk' }, h(Sticker, { tone: 'normal', tilt: -5 }, (p.revisados || 0) + ' precios revisados')),
      h('div', { key: 'a', className: 'up-ig-avatar' }, h(PraisAvatar, { mood: 'pilas', size: 520, ground: false })),
      h('p', { key: 'n', className: 'up-ig-next' }, 'Desliza', h(Icon, { name: 'flecha', size: 44 }))
    ];
  } else if (tipo === 'oferta') {
    body = [
      h('div', { key: 'r', className: 'up-ig-rank' }, '#' + (p.rank || 1)),
      p.rank === 1 ? h('div', { key: 'f', className: 'up-ig-flag' }, h(Sticker, { tone: 'sol', tilt: 4 }, 'Más barato')) : null,
      h('p', { key: 'st', className: 'up-ig-store' }, o.tienda),
      h('p', { key: 'c', className: 'up-ig-canal' }, [o.canal, o.ubicacion].filter(Boolean).join(' · ')),
      h('div', { key: 'p', className: 'up-ig-price' }, usd(total(o))),
      p.tasa ? h('div', { key: 'b', className: 'up-ig-bs' }, bs(total(o) * p.tasa)) : null,
      h('p', { key: 'm', className: 'up-ig-meta' }, [o.envio ? 'Envío ' + usd(o.envio) + ' incluido' : o.envio === 0 ? 'Envío gratis' : null, o.condicion, o.garantia ? 'Garantía ' + o.garantia : null].filter(Boolean).join(' · ')),
      p.ahorro ? h('div', { key: 'ah', className: 'up-ig-ahorro' }, h(Sticker, { tone: 'barato', tilt: -3 }, 'Ahorras ' + usd(p.ahorro))) : null,
      h('div', { key: 'wm', className: 'up-ig-foot' }, h(Wordmark, { size: 'md', dotcom: true }), h('span', null, (p.rank || 1) + ' / ' + (p.de || 5)))
    ];
  } else {
    body = [
      h('h2', { key: 't', className: 'up-ig-close' }, p.titulo || '¿Vas a comprar algo?'),
      h('p', { key: 'p', className: 'up-ig-close-sub' }, p.subtitulo || 'Mándale el link a Prais antes de pagar. Te dice si hay un precio mejor.'),
      h('div', { key: 'a', className: 'up-ig-close-avatar' }, h(PraisAvatar, { mood: 'ganga', size: 460 })),
      h('div', { key: 'wm', className: 'up-ig-close-wm' }, h(Wordmark, { size: 'xl', dotcom: true }))
    ];
  }
  return h('div', { className: cx('up-ig-frame', p.className), style: { width: w, height: w * 1350 / 1080 } },
    h('div', { className: cx('up-ig', 'up-ig-' + tipo), style: { transform: 'scale(' + k + ')' } }, body));
}

// ---------- Ficha de oferta (móvil primero) ----------

// ================= Capa de producto: componentes sobrios =================

function Badge(p) {
  var tone = p.tone || 'neutro';
  return h('span', { className: cx('up-badge', 'up-badge-' + tone, p.className) },
    p.icon ? h(Icon, { name: p.icon, size: 13 }) : null, p.children);
}
var VEREDICTO_TONO = { barato: 'barato', normal: 'neutro', caro: 'caro' };

function PraisSays(p) {
  return h('div', { className: cx('up-says', p.className) },
    h(PraisAvatar, { mood: p.mood, size: p.avatarSize || 36 }),
    h('p', { className: 'up-says-text' }, p.children));
}

function PriceTag(p) {
  var size = p.size || 'md';
  return h('span', { className: cx('up-price', 'up-price-' + size, p.marca && 'up-price-marca', p.align === 'left' && 'up-price-left', p.className) },
    p.label ? h('span', { className: 'up-price-label' }, p.label) : null,
    p.antes != null ? h('s', { className: 'up-price-antes' }, usd(p.antes)) : null,
    h('span', { className: 'up-price-usd' }, usd(p.usd)),
    p.tasa ? h('span', { className: 'up-price-bs', title: 'Calculado a ' + bs(p.tasa) + ' por dólar' }, bs(p.usd * p.tasa)) : null);
}

function PriceRange(p) {
  var min = p.min, max = p.max, prom = p.promedio, val = p.valor;
  var span = Math.max(max - min, 0.0001);
  var pos = function (x) { return Math.max(0, Math.min(100, (x - min) / span * 100)); };
  var b1 = pos(prom * 0.95), b2 = pos(prom * 1.05);
  var ver = val != null ? veredicto(val, prom) : null;
  var pin = function (x) { return { left: pos(x) + '%' }; };
  var align = function (x) { var q = pos(x); return q < 14 ? 'start' : q > 86 ? 'end' : 'center'; };
  return h('div', { className: cx('up-range', p.className) },
    h('div', { className: 'up-range-head' },
      h('span', { className: 'up-range-title' }, p.titulo || 'Dónde cae este precio'),
      ver && p.badge !== false ? h(Badge, { tone: VEREDICTO_TONO[ver], icon: ver === 'caro' ? 'alerta' : ver === 'barato' ? 'check' : null }, VEREDICTO[ver]) : null),
    h('div', { className: 'up-range-track-wrap' },
      val != null ? h('span', { className: 'up-range-pin-label up-range-' + align(val), style: pin(val) }, (p.etiquetaValor || 'Tu precio') + ' ', h('b', null, usd(val))) : null,
      h('div', { className: 'up-range-track', role: 'img', 'aria-label': 'Precios desde ' + usd(min) + ' hasta ' + usd(max) + ', promedio ' + usd(prom) + (val != null ? ', tu precio ' + usd(val) : '') },
        h('span', { className: 'up-range-zone up-range-zone-barato', style: { left: 0, width: b1 + '%' } }),
        h('span', { className: 'up-range-zone up-range-zone-normal', style: { left: b1 + '%', width: (b2 - b1) + '%' } }),
        h('span', { className: 'up-range-zone up-range-zone-caro', style: { left: b2 + '%', width: (100 - b2) + '%' } }),
        h('span', { className: 'up-range-avg', style: pin(prom) })),
      val != null ? h('span', { className: 'up-range-pin-dot', style: pin(val) }) : null),
    h('div', { className: 'up-range-ends' },
      h('span', null, usd(min), ' más bajo'),
      h('span', null, 'Promedio ', h('b', null, usd(prom))),
      h('span', null, usd(max), ' más alto')));
}

function confianzaTexto(n) { return n >= 4 ? 'Vendedor confiable' : n >= 3 ? 'Buenas referencias' : n >= 1 ? 'Pocas referencias' : 'Sin referencias'; }

function TrustDots(p) {
  var n = Math.max(0, Math.min(5, p.value || 0));
  var label = confianzaTexto(n);
  var dots = [];
  for (var i = 0; i < 5; i++) dots.push(h('span', { key: i, className: cx('up-trust-dot', i < n && 'on') }));
  return h('span', { className: cx('up-trust', n <= 2 && 'up-trust-baja'), 'aria-label': label + ' (' + n + ' de 5)', role: 'img' },
    h('span', { className: 'up-trust-dots', 'aria-hidden': true }, dots), h('span', { className: 'up-trust-label', 'aria-hidden': true }, label));
}

function metaOferta(o, corto) {
  return [o.envio == null ? 'Envío por confirmar' : o.envio === 0 ? 'Envío gratis' : 'Envío ' + usd(o.envio), o.condicion, o.garantia ? 'Garantía ' + o.garantia : null, corto ? null : o.ubicacion].filter(Boolean).join(' · ');
}

function OfferRow(p) {
  var t = total(p);
  var diff = p.promedio != null ? p.promedio - t : null;
  var baja = p.confianza != null && p.confianza <= 2;
  var Tag = p.onAbrir ? 'button' : 'article';
  var props = { className: cx('up-offer', p.destacado && 'up-offer-top', p.onAbrir && 'up-offer-btn', p.className) };
  if (p.onAbrir) { props.type = 'button'; props.onClick = p.onAbrir; }
  return h('div', { className: 'up-offer-c' }, h(Tag, props,
    h('span', { className: 'up-offer-rank', 'aria-label': 'Puesto ' + p.rank }, p.rank),
    h('span', { className: 'up-offer-main' },
      p.destacado ? h(Badge, { tone: 'destacado', className: 'up-offer-flag' }, p.flag || 'Más barato') : null,
      h('span', { className: 'up-offer-store' },
        h('span', { className: 'up-offer-name' }, p.tienda),
        p.canal ? h('span', { className: 'up-offer-canal' }, p.canal) : null),
      h('span', { className: 'up-offer-meta' }, metaOferta(p, true)),
      p.confianza != null ? h('span', { className: cx('up-offer-trust', baja && 'baja') },
        h(Icon, { name: baja ? 'alerta' : 'escudo', size: 15 }), confianzaTexto(p.confianza)) : null),
    h('span', { className: 'up-offer-side' },
      h(PriceTag, { usd: t, tasa: p.tasa, size: 'md' }),
      diff != null && Math.abs(diff) >= 0.5 ? h('span', { className: cx('up-offer-diff', diff > 0 ? 'menos' : 'mas') },
        diff > 0 ? 'Ahorras ' + usd(diff) : '+' + usd(-diff) + ' vs. promedio') : null),
    p.onAbrir ? h(Icon, { name: 'chevron', size: 18, className: 'up-offer-chev' }) : null));
}

function RankedList(p) {
  var ofertas = (p.ofertas || []).slice().sort(function (a, b) { return total(a) - total(b); });
  var prom = p.promedio != null ? p.promedio : (ofertas.reduce(function (s, o) { return s + total(o); }, 0) / Math.max(1, ofertas.length));
  var head = [ofertas.length + ' precios', 'ordenados por total con envío'];
  if (p.tasa) head.push('tasa ' + bs(p.tasa));
  return h('section', { className: cx('up-list', p.className) },
    h('header', { className: 'up-list-head' },
      p.producto ? h('h2', { className: 'up-list-title' }, p.producto) : null,
      h('p', { className: 'up-list-meta' }, head.join(' · '))),
    h('ol', { className: 'up-list-items' }, ofertas.map(function (o, i) {
      return h('li', { key: o.tienda + i }, h(OfferRow, Object.assign({}, o, { rank: i + 1, tasa: p.tasa, promedio: prom, destacado: i === 0 })));
    })),
    p.actualizado ? h('p', { className: 'up-list-foot' }, h(Icon, { name: 'reloj', size: 14 }), 'Revisado ' + p.actualizado + ' · Confirma con la tienda antes de pagar.') : null);
}

function FichaOferta(p) {
  var o = p.oferta || {}, t = total(o), v = o.vendedor || {};
  var prom = p.promedio, ver = prom != null ? veredicto(t, prom) : null;
  var diff = prom != null ? prom - t : null;
  var revis = p.revisiones || [];
  var mejor = p.mejor;
  var baja = o.confianza != null && o.confianza <= 2;
  return h('article', { className: cx('up-ficha', p.className) },
    h('header', { className: 'up-bar' },
      h('button', { type: 'button', className: 'up-bar-btn', onClick: p.onVolver, 'aria-label': 'Volver a la lista' }, h(Icon, { name: 'volver', size: 22 })),
      h('span', { className: 'up-bar-title' }, p.producto),
      p.rank ? h('span', { className: 'up-bar-aux' }, p.rank + ' de ' + (p.de || p.rank)) : null),
    h('div', { className: 'up-ficha-foto' },
      o.foto ? h('img', { src: o.foto, alt: 'Foto del anuncio' }) : h('span', { className: 'up-ficha-foto-ph' }, h(Icon, { name: 'imagen', size: 32 }))),
    h('div', { className: 'up-ficha-body' },
      h('div', { className: 'up-ficha-head' },
        h('div', { className: 'up-ficha-badges' },
          p.rank === 1 ? h(Badge, { tone: 'destacado' }, 'Más barato') : ver ? h(Badge, { tone: VEREDICTO_TONO[ver], icon: ver === 'caro' ? 'alerta' : ver === 'barato' ? 'check' : null }, VEREDICTO[ver]) : null,
          o.canal ? h(Badge, { tone: 'neutro' }, o.canal) : null,
          o.publicado ? h('span', { className: 'up-ficha-fecha' }, o.publicado) : null),
        h('h1', { className: 'up-ficha-store' }, o.tienda),
        h(PriceTag, { usd: t, tasa: p.tasa, size: 'lg', align: 'left' }),
        h('p', { className: 'up-ficha-meta' }, metaOferta(o)),
        diff != null && Math.abs(diff) >= 0.5 ? h('p', { className: cx('up-ficha-diff', diff > 0 ? 'menos' : 'mas') },
          diff > 0 ? usd(diff) + ' por debajo del promedio de ' + usd(prom) : usd(-diff) + ' por encima del promedio de ' + usd(prom)) : null),
      revis.length ? h('section', { className: 'up-ficha-sec' },
        h('h2', { className: 'up-ficha-h' }, h(PraisAvatar, { mood: baja ? 'pilas' : 'tranqui', size: 28 }), 'Lo que revisó Prais'),
        h('ul', { className: 'up-ficha-checks' }, revis.map(function (r, i) {
          return h('li', { key: i, className: 'up-ficha-check ' + (r.tono === 'ojo' ? 'ojo' : 'ok') },
            h(Icon, { name: r.tono === 'ojo' ? 'alerta' : 'check', size: 17, label: r.tono === 'ojo' ? 'Atención' : 'Bien' }), h('span', null, r.texto));
        })),
        p.consejo ? h('p', { className: 'up-ficha-consejo' }, p.consejo) : null) : null,
      h('section', { className: 'up-ficha-sec' },
        h('h2', { className: 'up-ficha-h' }, 'Vendedor'),
        h('div', { className: 'up-ficha-seller' },
          h('span', { className: 'up-ficha-seller-icon' }, h(Icon, { name: v.tipo === 'Tienda' ? 'tienda' : 'usuario', size: 20 })),
          h('span', { className: 'up-ficha-seller-txt' },
            h('b', null, v.nombre || o.tienda),
            h('span', null, [v.tipo, v.desde ? 'desde ' + v.desde : null, v.referencias != null ? v.referencias + ' referencias' : null].filter(Boolean).join(' · '))),
          o.confianza != null ? h(TrustDots, { value: o.confianza }) : null)),
      mejor ? h('section', { className: 'up-ficha-sec' },
        h('h2', { className: 'up-ficha-h' }, p.masBaratas === 1 ? 'Hay 1 opción más barata' : 'Hay ' + (p.masBaratas || 1) + ' opciones más baratas'),
        h('button', { type: 'button', className: 'up-ficha-mejor', onClick: p.onVerMejor },
          h('span', { className: 'up-ficha-seller-txt' }, h('b', null, mejor.tienda), h('span', null, [mejor.canal, metaOferta(mejor).split(' · ')[0]].filter(Boolean).join(' · '))),
          h(PriceTag, { usd: total(mejor), size: 'sm' }),
          h(Icon, { name: 'chevron', size: 18 }))) : null,
      h('p', { className: 'up-ficha-legal' }, 'usaprais no vende ni cobra por este anuncio. La compra la acuerdas con el vendedor.')),
    h('footer', { className: 'up-ficha-cta' },
      h(Button, { variant: 'primario', size: 'lg', iconRight: 'enlace', onClick: p.onIr, className: 'up-ficha-ir' }, 'Ir al anuncio'),
      h(Button, { variant: 'secundario', size: 'lg', icon: 'compartir', onClick: p.onCompartir, 'aria-label': 'Compartir' })));
}

var ESTADOS = {
  cargando: { mood: 'pensando', titulo: 'Buscando precios…', texto: 'Estoy revisando tiendas de Instagram, Mercado Libre, Marketplace y la web.' },
  vacio: { mood: 'tranqui', titulo: 'No encontré ese producto en otras tiendas', texto: 'Prueba con el nombre exacto del modelo o pega el link del anuncio.' },
  error: { mood: 'pensando', titulo: 'Algo falló de mi lado', texto: 'No es tu conexión. Inténtalo otra vez en un momento.' }
};
function EstadoPrais(p) {
  var e = ESTADOS[p.tipo] || ESTADOS.vacio;
  return h('div', { className: cx('up-estado', p.className), role: p.tipo === 'cargando' ? 'status' : null },
    h(PraisAvatar, { mood: p.mood || e.mood, size: p.size || 112 }),
    h('p', { className: 'up-estado-titulo' }, p.titulo || e.titulo),
    h('p', { className: 'up-estado-texto' }, p.texto || e.texto),
    p.tipo === 'cargando' ? h('span', { className: 'up-estado-barra', 'aria-hidden': true }, h('span', null)) : null,
    p.accion ? h(Button, { variant: 'secundario', onClick: p.onAccion }, p.accion) : null);
}

var api = {Wordmark:Wordmark,PraisAvatar:PraisAvatar,PraisSays:PraisSays,Button:Button,Sticker:Sticker,Chip:Chip,Icon:Icon,PriceTag:PriceTag,SearchBox:SearchBox,PriceRange:PriceRange,TrustDots:TrustDots,OfferRow:OfferRow,RankedList:RankedList,MensajeCanal:MensajeCanal,IGSlide:IGSlide,FichaOferta:FichaOferta,Badge:Badge,EstadoPrais:EstadoPrais,textoParaCanal:textoParaCanal,veredicto:veredicto,formato:{usd:usd,bs:bs,num:num},praisSVG:praisSVG,isotipoSVG:isotipoSVG};
window.Prais = Object.assign(window.Prais || {}, api);
})();
