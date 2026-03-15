"""
test_video_downloader.py — Unit tests for the video selection logic.
Run with:  python test_video_downloader.py
"""
import random
import sys

# ── Inline the logic under test (no real HTTP calls) ─────────────────────────

SPACE_CONTENT_KEYWORDS = {
    "space", "galaxy", "nebula", "star", "stars", "planet", "cosmos",
    "universe", "astronaut", "milky way", "black hole", "supernova",
    "telescope", "solar", "moon", "sun", "mars", "jupiter", "saturn",
    "earth orbit", "astronomer", "astronomy", "rocket", "nasa", "spacex",
    "comet", "asteroid", "meteor", "night sky", "timelapse sky",
    "cosmic", "orbit", "spacecraft", "satellite", "hubble", "stellar",
}
PREFERRED_QUALITY = ["hd", "sd"]
MIN_DURATION, MAX_DURATION = 15, 70
TOP_N_RANDOM = 5


def is_space_related(video):
    alt = (video.get("alt") or "").lower()
    user_name = (video.get("user", {}).get("name") or "").lower()
    combined = f"{alt} {user_name}"
    for kw in SPACE_CONTENT_KEYWORDS:
        if kw in combined:
            return True
    return False


def pick_best(videos, used_ids, require_space=True):
    scored = []
    for video in videos:
        vid = str(video.get("id", ""))
        if vid and vid in used_ids:
            continue
        if require_space and not is_space_related(video):
            continue
        score = 0
        duration = float(video.get("duration", 0))
        if 20 <= duration <= 59:
            score += 1
        elif duration < MIN_DURATION or duration > MAX_DURATION:
            score -= 1
        w, h = video.get("width", 0), video.get("height", 0)
        if h > w:
            score += 3
        best_url, best_quality = None, None
        for q in PREFERRED_QUALITY:
            for vf in video.get("video_files", []):
                if vf.get("quality") == q and best_url is None:
                    best_url, best_quality = vf["link"], q
        if best_quality == "hd":
            score += 2
        elif best_quality == "sd":
            score += 1
        if best_url is None and video.get("video_files"):
            best_url = video["video_files"][0]["link"]
        if best_url:
            scored.append((score, duration, best_url, video.get("alt", ""), video.get("id")))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    return random.choice(scored[: min(TOP_N_RANDOM, len(scored))])


# ── Fixtures ──────────────────────────────────────────────────────────────────

FAKE_VIDEOS = [
    {
        "id": 1, "duration": 30, "width": 1080, "height": 1920,
        "alt": "Beautiful galaxy nebula in deep space",
        "user": {"name": "NASAShots"},
        "video_files": [{"quality": "hd", "link": "http://x.com/v1.mp4"}],
    },
    {
        "id": 2, "duration": 25, "width": 1080, "height": 1920,
        "alt": "Kid playing in park",
        "user": {"name": "UserA"},
        "video_files": [{"quality": "hd", "link": "http://x.com/v2.mp4"}],
    },
    {
        "id": 3, "duration": 35, "width": 1080, "height": 1920,
        "alt": "Stars timelapse night sky cosmos",
        "user": {"name": "Astrophoto"},
        "video_files": [{"quality": "hd", "link": "http://x.com/v3.mp4"}],
    },
]

# ── Tests ─────────────────────────────────────────────────────────────────────

def test_space_filter_blocks_non_space():
    result = pick_best(FAKE_VIDEOS, used_ids=set(), require_space=True)
    assert result is not None, "Expected a result"
    assert result[4] in (1, 3), f"Expected id 1 or 3, got {result[4]}"
    print(f"PASS test_space_filter_blocks_non_space: chose id={result[4]}")


def test_used_id_skip():
    result = pick_best(FAKE_VIDEOS, used_ids={"1", "3"}, require_space=True)
    assert result is None, f"Expected None (all space vids used), got {result}"
    print("PASS test_used_id_skip")


def test_relaxed_fallback_picks_non_space():
    result = pick_best(FAKE_VIDEOS, used_ids={"1", "3"}, require_space=False)
    assert result is not None and result[4] == 2, f"Expected id 2, got {result}"
    print(f"PASS test_relaxed_fallback_picks_non_space: chose id={result[4]}")


def test_randomised_selection():
    ids_seen = set()
    for _ in range(50):
        r = pick_best(FAKE_VIDEOS, used_ids=set(), require_space=True)
        if r:
            ids_seen.add(r[4])
    assert len(ids_seen) > 1, f"Randomisation not working, only got ids: {ids_seen}"
    print(f"PASS test_randomised_selection: saw ids {ids_seen} over 50 runs")


if __name__ == "__main__":
    tests = [
        test_space_filter_blocks_non_space,
        test_used_id_skip,
        test_relaxed_fallback_picks_non_space,
        test_randomised_selection,
    ]
    failures = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            print(f"FAIL {t.__name__}: {e}")
            failures += 1
    if failures:
        print(f"\n{failures}/{len(tests)} test(s) FAILED")
        sys.exit(1)
    else:
        print(f"\nAll {len(tests)} tests PASSED")
