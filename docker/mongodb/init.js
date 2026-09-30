// ============================================================================
// Cogito — MongoDB init: turn the node into a single-node replica set so
// change streams + search work. Idempotent and defensive.
// ============================================================================

function tryInitReplicaSet() {
  try {
    // If already a replica set and PRIMARY, nothing to do.
    const status = db.adminCommand({ replSetGetStatus: 1 });
    if (status.ok && status.myState === 1) {
      print(">>> replica set already PRIMARY (rs0)");
      return;
    }
  } catch (e) {
    print(">>> replSetGetStatus: " + e.message);
  }
  const conf = {
    _id: "rs0",
    version: 1,
    members: [{ _id: 0, host: "mongodb:27017" }],
  };
  try {
    printjson(db.adminCommand({ replSetInitiate: conf }));
  } catch (e) {
    if (/already initialized|already exists|already configured/i.test(e.message)) {
      print(">>> replica set already initialized");
    } else if (/not authorized/i.test(e.message)) {
      print(">>> retrying initiate after delay");
    } else {
      print(">>> initiate result: " + e.message);
    }
  }
}

function ensureCollections() {
  const d = db.getSiblingDB("cogito");
  const names = [
    "documents", "chunks", "memories", "query_logs",
    "eval_results", "feedback", "conversations",
  ];
  names.forEach((n) => {
    if (!d.getCollectionNames().includes(n)) {
      d.createCollection(n);
      print(">>> created collection: " + n);
    }
  });
}

tryInitReplicaSet();
ensureCollections();
print(">>> mongodb init complete");