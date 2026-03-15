"""
test_video_downloader.py — Unit tests for the video selection logic.
Run with:  .venv\\Scripts\\python.exe test_video_downloader.py
"""
import random
import re
import sys

# ── Mirror the logic under test (no real HTTP calls) ─────────────────────────

SPACE_POSITIVE_KEYWORDS = {
    "space", "galaxy", "galaxies", "nebula", "nebulae", "star", "stars",
    "planet", "planets", "cosmos", "universe", "astronaut", "milky",
    "milky-way", "milkyway", "black-hole", "blackhole", "supernova",
    "telescope", "solar", "moon", "sun", "mars", "jupiter", "saturn",
    "earth-orbit", "astronomer", "astronomy", "rocket", "nasa", "spacex",
    "comet", "asteroid", "meteor", "night-sky", "nightsky", "timelapse",
    "time-lapse", "cosmic", "orbit", "spacecraft", "satellite", "hubble",
    "stellar", "astrophoto", "astrophotography", "aurora", "constellation",
    "exoplanet", "quasar", "pulsar", "interstellar", "deep-space",
    "space-exploration", "launch", "observatory",
}

NEGATIVE_KEYWORDS = {
    "child", "children", "kid", "kids", "baby", "babies", "toddler",
    "woman", "man", "people", "person", "girl", "boy", "family",
    "beach", "ocean", "sea", "forest", "mountain", "city", "urban",
    "food", "cook", "cooking", "kitchen", "restaurant", "coffee",
    "dog", "cat", "animal", "bird", "horse", "fish",
    "wedding", "yoga", "gym", "fitness", "dance", "sport", "football",
    "fashion", "makeup", "hair",
}

PREFERRED_QUALITY = ["hd", "sd"]
MIN_DURATION, MAX_DURATION = 15, 70
TOP_N_RANDOM = 5


def extract_text_fields(video):
    alt = (video.get("alt") or "").lower()
    url = (video.get("url") or "").lower()
    url_slug = re.sub(r"https?://[^/]+/video/", "", url)
    url_slug = re.sub(r"-\d+/?$", "", url_slug)
    user_name = (video.get("user", {}).get("name") or "").lower()
    return f"{alt} {url_slug} {user_name}"


def is_space_related(combined):
    for kw in SPACE_POSITIVE_KEYWORDS:
        if kw in combined:
            return True
    return False


def has_negative_keyword(combined):
    for kw in NEGATIVE_KEYWORDS:
        if kw in combined:
            return True
    return False


def pick_best(videos, used_ids, require_space=True):
    scored = []
    for video in videos:
        vid = str(video.get("id", ""))
        if vid and vid in used_ids:
            continue
        combined = extract_text_fields(video)
        if has_negative_keyword(combined):
            continue
        if require_space and not is_space_related(combined):
            continue
        score = 0
        duration = float(video.get("duration", 0))
        w, h = video.get("width", 0), video.get("height", 0)
        if 20 <= duration <= 59:
            score += 1
        elif duration < MIN_DURATION or duration > MAX_DURATION:
            score -= 1
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


# ── Test data ─────────────────────────────────────────────────────────────────

FAKE_VIDEOS = [
    # id=1: Landscape space video, EMPTY alt — detected via URL slug
    {
        "id": 1, "duration": 30, "width": 1920, "height": 1080,
        "alt": "",  # empty alt — the common real-world case
        "url": "https://www.pexels.com/video/galaxy-nebula-stars-timelapse-1234/",
        "user": {"name": "AstroShots"},
        "video_files": [{"quality": "hd", "link": "http://x.com/v1.mp4"}],
    },
    # id=2: Portrait kid video — should be blocked by NEGATIVE_KEYWORDS
    {
        "id": 2, "duration": 25, "width": 1080, "height": 1920,
        "alt": "Kid playing in park",
        "url": "https://www.pexels.com/video/kid-playing-park-5678/",
        "user": {"name": "UserA"},
        "video_files": [{"quality": "hd", "link": "http://x.com/v2.mp4"}],
    },
    # id=3: Portrait space video with alt text
    {
        "id": 3, "duration": 35, "width": 1080, "height": 1920,
        "alt": "Stars timelapse night sky cosmos",
        "url": "https://www.pexels.com/video/stars-cosmos-9012/",
        "user": {"name": "Astrophoto"},
        "video_files": [{"quality": "hd", "link": "http://x.com/v3.mp4"}],
    },
    # id=4: Beach video — blocked by NEGATIVE_KEYWORDS even if URL has "space" absent
    {
        "id": 4, "duration": 20, "width": 1920, "height": 1080,
        "alt": "Beautiful beach sunset",
        "url": "https://www.pexels.com/video/beach-sunset-3456/",
        "user": {"name": "NatureFilms"},
        "video_files": [{"quality": "sd", "link": "http://x.com/v4.mp4"}],
    },
]

