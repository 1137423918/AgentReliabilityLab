// Offline audit of the pinned llama.cpp common chat path. No inference context.
#include "chat.h"
#include "llama.h"
#include "server-common.h"
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>

static std::vector<llama_token> tokenize(const llama_vocab *vocab, const std::string &text) {
    int count = llama_tokenize(vocab, text.data(), static_cast<int>(text.size()), nullptr, 0, false, true);
    std::vector<llama_token> result(count < 0 ? -count : count);
    count = llama_tokenize(vocab, text.data(), static_cast<int>(text.size()), result.data(), result.size(), false, true);
    if (count < 0) throw std::runtime_error("tokenization failed");
    result.resize(count);
    return result;
}

int main(int argc, char **argv) {
    if (argc != 3) return 2;
    try {
        llama_backend_init();
        auto params = llama_model_default_params();
        ggml_backend_dev_t devices[] = {nullptr};
        params.devices = devices;
        params.n_gpu_layers = 0;
        params.vocab_only = true;
        auto *model = llama_model_load_from_file(argv[1], params);
        if (!model) return 3;
        const auto *vocab = llama_model_get_vocab(model);
        auto templates = common_chat_templates_init(model, "");
        server_chat_params options{};
        options.use_jinja = true;
        options.prefill_assistant = true;
        options.reasoning_format = COMMON_REASONING_FORMAT_NONE;
        options.chat_template_kwargs["enable_thinking"] = "false";
        options.enable_thinking = false;
        options.tmpls = common_chat_templates_init(model, "");
        std::ifstream file(argv[2]);
        if (!file) return 4;
        const std::string json_text((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
        common_json cases = common_json::parse(json_text);
        for (const auto &item : cases) {
            const auto &body = item.at("body");
            // Restricted mapping audited against server-common.cpp at 4783b114.
            // It is NOT an invocation of the server HTTP request converter.
            common_chat_templates_inputs inputs;
            inputs.messages = common_chat_msgs_parse_oaicompat(body.at("messages"));
            inputs.tools = common_chat_tools_parse_oaicompat(body.at("tools"));
            inputs.tool_choice = COMMON_CHAT_TOOL_CHOICE_AUTO;
            inputs.parallel_tool_calls = common_chat_templates_get_caps(templates.get()).at("supports_parallel_tool_calls").get<bool>();
            inputs.reasoning_format = COMMON_REASONING_FORMAT_NONE;
            inputs.enable_thinking = false;
            inputs.chat_template_kwargs["enable_thinking"] = "false";
            auto rendered = common_chat_templates_apply(templates.get(), inputs);
            auto server_body = body;
            std::vector<raw_buffer> files;
            common_chat_session session;
            const auto converted = oaicompat_chat_params_parse(vocab, server_body, options, files, session);
            if (!files.empty() || !converted.at("prompt").is_string()) return 6;
            const auto text = converted.at("prompt").get<std::string>();
            common_json parts = common_json::array();
            for (const auto &part : session.prompt().parts) {
                parts.push_back({{"text", part.text}, {"is_input", part.is_input}});
            }
            std::cout << common_json({{"id", item.at("id")}, {"prompt", text},
                {"common_chat_prompt", rendered.prompt.str()},
                {"parts", parts}, {"flattened_parse_special_tokens", tokenize(vocab, text)},
                {"format", common_chat_format_name(rendered.format)},
                {"template", common_chat_templates_source(templates.get())}}).dump() << '\n';
        }
        templates.reset();
        options.tmpls.reset();
        llama_model_free(model);
        llama_backend_free();
    } catch (const std::exception &e) {
        std::cerr << e.what() << '\n';
        return 5;
    }
}
