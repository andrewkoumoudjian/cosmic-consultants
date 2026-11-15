/**
 * Moon and Mars for step 1, drawn live with three.js.
 *
 * The Figma file uses two engraved stills ("Asset / Lunar illustration",
 * "Asset / Martian illustration"). This keeps that look (lavender stipple for
 * the Moon, contour engraving for Mars, the night side dissolving into the
 * canvas) but on a real sphere that turns, so the choice feels alive.
 * The stills are the fallback when WebGL is unavailable.
 *
 * The surfaces are procedural and illustrative, not maps of either body.
 * Colours (issue #205): the Moon is grey, Mars is red.
 */
import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import marsStill from '../assets/mars-illustration.png';
import moonStill from '../assets/moon-illustration.png';
type World = 'moon' | 'mars';

const NOISE = /* glsl */ `
vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 permute(vec4 x){return mod289(((x*34.0)+10.0)*x);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
float snoise(vec3 v){
  const vec2 C=vec2(1.0/6.0,1.0/3.0);
  const vec4 D=vec4(0.0,0.5,1.0,2.0);
  vec3 i=floor(v+dot(v,C.yyy));
  vec3 x0=v-i+dot(i,C.xxx);
  vec3 g=step(x0.yzx,x0.xyz);
  vec3 l=1.0-g;
  vec3 i1=min(g.xyz,l.zxy);
  vec3 i2=max(g.xyz,l.zxy);
  vec3 x1=x0-i1+C.xxx;
  vec3 x2=x0-i2+C.yyy;
  vec3 x3=x0-D.yyy;
  i=mod289(i);
  vec4 p=permute(permute(permute(i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));
  float n_=0.142857142857;
  vec3 ns=n_*D.wyz-D.xzx;
  vec4 j=p-49.0*floor(p*ns.z*ns.z);
  vec4 x_=floor(j*ns.z);
  vec4 y_=floor(j-7.0*x_);
  vec4 x=x_*ns.x+ns.yyyy;
  vec4 y=y_*ns.x+ns.yyyy;
  vec4 h=1.0-abs(x)-abs(y);
  vec4 b0=vec4(x.xy,y.xy);
  vec4 b1=vec4(x.zw,y.zw);
  vec4 s0=floor(b0)*2.0+1.0;
  vec4 s1=floor(b1)*2.0+1.0;
  vec4 sh=-step(h,vec4(0.0));
  vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy;
  vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
  vec3 p0=vec3(a0.xy,h.x);
  vec3 p1=vec3(a0.zw,h.y);
  vec3 p2=vec3(a1.xy,h.z);
  vec3 p3=vec3(a1.zw,h.w);
  vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
  p0*=norm.x;p1*=norm.y;p2*=norm.z;p3*=norm.w;
  vec4 m=max(0.5-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0);
  m=m*m;
  return 105.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}
float fbm(vec3 p){
  float s=0.0,a=0.5;
  for(int i=0;i<5;i++){s+=a*snoise(p);p=p*2.03+vec3(1.7,9.2,3.1);a*=0.5;}
  return s;
}
vec3 hash3(vec3 p){
  p=vec3(dot(p,vec3(127.1,311.7,74.7)),dot(p,vec3(269.5,183.3,246.1)),dot(p,vec3(113.5,271.9,124.6)));
  return fract(sin(p)*43758.5453123);
}
// Nearest feature point: xyz = vector to it, w = cell random.
vec4 worley(vec3 p){
  vec3 i=floor(p),f=fract(p);
  float d=9.0;vec4 best=vec4(0.0);
  for(int x=-1;x<=1;x++)for(int y=-1;y<=1;y++)for(int z=-1;z<=1;z++){
    vec3 g=vec3(float(x),float(y),float(z));
    vec3 o=hash3(i+g);
    vec3 r=g+o-f;
    float dd=dot(r,r);
    if(dd<d){d=dd;best=vec4(r,o.y);}
  }
  return best;
}
`;

const VERT = /* glsl */ `
varying vec3 vObj;
varying vec3 vNormalW;
varying vec3 vViewW;
void main(){
  vObj=position;
  vec4 w=modelMatrix*vec4(position,1.0);
  vNormalW=normalize(mat3(modelMatrix)*normal);
  vViewW=normalize(cameraPosition-w.xyz);
  gl_Position=projectionMatrix*viewMatrix*w;
}
`;

