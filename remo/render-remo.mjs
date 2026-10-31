// Pemakaian: node render-remo.mjs props.json keluaran.mp4   (aset di folder public/)
import {bundle} from '@remotion/bundler';
import {renderMedia, selectComposition} from '@remotion/renderer';
import fs from 'fs'; import path from 'path'; import {fileURLToPath} from 'url';
const dir = path.dirname(fileURLToPath(import.meta.url));
const [,, propsFile, out] = process.argv;
const inputProps = JSON.parse(fs.readFileSync(propsFile, 'utf8'));
const browserExecutable = process.env.CHROME_PATH || undefined;
fs.mkdirSync(path.join(dir, 'public'), {recursive: true});
const serveUrl = await bundle({entryPoint: path.join(dir, 'src/index.ts'), publicDir: path.join(dir, 'public')});
const comp = await selectComposition({serveUrl, id: 'Iklan', inputProps, browserExecutable});
await renderMedia({composition: comp, serveUrl, codec: 'h264', outputLocation: out, inputProps, browserExecutable,
  crf: 23, concurrency: 2, chromiumOptions: {gl: 'swangle'}, onProgress: ({progress}) => process.stdout.write(`\r${Math.round(progress*100)}%`)});
console.log('\nSelesai:', out);
