import React from 'react';
import {AbsoluteFill, Audio, Img, Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';

export type Kata = {w: string; mulai: number; durasi: number}; // detik
export type Props = {
  kode: string; judul: string; harga: string; durasi: number;
  artis: string; fotos: string[]; audio: string; musik: string;
  artisDetik: number; fotoDetik: number; kata: Kata[];
  artisPotong?: string; // PNG artis tanpa latar (kecil, goyang di atas foto produk)
};
const src = (s: string) => (s.startsWith('http') ? s : staticFile(s));

// Foto bergerak (Ken Burns) + masuk dengan "pop"
const Foto: React.FC<{u: string; dur: number; i: number}> = ({u, dur, i}) => {
  const f = useCurrentFrame(); const {fps} = useVideoConfig();
  const p = f / dur;
  const arah = i % 4;
  const zoom = arah === 1 ? interpolate(p, [0, 1], [1.22, 1.02]) : interpolate(p, [0, 1], [1.02, 1.2]);
  const geser = arah === 2 ? interpolate(p, [0, 1], [-40, 40]) : arah === 3 ? interpolate(p, [0, 1], [40, -40]) : 0;
  const masuk = spring({frame: f, fps, config: {damping: 14, stiffness: 140}, durationInFrames: 14});
  const kelip = interpolate(f, [0, 3], [0.6, 0], {extrapolateRight: 'clamp'}); // kilatan tipis tiap pindah foto
  return (
    <AbsoluteFill style={{backgroundColor: '#111'}}>
      <AbsoluteFill style={{transform: `scale(${0.96 + 0.04 * masuk})`, overflow: 'hidden'}}>
        <Img src={src(u)} style={{width: '100%', height: '100%', objectFit: 'cover', transform: `scale(${zoom}) translateX(${geser}px)`}} />
      </AbsoluteFill>
      <AbsoluteFill style={{background: '#fff', opacity: kelip}} />
    </AbsoluteFill>
  );
};

const Judul: React.FC<{judul: string; harga: string}> = ({judul, harga}) => {
  const f = useCurrentFrame(); const {fps} = useVideoConfig();
  const a = spring({frame: f - 4, fps, config: {damping: 10, stiffness: 160}});
  const b = spring({frame: f - 14, fps, config: {damping: 8, stiffness: 150}});
  const denyut = 1 + 0.04 * Math.sin(f / 5);
  return (
    <>
      <div style={{position: 'absolute', top: 170, left: 0, right: 0, textAlign: 'center', transform: `translateY(${(1 - a) * -120}px) scale(${a})`}}>
        <span style={{background: 'rgba(0,0,0,.6)', color: '#fff', fontSize: 50, fontWeight: 800, padding: '16px 30px', borderRadius: 18, fontFamily: 'sans-serif'}}>{judul}</span>
      </div>
      {harga && (
        <div style={{position: 'absolute', top: 300, left: 0, right: 0, textAlign: 'center', transform: `scale(${b * denyut}) rotate(${(1 - b) * -8}deg)`}}>
          <span style={{background: '#FFD400', color: '#C8102E', fontSize: 84, fontWeight: 900, padding: '10px 36px', borderRadius: 24, fontFamily: 'sans-serif', boxShadow: '0 8px 0 #b38f00'}}>{harga}</span>
        </div>
      )}
    </>
  );
};

// Subtitle karaoke di bagian bawah (tidak menutupi produk): 4 kata per layar, kata yang diucapkan menyala kuning
const Subtitle: React.FC<{kata: Kata[]}> = ({kata}) => {
  const f = useCurrentFrame(); const {fps} = useVideoConfig();
  const t = f / fps;
  if (!kata.length) return null;
  let idx = kata.findIndex((k) => t >= k.mulai && t < k.mulai + k.durasi);
  if (idx < 0) idx = Math.max(0, kata.findIndex((k) => k.mulai > t) - 1);
  const gStart = Math.floor(idx / 4) * 4;
  const grup = kata.slice(gStart, gStart + 4);
  if (t < kata[gStart].mulai - 0.2 || t > kata[Math.min(gStart + 3, kata.length - 1)].mulai + kata[Math.min(gStart + 3, kata.length - 1)].durasi + 0.3) return null;
  return (
    <div style={{position: 'absolute', bottom: 330, left: 50, right: 50, textAlign: 'center', fontFamily: 'sans-serif', fontWeight: 900, fontSize: 60, lineHeight: 1.18}}>
      {grup.map((k, j) => {
        const aktif = gStart + j === idx;
        return (
          <span key={j} style={{display: 'inline-block', margin: '0 12px', color: aktif ? '#FFE600' : '#fff',
            transform: `scale(${aktif ? 1.12 : 1})`, textShadow: '0 0 8px #000, 0 6px 0 #000, 4px 4px 0 #000, -4px 4px 0 #000'}}>{k.w}</span>
        );
      })}
    </div>
  );
};

const Ajakan: React.FC<{kode: string}> = ({kode}) => {
  const f = useCurrentFrame(); const {fps} = useVideoConfig();
  const m = spring({frame: f, fps, config: {damping: 9, stiffness: 120}});
  const goyang = Math.sin(f / 4) * 3;
  return (
    <div style={{position: 'absolute', bottom: 170, left: 0, right: 0, textAlign: 'center', transform: `scale(${m}) rotate(${goyang}deg)`}}>
      <div style={{display: 'inline-block', background: '#EE4D2D', color: '#fff', fontFamily: 'sans-serif', fontWeight: 900, fontSize: 54, padding: '20px 40px', borderRadius: 26, boxShadow: '0 10px 0 #9c2d16'}}>
        KODE {kode} • CEK LINK DI BIO
      </div>
    </div>
  );
};

// Artis kecil tanpa latar: masuk membal, lalu goyang-goyang lucu di sisi kanan
const ArtisKecil: React.FC<{u: string}> = ({u}) => {
  const f = useCurrentFrame(); const {fps} = useVideoConfig();
  const masuk = spring({frame: f, fps, config: {damping: 7, stiffness: 150}});
  const goyang = Math.sin(f / 3.2) * 7;                 // miring kiri-kanan
  const loncat = Math.abs(Math.sin(f / 5)) * -26;       // melonjak kecil
  const napas = 1 + 0.03 * Math.sin(f / 4);
  return (
    <div style={{position: 'absolute', right: 24, bottom: 520, width: 340, height: 540, transformOrigin: '50% 100%',
      transform: `translateY(${(1 - masuk) * 500 + loncat}px) rotate(${goyang}deg) scale(${masuk * napas})`}}>
      <Img src={src(u)} style={{width: '100%', height: '100%', objectFit: 'contain', objectPosition: 'bottom',
        filter: 'drop-shadow(0 12px 14px rgba(0,0,0,.45))'}} />
    </div>
  );
};

export const Iklan: React.FC<Props> = (p) => {
  const {fps} = useVideoConfig();
  const akhir = Math.round(p.durasi * fps);
  // Susunan: foto artis (artisDetik) -> maks 3 foto asli (fotoDetik tiap foto, artis kecil goyang di atasnya)
  // -> sisa waktu foto artis lagi.
  const bagian: {u: string; dur: number; i: number; kecil: boolean}[] = [];
  let sisa = akhir, i = 0;
  const tambah = (u: string, detik: number, kecil: boolean) => {
    const d = Math.min(sisa, Math.round(detik * fps));
    if (d > 0 && u) { bagian.push({u, dur: d, i: i++, kecil}); sisa -= d; }
  };
  tambah(p.artis, p.artisDetik, false);
  p.fotos.slice(0, 3).forEach((u) => tambah(u, p.fotoDetik, !!p.artisPotong));
  if (sisa > 0) tambah(p.artis || p.fotos[0], sisa / fps, false);
  let mulai = 0;
  return (
    <AbsoluteFill style={{backgroundColor: '#000'}}>
      {bagian.map((s, n) => { const fr = mulai; mulai += s.dur; return (
        <Sequence key={n} from={fr} durationInFrames={s.dur}>
          <Foto u={s.u} dur={s.dur} i={s.i} />
          {s.kecil && p.artisPotong ? <ArtisKecil u={p.artisPotong} /> : null}
        </Sequence>); })}
      <Judul judul={p.judul} harga={p.harga} />
      <Subtitle kata={p.kata} />
      <Sequence from={Math.max(0, akhir - 3 * fps)}><Ajakan kode={p.kode} /></Sequence>
      {p.audio ? <Audio src={src(p.audio)} /> : null}
      {p.musik ? <Audio src={src(p.musik)} volume={(f) => 0.13 * interpolate(f, [0, 30, akhir - 36, akhir], [0, 1, 1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})} loop /> : null}
    </AbsoluteFill>
  );
};
