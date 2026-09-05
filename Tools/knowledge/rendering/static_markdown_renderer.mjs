/** Actual, offline Markdown construct rendering. Governance lives in K12. */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath, pathToFileURL} from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const moduleRoot = fs.realpathSync(process.env.CAMBIUM_RENDER_NODE_MODULES ||
  path.join(here, 'static_renderer', 'node_modules'));
const requireLocal = createRequire(path.join(moduleRoot, '..', 'package.json'));
async function dependency(name) {
  const resolved = fs.realpathSync(requireLocal.resolve(name));
  if (!resolved.startsWith(moduleRoot + path.sep)) throw new Error(`Nonlocal dependency: ${name}`);
  return import(pathToFileURL(resolved).href);
}
const [{unified}, {default: remarkParse}, {default: remarkMath},
  {default: remarkGfm}, {default: remarkFrontmatter},
  {default: remarkRehype}, {default: rehypeStringify}, {default: katex}] =
  await Promise.all(['unified', 'remark-parse', 'remark-math', 'remark-gfm',
    'remark-frontmatter', 'remark-rehype', 'rehype-stringify', 'katex'].map(dependency));

const SELECTOR = 'remark-commonmark-gfm-math-v1';
const ACCEPTANCE = Object.freeze({
  'mermaid-fence': 'mermaid-svg',
  'dollar-math': 'katex-html-mathml',
  'outer-pipe-markdown-table': 'wrap-or-scroll-table',
});
const sha = value => 'sha256:' + crypto.createHash('sha256').update(value).digest('hex');
const processor = unified().use(remarkParse).use(remarkFrontmatter, ['yaml'])
  .use(remarkGfm).use(remarkMath, {singleDollarTextMath: true});

function parse(source) {
  const found = [];
  function visit(node) {
    let kind;
    if (node.type === 'code' && node.lang?.toLowerCase() === 'mermaid') kind = 'mermaid-fence';
    if (node.type === 'math' || node.type === 'inlineMath') kind = 'dollar-math';
    if (node.type === 'table') {
      // The Kernel's admitted table family requires outer pipes. Selection
      // itself is an official GFM table node; this only narrows that family.
      const firstLine = source.slice(node.position.start.offset, node.position.end.offset).split('\n')[0].trim();
      if (firstLine.startsWith('|') && firstLine.endsWith('|')) kind = 'outer-pipe-markdown-table';
    }
    if (kind) found.push({kind, node});
    for (const child of node.children || []) visit(child);
  }
  visit(processor.parse(source));
  return found;
}

async function htmlFor(node) {
  const compiler = unified().use(remarkRehype).use(rehypeStringify);
  return compiler.stringify(await compiler.run({type: 'root', children: [node]}));
}

function textOf(node) {
  if (typeof node.value === 'string') return node.value;
  return (node.children || []).map(textOf).join('');
}

const STYLE = `
html,body { margin:0; padding:0; background:white; color:black; font:16px Arial,sans-serif; }
#fixture { box-sizing:border-box; width:960px; padding:16px; }
.table-scroll { overflow-x:auto; overflow-y:visible; max-width:100%; }
table { border-collapse:collapse; min-width:100%; }
th,td { border:1px solid #888; padding:8px; white-space:normal; overflow-wrap:anywhere; vertical-align:top; }
.diagram { overflow:visible; }
`;

