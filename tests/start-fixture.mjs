import {startServer} from './sandbox/server.mjs';
const {server, origin} = await startServer({port: 0, root: process.argv[2], site: process.argv[2], quiet: true});
console.log(origin);
process.on('SIGTERM', () => server.close());
