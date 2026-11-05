"""Optional: fetch a short public Vietnamese conversation for ASR verification."""
from pathlib import Path
import json
import urllib.request
import wave

ROOT=Path(__file__).resolve().parent.parent
URL="https://datasets-server.huggingface.co/first-rows?dataset=humyn-labs%2FAsian-High-Fidelity-ASR-Dataset&config=default&split=train"


def main():
    with urllib.request.urlopen(URL,timeout=60) as source:
        data=json.load(source)
    row=data["rows"][0]["row"]
    audio=row["audio"]
    if isinstance(audio,list):
        audio=audio[0]
    url=audio.get("src") or audio.get("url")
    if not url:
        raise RuntimeError(f"Audio URL unavailable: {list(audio.keys())}")
    folder=ROOT/".tmp"/"fixtures"
    folder.mkdir(parents=True,exist_ok=True)
    # Only the first 8 seconds are read, not the full multi-minute recording.
    with urllib.request.urlopen(url,timeout=60) as source, wave.open(source,"rb") as audio:
        params=audio.getparams()
        pcm=audio.readframes(audio.getframerate()*8)
        with wave.open(str(folder/"vietnamese.wav"),"wb") as out:
            out.setparams(params)
            out.writeframes(pcm)
    segments=json.loads(row["transcript_json"])
    reference=" ".join(s["text"] for s in segments if float(s["end"].split(":")[-1])<=8 and s["end"].startswith("00:00:"))
    metadata={"dataset":"humyn-labs/Asian-High-Fidelity-ASR-Dataset","config":"default","split":"train",
              "file":row["file_name"],"seconds":8,"reference":reference,
              "source":URL}
    (folder/"vietnamese.json").write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(metadata,ensure_ascii=True))


if __name__=="__main__":
    main()
