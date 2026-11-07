// Local MongoDB for LibreChat P1, via mongodb-memory-server.
// Copy to D:/luno_external/librechat/scripts/dev-mongo.cjs and run with:
//   node scripts/dev-mongo.cjs
// It downloads a MongoDB binary on first run and keeps it alive on port 27017.

const { MongoMemoryServer } = require('mongodb-memory-server');

(async () => {
  const mongod = await MongoMemoryServer.create({
    instance: { port: 27017, dbName: 'LibreChat' },
  });
  console.log('MONGO_URI=' + mongod.getUri('LibreChat'));
  const stop = async () => {
    try {
      await mongod.stop();
    } catch {}
    process.exit(0);
  };
  process.on('SIGINT', stop);
  process.on('SIGTERM', stop);
  setInterval(() => {}, 1 << 30);
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
