import React from 'react';
import {Composition} from 'remotion';
import {Iklan, Props} from './Iklan';

export const FPS = 30;
const contoh: Props = {
  kode: 'GB01', judul: 'Contoh Produk', harga: 'Rp49.900', durasi: 15,
  artis: '', fotos: [],
  audio: '', musik: '', artisDetik: 5, fotoDetik: 2,
  kata: [],
};
export const Root: React.FC = () => (
  <Composition
    id="Iklan" component={Iklan} width={1080} height={1920} fps={FPS}
    durationInFrames={15 * FPS} defaultProps={contoh}
    calculateMetadata={({props}) => ({durationInFrames: Math.round(props.durasi * FPS)})}
  />
);