const FRAG = /* glsl */ `
precision highp float;
uniform float uKind;      // 0 moon, 1 mars
uniform vec3 uLight;      // world space
uniform vec3 uLightObj;   // object space
uniform float uCell;      // halftone cell in device px
uniform vec3 uDeep;
uniform vec3 uMid;
uniform vec3 uHigh;
varying vec3 vObj;
varying vec3 vNormalW;
varying vec3 vViewW;
${NOISE}

float crater(vec3 p, float scale, float density, vec3 L){
  vec4 w=worley(p*scale);
  if(w.w>density) return 0.0;
  float rr=mix(0.28,0.46,fract(w.w*17.0));
  float d=length(w.xyz)/rr;
  if(d>1.8) return 0.0;
  vec3 dir=normalize(w.xyz);
  float face=dot(dir,L);
  float inside=(1.0-smoothstep(0.85,1.0,d));
  float bowl=inside*(-0.25+0.55*face*smoothstep(0.15,0.95,d));
  float rim=smoothstep(0.75,1.0,d)*(1.0-smoothstep(1.0,1.25,d))*(0.35-0.4*face);
  float ejecta=(1.0-inside)*exp(-(d-1.0)*5.0)*0.12;
  return bowl+rim+ejecta;
}

void main(){
  vec3 p=normalize(vObj);
  vec3 n=normalize(vNormalW);
  float ndl=dot(n,normalize(uLight));
  float h;
  float pattern;
  vec2 cellCoord=gl_FragCoord.xy/uCell;

  if(uKind<0.5){
    float maria=smoothstep(-0.05,0.55,snoise(p*1.25)+0.55*snoise(p*2.9+3.0));
    h=0.62+0.18*fbm(p*5.0)-0.32*maria;
    h+=0.55*crater(p,3.2,0.55,uLightObj);
    h+=0.35*crater(p+7.1,7.5,0.5,uLightObj);
    h+=0.18*crater(p+2.3,16.0,0.45,uLightObj);
    float lum=clamp(smoothstep(-0.15,0.85,ndl)*(0.25+0.85*h),0.0,1.0);
    vec2 f=fract(cellCoord)-0.5;
    float r=0.56*sqrt(lum)+0.08;
    pattern=1.0-smoothstep(r-0.09,r+0.09,length(f));
    vec3 col=mix(uDeep,uMid,smoothstep(0.1,0.5,lum));
    col=mix(col,uHigh,smoothstep(0.5,0.95,lum));
    float night=smoothstep(-0.45,0.1,ndl);
    float limb=smoothstep(0.0,0.22,dot(n,vViewW));
    float a=pattern*night*limb*mix(0.35,1.0,smoothstep(0.0,0.35,lum));
    gl_FragColor=vec4(col,a);
  } else {
    // Layered, wind-cut strata: mostly horizontal, gently warped.
    vec3 q=p*vec3(1.0,0.55,1.0);
    float warp=fbm(q*1.6)*0.9+0.25*snoise(p*vec3(3.0,1.2,3.0));
    float band=p.y*4.2+warp;
    // Broad bright terraces separated by darker scarps.
    float scarp=smoothstep(0.1,0.8,abs(snoise(vec3(band*1.1,p.x*1.2,p.z*1.2))));
    h=0.45+0.5*scarp+0.08*snoise(p*12.0);
    float lum=clamp(smoothstep(-0.15,0.85,ndl)*(0.25+0.85*h),0.0,1.0);
    // Fine engraved lines; the gaps keep a dim indigo fill so it reads as tone.
    float t=band*30.0;
    float aa=fwidth(t)*0.75;
    float w=0.06+0.24*lum;
    float line=1.0-smoothstep(w-aa,w+aa,abs(fract(t)-0.5));
    vec3 ink=mix(uDeep,uMid,smoothstep(0.1,0.55,lum));
    ink=mix(ink,uHigh,smoothstep(0.45,0.85,lum));
    vec3 gap=mix(uDeep,uMid,0.35*lum);
    vec3 col=mix(gap,ink,line);
    float night=smoothstep(-0.25,0.2,ndl);
    float limb=smoothstep(0.0,0.16,dot(n,vViewW));
    float a=mix(0.32*smoothstep(0.0,0.4,lum),1.0,line)*night*limb*mix(0.4,1.0,smoothstep(0.0,0.3,lum));
    gl_FragColor=vec4(col,a);
  }
}
`;

const LOOKS: Record<World, { light: THREE.Vector3; tilt: number; speed: number; deep: string; mid: string; high: string }> = {
  moon: { light: new THREE.Vector3(0.7, -0.3, 0.65).normalize(), tilt: 0.12, speed: 0.045, deep: '#3a3e47', mid: '#a9aeb8', high: '#f0f2f5' },
  mars: { light: new THREE.Vector3(0.45, 0.65, 0.62).normalize(), tilt: 0.3, speed: 0.035, deep: '#5c1a12', mid: '#d0573e', high: '#f6c6ab' },
};

function webglAvailable(): boolean {
  try {
    const c = document.createElement('canvas');
    return !!(c.getContext('webgl2') || c.getContext('webgl'));
  } catch {
    return false;
  }
}

