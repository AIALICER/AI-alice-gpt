import torch
from transformers import pipeline

# モデルIDの指定（ITはInstruction Tunedの略）
MODEL_ID = "google/gemma-4-E4B-it"

# パイプラインの作成（any-to-anyでマルチモーダル対応）
pipe = pipeline(
    task="any-to-any",
    model=MODEL_ID,
    model_kwargs={
        "torch_dtype": torch.bfloat16,
        "quantization_config": {"load_in_4bit": True} # 4bitでメモリ節約
    },
    device_map="auto"
)

# 実行
prompt = "Gemma 4のE4Bモデルの特徴を短く教えて。"
outputs = pipe(prompt, max_new_tokens=200)

print(outputs[0]["generated_text"])