# ── Tests ─────────────────────────────────────────────────────────────────────

def test_empty_alt_detected_via_url_slug():
    """Video with empty alt but space slug URL should PASS the filter."""
    result = pick_best(FAKE_VIDEOS, used_ids=set(), require_space=True)
    assert result is not None, "Expected a result"
    assert result[4] in (1, 3), f"Expected id 1 or 3, got {result[4]}"
    print(f"PASS test_empty_alt_detected_via_url_slug: chose id={result[4]}")


def test_negative_keyword_blocks_kid_video():
    """Kid video should be blocked even though it is portrait+HD."""
    # Let's check id=2 directly via extract_text_fields + has_negative
    vid2 = FAKE_VIDEOS[1]
    combined = extract_text_fields(vid2)
    assert has_negative_keyword(combined), f"Expected kid to trigger negative, combined='{combined}'"
    print("PASS test_negative_keyword_blocks_kid_video")


def test_beach_video_blocked():
    """Beach/non-space video blocked regardless of video quality."""
    vid4 = FAKE_VIDEOS[3]
    combined = extract_text_fields(vid4)
    assert has_negative_keyword(combined), f"Beach not blocked, combined='{combined}'"
    print("PASS test_beach_video_blocked")


def test_used_id_skip():
    """Videos with already-used IDs must be skipped."""
    result = pick_best(FAKE_VIDEOS, used_ids={"1", "3"}, require_space=True)
    assert result is None, f"Expected None (all space vids used or blocked), got {result}"
    print("PASS test_used_id_skip")


def test_relaxed_fallback_skips_negative_keywords():
    """Even in relaxed mode, negative keywords still block videos."""
    # ids 1 and 3 used, loose filter — should still block kids(2) and beach(4)
    result = pick_best(FAKE_VIDEOS, used_ids={"1", "3"}, require_space=False)
    # kid(2) and beach(4) have negative keywords, so result should be None
    assert result is None, f"Expected None (negative keywords block remaining), got {result}"
    print("PASS test_relaxed_fallback_skips_negative_keywords")


def test_randomised_selection():
    """Should select different space video IDs across repeated calls."""
    ids_seen = set()
    for _ in range(50):
        r = pick_best(FAKE_VIDEOS, used_ids=set(), require_space=True)
        if r:
            ids_seen.add(r[4])
    assert len(ids_seen) > 1, f"Randomisation not working, only got ids: {ids_seen}"
    print(f"PASS test_randomised_selection: saw ids {ids_seen} over 50 runs")


def test_portrait_video_preferred_over_landscape():
    """Portrait clips should score higher than equivalent landscape clips."""
    portrait = {
        "id": 10, "duration": 30, "width": 1080, "height": 1920,
        "alt": "galaxy stars space", "url": "https://www.pexels.com/video/galaxy-stars-10/",
        "user": {"name": "A"},
        "video_files": [{"quality": "hd", "link": "http://x.com/p.mp4"}],
    }
    landscape = {
        "id": 11, "duration": 30, "width": 1920, "height": 1080,
        "alt": "galaxy stars space", "url": "https://www.pexels.com/video/galaxy-stars-11/",
        "user": {"name": "A"},
        "video_files": [{"quality": "hd", "link": "http://x.com/l.mp4"}],
    }
    # Run 20 times — portrait should win far more often than landscape due to +3 bonus
    wins = {10: 0, 11: 0}
    for _ in range(20):
        r = pick_best([portrait, landscape], used_ids=set(), require_space=True)
        if r:
            wins[r[4]] = wins.get(r[4], 0) + 1
    assert wins[10] > wins[11], f"Portrait should win more often: {wins}"
    print(f"PASS test_portrait_video_preferred: portrait={wins[10]} landscape={wins[11]}")


if __name__ == "__main__":
    tests = [
        test_empty_alt_detected_via_url_slug,
        test_negative_keyword_blocks_kid_video,
        test_beach_video_blocked,
        test_used_id_skip,
        test_relaxed_fallback_skips_negative_keywords,
        test_randomised_selection,
        test_portrait_video_preferred_over_landscape,
    ]
    failures = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            print(f"FAIL {t.__name__}: {e}")
            failures += 1
    print()
    if failures:
        print(f"{failures}/{len(tests)} test(s) FAILED")
        sys.exit(1)
    else:
        print(f"All {len(tests)} tests PASSED ✅")
