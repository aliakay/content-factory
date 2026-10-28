"""Text embeddings for near-duplicate detection (discovery candidates, already-made topics).

Preferred: fastembed (ONNX, no torch, ~120 MB model, fast on CPU) with a multilingual MiniLM so Turkish and English
titles about the same story land close together. Install on the VM with
    ~/.local/bin/uv pip install --python .venv/bin/python fastembed
Without it (or offline) a hashed character-trigram vector is used: weaker on paraphrases, still far better than word
overlap on reworded headlines. Vectors are cached in factory.db (table `embeddings`), keyed by model + text hash.
`backend()` says which one is active; thresholds differ per backend (see THRESH).
"""
import hashlib, os, re, unicodedata

import numpy as np

MODEL = os.environ.get("CF_EMBED_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
HASH_DIM = 1024
# cosine at or above which two texts are "the same story" / "a topic we already did"
THRESH = {"fastembed": {"same": 0.78, "seen": 0.84, "press": 0.70}, "hash": {"same": 0.60, "seen": 0.66, "press": 0.45}}
# "press": a paper title vs a news headline about it (academic wording vs news wording, so a lower bar)
SCHEMA = "CREATE TABLE IF NOT EXISTS embeddings (key TEXT PRIMARY KEY, model TEXT, vec BLOB)"
_model = None
_backend = None


def backend():
    """'fastembed' when the library and its model load, else 'hash'. Decided once per process."""
    global _model, _backend
    if _backend is None:
        if os.environ.get("CF_EMBED") == "hash":
            _backend = "hash"
        else:
            try:
                from fastembed import TextEmbedding
                _model = TextEmbedding(MODEL)
                _backend = "fastembed"
            except Exception:   # not installed, model download blocked, ...
                _backend = "hash"
    return _backend


STOP = set("the a an of to in on for and or at by with from is are was were be as it its this that new says say said "
           "after over how why what who will can could may just into than more about up out not has have had here now "
           "launches launch releases release unveils unveil announces announce reveals reveal report reports found finds "
           "ve bir bu da de ile için yeni".split())


def _norm_word(w):
    w = unicodedata.normalize("NFKD", w.replace("ı", "i").replace("İ", "I"))
    return re.sub(r"[^a-z0-9$%.-]+", "", "".join(c for c in w if not unicodedata.combining(c)).lower()).strip(".-")


def hash_vec(text):
    """Offline fallback: hashed character trigrams + whole words, stop words dropped, names and numbers weighted up
    (a story is mostly its entities: 'OpenAI', 'GPT-6', 'Moon', '20%'). L2-normalised, HASH_DIM buckets."""
    v = np.zeros(HASH_DIM, dtype=np.float32)
    for raw in re.findall(r"[\w$%.-]+", str(text or "")):
        w = _norm_word(raw)
        if len(w) < 2 or w in STOP:
            continue
        weight = 2.0 if (raw[:1].isupper() or any(c.isdigit() for c in w)) else 1.0
        g = f" {w} "
        feats = [(g[i:i + 3], 0.35) for i in range(len(g) - 2)] + [("w:" + w[:5], 1.0)]
        for f, k in feats:
            h = int.from_bytes(hashlib.md5(f.encode()).digest()[:4], "little")
            v[h % HASH_DIM] += weight * k
    n = np.linalg.norm(v)
    return v / n if n else v


def vectors(texts, con=None):
    """Unit vectors for `texts` (np.ndarray, one row per text), cached in `con` when given."""
    be = backend()
    key = (MODEL if be == "fastembed" else f"hash{HASH_DIM}")
    out, todo = [None] * len(texts), []
    if con is not None:
        con.execute(SCHEMA)
    for i, t in enumerate(texts):
        k = hashlib.sha1(f"{key}|{t}".encode()).hexdigest()
        row = con.execute("SELECT vec FROM embeddings WHERE key=?", (k,)).fetchone() if con is not None else None
        if row:
            out[i] = np.frombuffer(row[0], dtype=np.float32)
        else:
            todo.append((i, k, t))
    if todo:
        if be == "fastembed":
            new = [np.asarray(v, dtype=np.float32) for v in _model.embed([t for _, _, t in todo])]
            new = [v / (np.linalg.norm(v) or 1) for v in new]
        else:
            new = [hash_vec(t) for _, _, t in todo]
        for (i, k, _), v in zip(todo, new):
            out[i] = v
            if con is not None:
                con.execute("INSERT OR REPLACE INTO embeddings VALUES (?,?,?)", (k, key, v.astype(np.float32).tobytes()))
        if con is not None:
            con.commit()
    dim = len(out[0]) if out else HASH_DIM
    return np.vstack(out) if out else np.zeros((0, dim), dtype=np.float32)


def threshold(kind):
    return THRESH[backend()][kind]


def best_match(vec, mat):
    """(index, cosine) of the closest row of `mat` to `vec`, or (None, 0.0) for an empty matrix."""
    if mat is None or not len(mat):
        return None, 0.0
    sims = mat @ vec
    i = int(np.argmax(sims))
    return i, float(sims[i])
