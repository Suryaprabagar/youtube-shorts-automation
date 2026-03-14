import sys
import os

# Add the project root to sys.path
sys.path.append(os.getcwd())

from modules.subtitle_generator import SubtitleGenerator

def test_subtitle_generation():
    script = "Did you know space is completely silent even when massive stars explode?"
    duration = 10.0 # 10 seconds audio
    
    generator = SubtitleGenerator(wpm=150)
    subtitles = generator.generate(script, duration)
    
    print(f"Original Script: {script}")
    print(f"Audio Duration: {duration}s")
    print(f"Number of chunks: {len(subtitles)}")
    print("-" * 30)
    
    for start, end, text in subtitles:
        print(f"[{start:0.2f} - {end:0.2f}] {text}")
        
    # Basic assertions
    assert len(subtitles) > 0, "No subtitles generated"
    assert subtitles[-1][1] == duration, f"End time mismatch: {subtitles[-1][1]} != {duration}"
    
    for i in range(len(subtitles)):
        words = subtitles[i][2].split()
        assert 2 <= len(words) <= 4 or (i == len(subtitles)-1 and len(words) < 2), f"Chunk size mismatch in chunk {i}: {len(words)} words"

if __name__ == "__main__":
    try:
        test_subtitle_generation()
        print("\n✅ Subtitle generation test passed!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