export function Planet({ world, hovered, label }: { world: World; hovered: boolean; label: string }) {
  const host = useRef<HTMLDivElement>(null);
  const hoverRef = useRef(hovered);
  const pointer = useRef({ x: 0, y: 0 });
  const [fallback, setFallback] = useState(false);
  hoverRef.current = hovered;

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    if (!webglAvailable()) {
      setFallback(true);
      return;
    }
    const look = LOOKS[world];
    const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'low-power' });
    } catch {
      setFallback(true);
      return;
    }
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    renderer.setPixelRatio(dpr);
    renderer.setClearColor(0x000000, 0);
    el.appendChild(renderer.domElement);
    renderer.domElement.setAttribute('aria-hidden', 'true');

    const scene = new THREE.Scene();
    const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 10);
    camera.position.set(0, 0, 4);

    const uniforms = {
      uKind: { value: world === 'moon' ? 0 : 1 },
      uLight: { value: look.light.clone() },
      uLightObj: { value: look.light.clone() },
      uCell: { value: 3.4 * dpr },
      uDeep: { value: new THREE.Color(look.deep) },
      uMid: { value: new THREE.Color(look.mid) },
      uHigh: { value: new THREE.Color(look.high) },
    };
    const material = new THREE.ShaderMaterial({ vertexShader: VERT, fragmentShader: FRAG, uniforms, transparent: true, depthWrite: false });
    const geometry = new THREE.SphereGeometry(1, 160, 120);
    const pivot = new THREE.Group();
    pivot.rotation.z = look.tilt;
    const mesh = new THREE.Mesh(geometry, material);
    mesh.rotation.y = world === 'moon' ? 0.6 : 2.2;
    pivot.add(mesh);
    scene.add(pivot);

    const fit = () => {
      const w = el.clientWidth || 1;
      const hgt = el.clientHeight || 1;
      renderer.setSize(w, hgt, false);
      renderer.domElement.style.width = `${w}px`;
      renderer.domElement.style.height = `${hgt}px`;
      const aspect = w / hgt;
      const half = 1.03;
      camera.left = -half * aspect;
      camera.right = half * aspect;
      camera.top = half;
      camera.bottom = -half;
      camera.updateProjectionMatrix();
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(el);

    const onMove = (e: PointerEvent) => {
      const r = el.getBoundingClientRect();
      pointer.current = { x: ((e.clientX - r.left) / r.width) * 2 - 1, y: ((e.clientY - r.top) / r.height) * 2 - 1 };
    };
    el.addEventListener('pointermove', onMove);

    let visible = true;
    const io = new IntersectionObserver(([entry]) => (visible = entry.isIntersecting));
    io.observe(el);

    const inv = new THREE.Matrix4();
    const lightObj = new THREE.Vector3();
    const clock = new THREE.Clock();
    let speed = look.speed;
    let tiltX = 0;
    let tiltY = 0;

    const frame = () => {
      const dt = Math.min(clock.getDelta(), 0.05);
      if (!visible || document.hidden) return;
      if (!reduce) {
        const target = hoverRef.current ? look.speed * 5 : look.speed;
        speed += (target - speed) * Math.min(1, dt * 3);
        mesh.rotation.y += speed * dt;
        const tx = hoverRef.current ? pointer.current.y * 0.12 : 0;
        const ty = hoverRef.current ? pointer.current.x * 0.12 : 0;
        tiltX += (tx - tiltX) * Math.min(1, dt * 4);
        tiltY += (ty - tiltY) * Math.min(1, dt * 4);
        pivot.rotation.x = tiltX;
        pivot.rotation.y = tiltY;
      }
      mesh.updateMatrixWorld();
      inv.copy(mesh.matrixWorld).invert();
      lightObj.copy(look.light).transformDirection(inv);
      uniforms.uLightObj.value.copy(lightObj);
      renderer.render(scene, camera);
    };
    if (reduce) {
      frame();
      const again = () => frame();
      ro.disconnect();
      const ro2 = new ResizeObserver(() => {
        fit();
        again();
      });
      ro2.observe(el);
      return () => {
        ro2.disconnect();
        io.disconnect();
        el.removeEventListener('pointermove', onMove);
        geometry.dispose();
        material.dispose();
        renderer.dispose();
        renderer.domElement.remove();
      };
    }
    renderer.setAnimationLoop(frame);

    return () => {
      renderer.setAnimationLoop(null);
      ro.disconnect();
      io.disconnect();
      el.removeEventListener('pointermove', onMove);
      geometry.dispose();
      material.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [world]);

  return (
    <div className="planet" ref={host} role="img" aria-label={label}>
      {fallback && <img className="planet__still" data-world={world} src={world === 'moon' ? moonStill : marsStill} alt="" />}
    </div>
  );
}
