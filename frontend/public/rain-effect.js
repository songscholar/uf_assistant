(function() {
  'use strict';

  var canvas, gl, prog, u, texture, bgCanvas;
  var rafId;
  var startTime = performance.now();
  var isRunning = false;
  var needsTextureUpdate = true;

  // Media state
  var defaultImg = null;
  var defaultVid = null;
  var uploadImg = null;
  var uploadVid = null;
  var uploadUrl = null;
  var currentMode = 'defaultImage'; // 'defaultImage' | 'defaultVideo' | 'uploadImage' | 'uploadVideo'

  // Default params
  window.__rainConfig = window.__rainConfig || {
    rain: 0.6,
    fog: 0.3,
    refract: 1.0,
    glass: 0.0,
    speed: 0.2
  };

  // Media control API
  window.__rainMedia = {
    mode: function() { return currentMode; },
    setMode: function(m) { setMediaMode(m); },
    reset: function() { setMediaMode('defaultImage'); },
    setUpload: function(file) { loadUpload(file); }
  };

  var VERT = [
    'precision highp float;',
    'attribute vec2 a_pos;',
    'varying vec2 v_uv;',
    'void main(){',
    '  v_uv = a_pos * 0.5 + 0.5;',
    '  gl_Position = vec4(a_pos, 0.0, 1.0);',
    '}'
  ].join('\n');

  var FRAG = [
    'precision highp float;',
    '',
    'uniform float u_time;',
    'uniform vec2 u_res;',
    'uniform float u_rain;',
    'uniform float u_fog;',
    'uniform float u_refract;',
    'uniform float u_glass;',
    'uniform float u_speed;',
    'uniform sampler2D u_tex;',
    '',
    'varying vec2 v_uv;',
    '',
    '#define S(a,b,t) smoothstep(a,b,t)',
    '',
    'vec3 N13(float p){',
    '  vec3 p3 = fract(vec3(p)*vec3(.1031,.11369,.13787));',
    '  p3 += dot(p3,p3.yzx+19.19);',
    '  return fract(vec3((p3.x+p3.y)*p3.z,(p3.x+p3.z)*p3.y,(p3.y+p3.z)*p3.x));',
    '}',
    '',
    'float N(float t){return fract(sin(t*12345.564)*7658.76);}',
    '',
    'float Saw(float b,float t){return S(0.,b,t)*S(1.,b,t);}',
    '',
    'vec2 DropLayer2(vec2 uv,float t){',
    '  vec2 UV=uv;',
    '  uv.y += t*0.75;',
    '  vec2 a=vec2(6.,3.);',
    '  vec2 grid=a*2.;',
    '  vec2 id=floor(uv*grid);',
    '  float colShift=N(id.x);',
    '  uv.y += colShift;',
    '  id=floor(uv*grid);',
    '  vec3 n=N13(id.x*35.2+id.y*2376.1);',
    '  vec2 st=fract(uv*grid)-vec2(.5,0);',
    '  float x=n.x-.5;',
    '  float y=UV.y*20.;',
    '  float wiggle=sin(y+sin(y));',
    '  x += wiggle*(.5-abs(x))*(n.z-.5);',
    '  x *= .7;',
    '  float ti=fract(t+n.z);',
    '  y=(Saw(.85,ti)-.5)*.9+.5;',
    '  vec2 p=vec2(x,y);',
    '  float d=length((st-p)*a.yx);',
    '  float mainDrop=S(.35,.0,d);',
    '  float r=sqrt(S(1.,y,st.y));',
    '  float cd=abs(st.x-x);',
    '  float trail=S(.23*r,.15*r*r,cd);',
    '  float trailFront=S(-.02,.02,st.y-y);',
    '  trail *= trailFront*r*r;',
    '  y=UV.y;',
    '  float trail2=S(.2*r,.0,cd);',
    '  float droplets=max(0.,(sin(y*(1.-y)*120.)-st.y))*trail2*trailFront*n.z;',
    '  y=fract(y*10.)+(st.y-.5);',
    '  float dd=length(st-vec2(x,y));',
    '  droplets=S(.3,0.,dd);',
    '  float m=mainDrop+droplets*r*trailFront;',
    '  return vec2(m,trail);',
    '}',
    '',
    'float StaticDrops(vec2 uv,float t){',
    '  uv *= 40.;',
    '  vec2 id=floor(uv);',
    '  uv=fract(uv)-.5;',
    '  vec3 n=N13(id.x*107.45+id.y*3543.654);',
    '  vec2 p=(n.xy-.5)*.7;',
    '  float d=length(uv-p);',
    '  float fade=Saw(.025,fract(t+n.z));',
    '  float c=S(.25,0.,d)*fract(n.z*10.)*fade;',
    '  return c*1.2;',
    '}',
    '',
    'vec2 Drops(vec2 uv,float t,float l0,float l1,float l2){',
    '  float s=StaticDrops(uv,t)*l0;',
    '  vec2 m1=DropLayer2(uv,t)*l1;',
    '  vec2 m2=DropLayer2(uv*1.85,t)*l2;',
    '  float c=s+m1.x+m2.x;',
    '  c=S(.2,.95,c);',
    '  return vec2(c,max(m1.y*l0,max(m2.y*l1,s)));',
    '}',
    '',
    'void main(){',
    '  vec2 uv=(v_uv-.5)*u_res/min(u_res.x,u_res.y);',
    '  float t=u_time*u_speed;',
    '  float rain=u_rain;',
    '  float staticDrops=S(-.5,1.,rain)*1.0;',
    '  float layer1=S(.25,.75,rain);',
    '  float layer2=S(.0,.5,rain);',
    '  vec2 c=Drops(uv,t,staticDrops,layer1,layer2);',
    '  vec2 e=vec2(.001,0.);',
    '  float cx=Drops(uv+e,t,staticDrops,layer1,layer2).x;',
    '  float cy=Drops(uv+e.yx,t,staticDrops,layer1,layer2).x;',
    '  vec2 n=vec2(cx-c.x,cy-c.x)*u_refract;',
    '  float focus=mix(max(0.,1.-c.x*2.2),0.,0.45);',
    '  vec2 texUV=v_uv;',
    '  texUV.y=1.0-texUV.y;',
    '  vec3 col=texture2D(u_tex,texUV+n).rgb;',
    '  float glassFactor=max(0.1,pow(max(0.0,1.0-u_glass),0.35));',
    '  vec3 blurredCol=vec3(0.);',
    '  float total=0.;',
    '  float radius=0.007*(0.5+u_fog*1.8)*glassFactor;',
    '  for(float i=-1.;i<=1.;i++){',
    '    for(float j=-1.;j<=1.;j++){',
    '      vec2 off=vec2(i,j)*radius;',
    '      blurredCol += texture2D(u_tex,texUV+n+off).rgb;',
    '      total += 1.;',
    '    }',
    '  }',
    '  blurredCol /= total;',
    '  col=mix(col,blurredCol,S(0.,1.,c.y*2.2));',
    '  col=mix(col,blurredCol,(1.-focus)*(1.0-u_glass*0.85));',
    '  col=(col-.5)*1.08+.5;',
    '  float spec=pow(max(0.,dot(normalize(vec3(n,1.)),normalize(vec3(.3,.5,1.)))),12.);',
    '  col += spec*c.x*.65;',
    '  col += c.x*vec3(.04,.06,.10);',
    '  col += c.x*0.04;',
    '  gl_FragColor=vec4(col,1.);',
    '}'
  ].join('\n');

  function compile(type, src) {
    var s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      console.error('Rain shader error:', gl.getShaderInfoLog(s));
      gl.deleteShader(s);
      return null;
    }
    return s;
  }

  function initGL() {
    canvas = document.getElementById('rainCanvas');
    if (!canvas) return false;
    gl = canvas.getContext('webgl', { antialias: false, alpha: false, premultipliedAlpha: false });
    if (!gl) {
      console.warn('WebGL not supported for rain effect');
      return false;
    }

    var vs = compile(gl.VERTEX_SHADER, VERT);
    var fs = compile(gl.FRAGMENT_SHADER, FRAG);
    if (!vs || !fs) return false;

    prog = gl.createProgram();
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      console.error('Rain link error:', gl.getProgramInfoLog(prog));
      return false;
    }
    gl.useProgram(prog);

    // Fullscreen quad
    var pos = new Float32Array([-1,-1, 1,-1, -1,1, 1,1]);
    var pb = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, pb);
    gl.bufferData(gl.ARRAY_BUFFER, pos, gl.STATIC_DRAW);
    var pl = gl.getAttribLocation(prog, 'a_pos');
    gl.enableVertexAttribArray(pl);
    gl.vertexAttribPointer(pl, 2, gl.FLOAT, false, 0, 0);

    u = {
      time: gl.getUniformLocation(prog, 'u_time'),
      res: gl.getUniformLocation(prog, 'u_res'),
      rain: gl.getUniformLocation(prog, 'u_rain'),
      fog: gl.getUniformLocation(prog, 'u_fog'),
      refract: gl.getUniformLocation(prog, 'u_refract'),
      glass: gl.getUniformLocation(prog, 'u_glass'),
      speed: gl.getUniformLocation(prog, 'u_speed'),
      tex: gl.getUniformLocation(prog, 'u_tex')
    };
    gl.uniform1i(u.tex, 0);

    bgCanvas = document.createElement('canvas');
    return true;
  }

  function resize() {
    if (!canvas || !gl) return;
    var dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    var w = Math.floor(window.innerWidth * dpr);
    var h = Math.floor(window.innerHeight * dpr);
    canvas.width = w;
    canvas.height = h;
    canvas.style.width = window.innerWidth + 'px';
    canvas.style.height = window.innerHeight + 'px';
    gl.viewport(0, 0, w, h);
  }

  // ============ Media loading ============

  function loadDefaultImage() {
    if (defaultImg) return;
    defaultImg = new Image();
    defaultImg.crossOrigin = 'anonymous';
    defaultImg.onload = function() { if (currentMode === 'defaultImage') needsTextureUpdate = true; };
    defaultImg.onerror = function() { defaultImg = null; };
    defaultImg.src = 'resources/橘子洲头.png';
  }

  function loadDefaultVideo() {
    if (defaultVid) return;
    defaultVid = document.createElement('video');
    defaultVid.crossOrigin = 'anonymous';
    defaultVid.src = 'resources/back.mp4';
    defaultVid.loop = true;
    defaultVid.muted = true;
    defaultVid.playsInline = true;
    defaultVid.autoplay = true;
    defaultVid.play().catch(function(){});
  }

  function loadUpload(file) {
    if (!file) return;
    // Clean up previous upload
    if (uploadUrl) { URL.revokeObjectURL(uploadUrl); uploadUrl = null; }
    if (uploadImg) { uploadImg = null; }
    if (uploadVid) { uploadVid.pause(); uploadVid = null; }

    uploadUrl = URL.createObjectURL(file);

    if (file.type.startsWith('video/')) {
      uploadVid = document.createElement('video');
      uploadVid.src = uploadUrl;
      uploadVid.loop = true;
      uploadVid.muted = true;
      uploadVid.playsInline = true;
      uploadVid.autoplay = true;
      uploadVid.play().catch(function(){});
      currentMode = 'uploadVideo';
    } else {
      uploadImg = new Image();
      uploadImg.onload = function() { needsTextureUpdate = true; };
      uploadImg.src = uploadUrl;
      currentMode = 'uploadImage';
    }
    needsTextureUpdate = true;
  }

  function setMediaMode(mode) {
    currentMode = mode;
    needsTextureUpdate = true;
    if (mode === 'defaultImage') loadDefaultImage();
    if (mode === 'defaultVideo') loadDefaultVideo();
  }

  // ============ Texture update ============

  function drawGradient(ctx, w, h) {
    var grad = ctx.createLinearGradient(0, 0, w, h);
    grad.addColorStop(0, '#0f172a');
    grad.addColorStop(0.5, '#1e293b');
    grad.addColorStop(1, '#0b1221');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, w, h);
  }

  function drawMedia(ctx, w, h, media) {
    if (!media) return false;
    var mw = media.videoWidth || media.naturalWidth || media.width || 1;
    var mh = media.videoHeight || media.naturalHeight || media.height || 1;
    var mr = mw / mh;
    var cr = w / h;
    var dw = w, dh = h;
    if (cr > mr) dh = w / mr;
    else dw = h * mr;
    ctx.drawImage(media, (w - dw) / 2, (h - dh) / 2, dw, dh);
    return true;
  }

  function updateTexture() {
    if (!gl || !bgCanvas) return;
    var w = Math.floor(window.innerWidth);
    var h = Math.floor(window.innerHeight);
    bgCanvas.width = w;
    bgCanvas.height = h;
    var ctx = bgCanvas.getContext('2d');

    var drawn = false;

    if (currentMode === 'uploadVideo' && uploadVid && uploadVid.readyState >= 2) {
      drawn = drawMedia(ctx, w, h, uploadVid);
    } else if (currentMode === 'defaultVideo' && defaultVid && defaultVid.readyState >= 2) {
      drawn = drawMedia(ctx, w, h, defaultVid);
    } else if (currentMode === 'uploadImage' && uploadImg && uploadImg.complete) {
      drawn = drawMedia(ctx, w, h, uploadImg);
    } else if (currentMode === 'defaultImage' && defaultImg && defaultImg.complete) {
      drawn = drawMedia(ctx, w, h, defaultImg);
    }

    if (!drawn) {
      drawGradient(ctx, w, h);
    }

    if (!texture) {
      texture = gl.createTexture();
    }
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, bgCanvas);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  }

  // ============ Render loop ============

  function render() {
    if (!isRunning || !gl) return;
    var elapsed = (performance.now() - startTime) / 1000.0;
    var w = canvas.width;
    var h = canvas.height;
    var cfg = window.__rainConfig || {};

    // Video backgrounds need per-frame texture update
    var isVideo = currentMode === 'defaultVideo' || currentMode === 'uploadVideo';
    if (needsTextureUpdate || isVideo) {
      updateTexture();
      needsTextureUpdate = false;
    }

    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, texture);

    gl.uniform1f(u.time, elapsed);
    gl.uniform2f(u.res, w, h);
    gl.uniform1f(u.rain, cfg.rain != null ? cfg.rain : 0.6);
    gl.uniform1f(u.fog, cfg.fog != null ? cfg.fog : 0.3);
    gl.uniform1f(u.refract, cfg.refract != null ? cfg.refract : 1.0);
    gl.uniform1f(u.glass, cfg.glass != null ? cfg.glass : 0.0);
    gl.uniform1f(u.speed, cfg.speed != null ? cfg.speed : 0.2);

    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    rafId = requestAnimationFrame(render);
  }

  function onResize() {
    resize();
    needsTextureUpdate = true;
  }

  window.initRain = function() {
    if (isRunning) return;
    if (!document.getElementById('rainCanvas')) {
      var rc = document.createElement('canvas');
      rc.id = 'rainCanvas';
      rc.style.cssText = 'position:fixed;top:0;left:0;width:100vw;height:100vh;z-index:0;pointer-events:none;';
      document.body.insertBefore(rc, document.body.firstChild);
    }
    if (!initGL()) return;
    resize();

    // Preload default media
    loadDefaultImage();
    loadDefaultVideo();
    currentMode = 'defaultImage';
    needsTextureUpdate = true;

    startTime = performance.now();
    isRunning = true;
    window.addEventListener('resize', onResize);
    rafId = requestAnimationFrame(render);
  };

  window.destroyRain = function() {
    isRunning = false;
    if (rafId) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
    window.removeEventListener('resize', onResize);
    var rc = document.getElementById('rainCanvas');
    if (rc && rc.parentNode) {
      rc.parentNode.removeChild(rc);
    }
    canvas = null;
    gl = null;
    prog = null;
    texture = null;
    bgCanvas = null;
    defaultImg = null;
    defaultVid = null;
    uploadImg = null;
    if (uploadVid) { uploadVid.pause(); uploadVid = null; }
    if (uploadUrl) { URL.revokeObjectURL(uploadUrl); uploadUrl = null; }
  };

  // Auto-init: watch for rain class to appear (handles async Zustand rehydration)
  function tryAutoInit() {
    if (document.documentElement.classList.contains('rain') && !isRunning) {
      window.initRain();
    }
  }

  if (document.documentElement.classList.contains('rain')) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function() {
        setTimeout(tryAutoInit, 50);
      });
    } else {
      setTimeout(tryAutoInit, 50);
    }
  }

  // Also watch for class changes (React/Zustand may add 'rain' later)
  var observer = new MutationObserver(function(mutations) {
    for (var i = 0; i < mutations.length; i++) {
      if (mutations[i].attributeName === 'class') {
        if (document.documentElement.classList.contains('rain')) {
          if (!isRunning) window.initRain();
        } else {
          if (isRunning) window.destroyRain();
        }
      }
    }
  });
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
})();
