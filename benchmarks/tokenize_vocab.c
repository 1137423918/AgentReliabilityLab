/* Offline exact GGUF vocabulary tokenization. No inference context or weights.
 * Compile against the pinned llama.cpp headers and libllama used by the server.
 * stdout: one JSON array of token IDs per UTF-8 file argument, in argument order.
 */
#include "llama.h"
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    if (argc < 3) { fprintf(stderr, "usage: tokenize_vocab model.gguf text-file...\n"); return 2; }
    llama_backend_init();
    struct llama_model_params params = llama_model_default_params();
    ggml_backend_dev_t devices[] = {NULL};
    params.devices = devices;
    params.n_gpu_layers = 0;
    params.vocab_only = true;
    struct llama_model *model = llama_model_load_from_file(argv[1], params);
    if (!model) return 3;
    const struct llama_vocab *vocab = llama_model_get_vocab(model);
    for (int i = 2; i < argc; i++) {
        FILE *f = fopen(argv[i], "rb");
        if (!f || fseek(f, 0, SEEK_END)) return 4;
        long size = ftell(f);
        if (size < 0 || size > 16 * 1024 * 1024 || fseek(f, 0, SEEK_SET)) return 5;
        char *text = malloc((size_t)size + 1);
        if (!text || fread(text, 1, size, f) != (size_t)size) return 6;
        fclose(f);
        int needed = llama_tokenize(vocab, text, (int)size, NULL, 0, false, true);
        int capacity = needed < 0 ? -needed : needed;
        llama_token *tokens = malloc(((size_t)capacity + 1) * sizeof(llama_token));
        if (!tokens) return 7;
        int count = llama_tokenize(vocab, text, (int)size, tokens, capacity, false, true);
        if (count < 0 || count != capacity) return 8;
        printf("[");
        for (int j = 0; j < count; j++) printf("%s%d", j ? "," : "", tokens[j]);
        printf("]\n");
        free(tokens); free(text);
    }
    llama_model_free(model);
    llama_backend_free();
    return 0;
}
