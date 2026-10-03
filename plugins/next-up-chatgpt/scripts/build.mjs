import { build } from 'esbuild';
import { mkdir, readFile, writeFile, copyFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
await mkdir(`${root}dist`, { recursive: true });
const result = await build({ entryPoints: [`${root}web/card.mjs`], bundle: true, format: 'esm', target: 'es2022', write: false, minify: true });
const template = await readFile(`${root}web/card.html`, 'utf8');
const css = await readFile(`${root}web/card.css`, 'utf8');
await writeFile(`${root}dist/card.html`, template.replace('/* STYLE */', () => css).replace('/* SCRIPT */', () => result.outputFiles[0].text.replace(/<\/script/gi, '<\\/script')));
const readFoundation = await readFile(`${root}assets/design-systems/next-up-0.3.1/design-system.css`, 'utf8');
const panelCss = await readFile(`${root}web/panel.css`, 'utf8');
const panel = await build({ entryPoints: [`${root}web/panel.mjs`], bundle: true, format: 'esm', target: 'es2022', write: false, minify: true });
const panelTemplate = await readFile(`${root}web/panel.html`, 'utf8');
await writeFile(`${root}dist/panel.html`, panelTemplate
  .replace('/* FOUNDATION */', () => readFoundation)
  .replace('/* STYLE */', () => panelCss)
  .replace('/* SCRIPT */', () => panel.outputFiles[0].text.replace(/<\/script/gi, '<\\/script')));
await build({ entryPoints: [`${root}web/preview.mjs`], bundle: true, format: 'esm', target: 'es2022', outfile: `${root}dist/preview.js` });
await copyFile(`${root}web/preview.html`, `${root}dist/preview.html`);
console.log('Built MCP card and local protocol preview.');
