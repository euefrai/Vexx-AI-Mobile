const fs = require('fs'), zlib = require('zlib');
const target = '../../public/vendor/three-engine.js';
fs.writeFileSync(target+'.gz', zlib.gzipSync(fs.readFileSync(target), {level:9}));
fs.copyFileSync('node_modules/three/LICENSE','../../public/vendor/THREE-LICENSE.txt');