async function run(request) {
  if (typeof request.source !== 'string') throw new Error('source must be a string');
  const items = parse(request.source);
  if (request.action === 'select') return {
    selector_id: SELECTOR,
    source_sha256: sha(request.source),
    constructs: [...new Set(items.map(item => item.kind))].sort(),
    instances: items.map(({kind, node}, index) => ({kind,
      instance_id: 'construct-' + (index + 1),
      source_range: {...node.position, offset_unit: 'utf-16-code-unit',
        line_base: 1, column_base: 1, end_exclusive: true},
      source_sha256: sha(request.source.slice(node.position.start.offset, node.position.end.offset))})),
  };
  if (request.action !== 'render') throw new Error('Unknown renderer action');
  const playwright = await dependency('playwright-core');
  const {chromium} = playwright.default || playwright;
  const browser = await chromium.launch({executablePath: request.browser, headless: true});
  const result = {selector_id: SELECTOR, source_sha256: sha(request.source),
    constructs: [], artifacts: [], result: 'pass', diagnostics: [],
    browser_version: browser.version()};
  try {
    const context = await browser.newContext({viewport: {width: 1024, height: 768},
      deviceScaleFactor: 1, locale: 'en-US', timezoneId: 'UTC', serviceWorkers: 'block'});
    // Network is unavailable while rendering. The only resource loader below
    // supplies the pinned local KaTeX fonts; no URL from the source is fetched.
    const fontRoot = path.join(moduleRoot, 'katex', 'dist', 'fonts');
    await context.route('**/*', async route => {
      const url = new URL(route.request().url());
      const name = path.basename(url.pathname);
      if (url.origin === 'https://cambium-render.invalid' &&
          url.pathname === '/fonts/' + name && fs.existsSync(path.join(fontRoot, name))) {
        await route.fulfill({body: fs.readFileSync(path.join(fontRoot, name)),
          contentType: name.endsWith('.woff2') ? 'font/woff2' : 'font/woff'});
      } else await route.abort();
    });
    const page = await context.newPage();
    await page.setContent('<!doctype html><html><head><base href="https://cambium-render.invalid/"></head><body><div id="fixture"></div></body></html>');
    await page.addStyleTag({content: STYLE});
    await page.addStyleTag({path: path.join(moduleRoot, 'katex', 'dist', 'katex.min.css')});
    await page.addScriptTag({path: path.join(moduleRoot, 'katex', 'dist', 'katex.min.js')});
    if (items.some(item => item.kind === 'mermaid-fence')) {
      await page.addScriptTag({path: path.join(moduleRoot, 'mermaid', 'dist', 'mermaid.min.js')});
      await page.evaluate(() => mermaid.initialize({startOnLoad: false, securityLevel: 'strict',
        deterministicIds: true, deterministicIDSeed: 'cambium-static-v1',
        fontFamily: 'Arial, sans-serif', theme: 'default'}));
    }
    for (let index = 0; index < items.length; index++) {
      const {kind, node} = items[index];
      const instanceId = 'construct-' + (index + 1);
      const item = {kind, instance_id: instanceId,
        source_range: {...node.position, offset_unit: 'utf-16-code-unit',
          line_base: 1, column_base: 1, end_exclusive: true},
        source_sha256: sha(request.source.slice(node.position.start.offset, node.position.end.offset)),
        acceptance: request.bindings[kind] || null, result: 'fail', artifact_ids: [],
        measurements: {}, diagnostics: []};
      result.constructs.push(item);
      try {
        if (request.bindings[kind] !== ACCEPTANCE[kind]) throw new Error(`Missing or invalid acceptance for ${kind}`);
        let content, mediaType;
        if (kind === 'mermaid-fence') {
          const rendered = await page.evaluate(async ({source, id}) => {
            document.querySelector('#fixture').replaceChildren();
            const {svg} = await mermaid.render(id, source);
            const host = document.querySelector('#fixture');
            host.innerHTML = svg;
            await document.fonts.ready;
            const image = host.querySelector('svg');
            if (!image) throw new Error('Mermaid produced no SVG');
            const box = image.getBBox();
            const view = image.viewBox.baseVal;
            const bounds = {x:box.x,y:box.y,width:box.width,height:box.height};
            if (![box.x,box.y,box.width,box.height,view.width,view.height].every(Number.isFinite) ||
                box.width <= 0 || box.height <= 0 || view.width <= 0 || view.height <= 0)
              throw new Error('Mermaid SVG has invalid geometry');
            return {svg: image.outerHTML, bounds, view_box: {x:view.x,y:view.y,width:view.width,height:view.height}};
          }, {source: node.value, id: 'cambium-' + sha(node.value).slice(7,23) + '-' + index});
          content = rendered.svg; mediaType = 'image/svg+xml';
          item.measurements = {bounds: rendered.bounds, view_box: rendered.view_box};
        } else if (kind === 'dollar-math') {
          content = katex.renderToString(node.value, {displayMode: node.type === 'math',
            output: 'htmlAndMathml', throwOnError: true, trust: false, strict: 'error', macros: {}});
          mediaType = 'text/html';
          item.measurements = await page.evaluate(async ({html, source}) => {
            const host = document.querySelector('#fixture'); host.innerHTML = html;
            await document.fonts.ready;
            const math = host.querySelector('.katex');
            const annotation = host.querySelector('math annotation[encoding="application/x-tex"]');
            if (!math || !annotation || annotation.textContent !== source || host.querySelector('.katex-error'))
              throw new Error('Math output does not preserve its source in MathML');
            const box = math.getBoundingClientRect();
            if (![box.width,box.height].every(Number.isFinite) || box.width <= 0 || box.height <= 0)
              throw new Error('Math output has invalid geometry');
            return {width:box.width,height:box.height,mathml_count:host.querySelectorAll('math').length};
          }, {html: content, source: node.value});
        } else {
          const tableHTML = await htmlFor(node);
          const expected = node.children.map(row => row.children.map(textOf));
          content = '<div class="table-scroll">' + tableHTML + '</div>'; mediaType = 'text/html';
          const rendered = await page.evaluate(async ({html, expected}) => {
            const host = document.querySelector('#fixture'); host.innerHTML = html;
            for (const code of host.querySelectorAll('code.language-math')) {
              const rendered = document.createElement('span');
              katex.render(code.textContent, rendered, {displayMode:code.classList.contains('math-display'),
                output:'htmlAndMathml',throwOnError:true,trust:false,strict:'error',macros:{}});
              code.replaceWith(rendered);
            }
            await document.fonts.ready;
            function originalText(node) {
              if (node.nodeType === Node.TEXT_NODE) return node.textContent;
              if (node.matches?.('.katex')) return node.querySelector('math annotation')?.textContent || '';
              return [...node.childNodes].map(originalText).join('');
            }
            const wrapper = host.querySelector('.table-scroll');
            const table = wrapper?.querySelector('table');
            if (!table) throw new Error('GFM renderer produced no table');
            const rows = [...table.rows].map(row => [...row.cells]);
            if (rows.length !== expected.length || rows.some((row,i) => row.length !== expected[i].length))
              throw new Error('Rendered table row/column coverage differs from AST');
            for (let r=0;r<rows.length;r++) for(let c=0;c<rows[r].length;c++) {
              const cell=rows[r][c], style=getComputedStyle(cell);
              if (originalText(cell) !== expected[r][c]) throw new Error('Rendered table cell text differs from AST');
              if (style.whiteSpace !== 'normal' || style.overflowWrap !== 'anywhere' ||
                  cell.scrollHeight > cell.clientHeight + 1)
                throw new Error('Table cell content is clipped');
            }
            const box=table.getBoundingClientRect();
            if (!Number.isFinite(box.width) || !Number.isFinite(box.height) || box.width<=0 || box.height<=0)
              throw new Error('Table has invalid geometry');
            if (wrapper.scrollWidth > wrapper.clientWidth && getComputedStyle(wrapper).overflowX !== 'auto')
              throw new Error('Wide table cannot scroll');
            return {html:wrapper.outerHTML,measurements:{rows:rows.length,columns:rows[0]?.length || 0,width:box.width,height:box.height,
              viewport_width:1024,wrapper_client_width:wrapper.clientWidth,wrapper_scroll_width:wrapper.scrollWidth}};
          }, {html: content, expected});
          content = rendered.html; item.measurements = rendered.measurements;
        }
        const artifactId = instanceId + '-artifact';
        result.artifacts.push({artifact_id: artifactId, media_type: mediaType, content, sha256: sha(content)});
        item.artifact_ids.push(artifactId); item.result = 'pass';
      } catch (error) {
        item.diagnostics.push(String(error.message || error)); result.result = 'fail';
      }
    }
  } finally { await browser.close(); }
  return result;
}

try {
  const chunks = []; for await (const chunk of process.stdin) chunks.push(chunk);
  const input = Buffer.concat(chunks).toString('utf8');
  process.stdout.write(JSON.stringify(await run(JSON.parse(input))));
} catch (error) {
  process.stdout.write(JSON.stringify({result:'fail',diagnostics:[String(error.message || error)]}));
  process.exitCode = 1;
}
