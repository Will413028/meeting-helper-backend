import subprocess

'''
### command line to run whisperx diarization
# multiple speaker, chinese chunk_size=6

### install whisperx and huggingface_hub
! pip3 install git+https://github.com/ifeimi/whisperx.git -q
! pip3 install -U huggingface_hub -q

### latest model, need to accept the user agreement: https://huggingface.co/pyannote/speaker-diarization-3.1
speaker-diarization-3.1
'''

def whisperx_diarize(audio_path: str, output_dir: str,
                     model: str = "large-v3", align_model: str = "", language: str = 'zh', chunk_size: int = 6,
                     hug_token: str = "", initial_prompt: str = ""):
    command = (f"whisperx '{audio_path}' "
               f"--model {model} "
               f"--align_model {align_model} "
               f"--diarize --min_speakers=2 --max_speakers=4 "  
               f"--chunk_size {chunk_size} "
               f"--compute_type float32 "  # ["float16", "float32", "int8"]
               f"--hf_token {hug_token} "

               # whisper parameters
               f"--temperature 0.1 "
               f"--fp16 False "
               f"--language {language} "
               f"--initial_prompt '{initial_prompt}' "
               f"--condition_on_previous_text False "

               # output
               f"--output_dir '{output_dir}' "
               f"--output_format srt"
               )
    subprocess.call(command, shell=True)

if __name__ == "__main__":
    demo_audio_path = "./audio.mp4"
    # initial_prompt = "填入你覺得適合的引導提示詞"
    whisperx_diarize(demo_audio_path,
                     output_dir="./output-test",
                     model="large-v3",
                     align_model="WAV2VEC2_ASR_LARGE_LV60K_960H",
                     language='zh',
                     hug_token="REDACTED",
                     chunk_size=6,
                    #  initial_prompt=initial_prompt
                     )
