#!/usr/bin/env python3
import sys
import os
import json
import argparse
import urllib.request
import urllib.error
import subprocess

def get_model_and_options(difficulty: str = None) -> tuple[str, dict]:
    # Determine the model based on difficulty and environment overrides
    difficulty = (difficulty or os.environ.get("NEXUS_TASK_DIFFICULTY") or "").strip().lower()
    
    # Model overrides
    env_override = os.environ.get("NEXUS_OLLAMA_REFLEX_MODEL") or os.environ.get("MODEL")
    if env_override:
        model_name = env_override
    elif difficulty == "easy":
        model_name = os.environ.get("NEXUS_OLLAMA_MODEL_EASY") or "qwen2.5-coder:7b"
    elif difficulty == "medium":
        model_name = os.environ.get("NEXUS_OLLAMA_MODEL_MEDIUM") or "qwen2.5-coder:14b"
    elif difficulty == "hard":
        model_name = os.environ.get("NEXUS_OLLAMA_MODEL_HARD") or "qwen2.5-coder:14b"
    else:
        model_name = "qwen2.5-coder:14b"

    # Default performance options for Apple Silicon Mac (Metal acceleration, CPU threading)
    options = {
        "temperature": 0.1,
        "num_gpu": int(os.environ.get("NEXUS_OLLAMA_NUM_GPU", "99")),
        "num_thread": int(os.environ.get("NEXUS_OLLAMA_NUM_THREAD", "8")),
        "num_ctx": 32768,
        "num_predict": 4096,
    }
    
    # Optimize context size for easy difficulty to run even faster
    if difficulty == "easy":
        options["num_ctx"] = 16384
        options["num_predict"] = 2048

    return model_name, options

def main():
    parser = argparse.ArgumentParser(description="Mock Gemini CLI for Local Ollama bridging")
    parser.add_argument("-m", "--model", default="gemini-3-flash-preview")
    parser.add_argument("-p", "--prompt", default="")
    parser.add_argument("--skip-trust", action="store_true")
    parser.add_argument("--yolo", action="store_true")
    parser.add_argument("--approval-mode", default="auto_edit")
    parser.add_argument("--output-format", default="json")
    
    # Absorb all unknown options silently
    args, unknown = parser.parse_known_args()

    # Read stdin payload if present
    stdin_content = ""
    if not sys.stdin.isatty():
        stdin_content = sys.stdin.read()

    # Determine if we should route to local Ollama
    use_local = os.environ.get("USE_LOCAL_OLLAMA", "").strip().lower() in {"1", "true", "yes", "on"}
    
    if use_local:
        difficulty = os.environ.get("NEXUS_TASK_DIFFICULTY")
        model_name, options = get_model_and_options(difficulty)
        endpoint = os.environ.get("NEXUS_OLLAMA_ENDPOINT", "http://localhost:11434").rstrip("/")
        
        # Combine System Prompt and Prompt payload
        full_prompt = args.prompt
        if stdin_content:
            full_prompt = f"{args.prompt}\n\n[PAYLOAD]\n{stdin_content}"
            
        payload = {
            "model": model_name,
            "prompt": full_prompt,
            "stream": False,
            "options": options
        }
        
        try:
            req = urllib.request.Request(
                f"{endpoint}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            # Timeout set to 300 seconds for heavy 14b local generation
            with urllib.request.urlopen(req, timeout=300) as response:
                resp_data = json.loads(response.read().decode("utf-8"))
                response_text = resp_data.get("response", "")
                
                # Estimate token counts
                tokens = len(full_prompt + response_text) // 4
                
                output_json = {
                    "response": response_text,
                    "usageMetadata": {
                        "totalTokenCount": tokens,
                        "promptTokenCount": len(full_prompt) // 4,
                        "candidatesTokenCount": len(response_text) // 4
                    }
                }
                
                print(json.dumps(output_json, ensure_ascii=False))
                sys.exit(0)
        except Exception as e:
            err_json = {
                "status": "FAIL",
                "summary": f"Ollama forward failed: {str(e)}",
                "violations": []
            }
            print(json.dumps(err_json))
            sys.exit(1)
    else:
        # Fallback to real gemini CLI
        real_gemini = "/Users/jameschen/.npm-global/bin/gemini"
        cmd = [real_gemini]
        cmd.extend(sys.argv[1:])
        
        # Run real subprocess and pipe streams
        proc = subprocess.run(
            cmd,
            input=stdin_content,
            text=True,
            capture_output=True,
            env=os.environ
        )
        sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        sys.exit(proc.returncode)

if __name__ == "__main__":
    main()
