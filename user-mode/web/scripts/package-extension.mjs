// A small, reproducible ZIP (stored entries, no compression or dependencies).
import { readFile, mkdir, writeFile } from 'node:fs/promises';
const source = new URL('../../extension/', import.meta.url);
const output = new URL('../public/guider-extension.zip', import.meta.url);
const files = ['manifest.json', 'background.js', 'controller.js', 'overlay.js', 'popup.html', 'popup.css', 'popup.js', 'README.md'];
const table = Array.from({ length: 256 }, (_, value) => {
  for (let bit = 0; bit < 8; bit++) value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
  return value >>> 0;
});
const locals = [], directory = [];
let offset = 0;
for (const file of files) {
  const name = Buffer.from(file), data = await readFile(new URL(file, source));
  let crc = 0xffffffff;
  for (const byte of data) crc = table[(crc ^ byte) & 255] ^ (crc >>> 8);
  crc = (crc ^ 0xffffffff) >>> 0;
  const local = Buffer.alloc(30); local.writeUInt32LE(0x04034b50); local.writeUInt16LE(20, 4);
  local.writeUInt16LE(33, 12); // 1980-01-01
  local.writeUInt32LE(crc, 14); local.writeUInt32LE(data.length, 18); local.writeUInt32LE(data.length, 22);
  local.writeUInt16LE(name.length, 26);
  const central = Buffer.alloc(46); central.writeUInt32LE(0x02014b50); central.writeUInt16LE(20, 4); central.writeUInt16LE(20, 6);
  central.writeUInt16LE(33, 14); central.writeUInt32LE(crc, 16); central.writeUInt32LE(data.length, 20); central.writeUInt32LE(data.length, 24);
  central.writeUInt16LE(name.length, 28); central.writeUInt32LE(offset, 42);
  locals.push(local, name, data); directory.push(central, name); offset += local.length + name.length + data.length;
}
const central = Buffer.concat(directory), end = Buffer.alloc(22);
end.writeUInt32LE(0x06054b50); end.writeUInt16LE(files.length, 8); end.writeUInt16LE(files.length, 10);
end.writeUInt32LE(central.length, 12); end.writeUInt32LE(offset, 16);
await mkdir(new URL('../public/', import.meta.url), { recursive: true });
await writeFile(output, Buffer.concat([...locals, central, end]));
console.log(`Packaged Guider tab extension (${files.length} files).`);
