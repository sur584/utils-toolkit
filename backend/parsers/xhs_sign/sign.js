// Xiaohongshu x-s signature CLI wrapper.
// Reads JSON {api, a1, data, method} from argv[2] (or stdin), prints
// {xs, xt, xs_common, xray} as JSON on stdout. Errors go to stderr, exit 1.

const path = require('path');

function readInput() {
  const arg = process.argv[2];
  if (arg && arg.trim()) return arg;
  try {
    return require('fs').readFileSync(0, 'utf8');
  } catch (e) {
    return '';
  }
}

function main() {
  const raw = readInput();
  if (!raw || !raw.trim()) {
    process.stderr.write('empty input\n');
    process.exit(1);
  }
  let req;
  try {
    req = JSON.parse(raw);
  } catch (e) {
    process.stderr.write('bad json: ' + e.message + '\n');
    process.exit(1);
  }
  const api = req.api || '';
  const a1 = req.a1 || '';
  const data = req.data || '';
  const method = req.method || 'GET';

  const main = require(path.join(__dirname, 'xhs_main_260411.js'));
  const ret = main.get_request_headers_params(api, data, a1, method);

  // The vendored signature module emits noise on stdout during require
  // (env-shim output). Wrap the real payload in sentinels so the Python
  // caller can extract it reliably.
  const payload = JSON.stringify({
    xs: ret.xs,
    xt: String(ret.xt),
    xs_common: ret.xs_common,
  });
  process.stdout.write('\n__XHS_SIGN_BEGIN__' + payload + '__XHS_SIGN_END__\n');
}

try {
  main();
} catch (e) {
  process.stderr.write('sign error: ' + (e && e.stack ? e.stack : String(e)) + '\n');
  process.exit(1);
}
