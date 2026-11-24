"""Local CPU-only E5 embeddings behind LlamaIndex's real embedding interface."""
from pathlib import Path
import hashlib
import json
from llama_index.core.embeddings import BaseEmbedding
from llama_index.core.bridge.pydantic import PrivateAttr


class LocalE5Embedding(BaseEmbedding):
    _model = PrivateAttr()
    _tokenizer = PrivateAttr()
    _fingerprint = PrivateAttr()
    _observer = PrivateAttr(default=None)
    _counts = PrivateAttr()

    def __init__(self, directory, *, observer=None, batch_size=4):
        import torch
        from transformers import AutoModel, AutoTokenizer
        directory = Path(directory); manifest = json.loads((directory/'model-manifest.json').read_text())
        if manifest['model_id'] != 'intfloat/multilingual-e5-small': raise ValueError('Expected the declared E5 model')
        for item in manifest['files']:
            p = directory/item['path']
            if p.is_symlink() or p.stat().st_size != item['bytes'] or hashlib.sha256(p.read_bytes()).hexdigest() != item['sha256']:
                raise ValueError('Model asset fingerprint changed')
        super().__init__(model_name=manifest['model_id']+'@'+manifest['revision'], embed_batch_size=batch_size)
        torch.set_num_threads(2)
        self._tokenizer = AutoTokenizer.from_pretrained(str(directory), local_files_only=True, trust_remote_code=False)
        self._model = AutoModel.from_pretrained(str(directory), local_files_only=True, trust_remote_code=False,
                                               use_safetensors=True).to('cpu').eval()
        self._fingerprint = {'model': self.model_name, 'model_manifest_sha256': hashlib.sha256((directory/'model-manifest.json').read_bytes()).hexdigest(),
                             'pooling': 'attention-mask mean;L2 normalization', 'dimensions': 384, 'device': 'cpu', 'max_tokens': 512}
        self._observer = observer; self._counts = {'reserved_forwards': 0, 'completed_forwards': 0, 'text_inputs': 0, 'query_inputs': 0}

    @property
    def fingerprint(self): return dict(self._fingerprint)

    @property
    def counts(self): return dict(self._counts)

    def tokens(self, text): return self._tokenizer.encode(text, add_special_tokens=False)

    def _encode(self, texts, kind):
        import torch
        prefix = 'query: ' if kind == 'query' else 'passage: '
        encoded = self._tokenizer([prefix+text for text in texts], padding=True, truncation=False, return_tensors='pt')
        if encoded['input_ids'].shape[1] > 512: raise ValueError('Embedding input exceeds512tokens;no silent truncation')
        event = {'kind': kind, 'inputs': len(texts), 'input_sha256': [hashlib.sha256(t.encode()).hexdigest() for t in texts]}
        if self._observer: self._observer('reserved', event)
        self._counts['reserved_forwards'] += 1; self._counts[kind+'_inputs'] += len(texts)
        with torch.inference_mode():
            hidden = self._model(**encoded).last_hidden_state
            weights = encoded['attention_mask'].unsqueeze(-1)
            vectors = (hidden*weights).sum(dim=1)/weights.sum(dim=1)
            vectors = torch.nn.functional.normalize(vectors, p=2, dim=1)
            if vectors.shape != (len(texts), 384) or not bool(torch.isfinite(vectors).all()): raise ValueError('Invalid embedding output')
            output = vectors.tolist()
        self._counts['completed_forwards'] += 1
        if self._observer: self._observer('completed', event)
        return output

    def _get_query_embedding(self, query): return self._encode([query], 'query')[0]
    async def _aget_query_embedding(self, query): return self._get_query_embedding(query)
    def _get_text_embedding(self, text): return self._encode([text], 'text')[0]
    def _get_text_embeddings(self, texts): return self._encode(texts, 'text')
